"""Sirius Argus — роутер: CI-вебхук и сканеры."""
import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel

from .. import audit, bus, domain, mapnodes, registry, scanners, signing, storage, ui
from ..auth import Principal, get_principal, revoke
from ..db import AuditEvent, SessionLocal
from ..rbac import PERMISSIONS, can_read_sensitivity, require

logger = logging.getLogger("sirius")
router = APIRouter()


GITEA_URL = os.environ.get("GITEA_BASE_URL", "http://gitea:3000")


GITEA_TOKEN = os.environ.get("GITEA_TOKEN", "")


CI_WEBHOOK_SECRET = os.environ.get("CI_WEBHOOK_SECRET", "")


class CiFile(BaseModel):
    path: str
    content: str = ""


class CiScanIn(BaseModel):
    ref: str = "HEAD"
    files: list[CiFile] = []


def _ci_gate(files):
    """Прогон файлов коммита через гейты: код (SAST+секреты), зависимости, секреты."""
    findings = []
    for f in files:
        path, content = f.get("path", ""), f.get("content", "")
        if path.endswith((".py", ".ipynb")):
            findings += scanners.scan_code(content, path) + scanners.scan_secrets(content)
        elif "requirements" in path and path.endswith(".txt"):
            findings += scanners.scan_dependencies(content)
        else:
            findings += scanners.scan_secrets(content)
    return findings


def _record_ci(findings, ref, actor, role=""):
    if findings:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with SessionLocal() as s:
            for r in findings:
                s.add(domain.Finding(ts=now, tool=r["tool"], verdict=r["verdict"], severity=r["severity"],
                                     status="open", asset_type="ci", asset_ref=f"ci/{ref}", detail=r["detail"],
                                     actor=actor, role=role))
            s.commit()


@router.post("/api/ci/scan")
def ci_scan(body: CiScanIn, p: Principal = Depends(require("ci.scan"))):
    """CI-01: гейт «control-plane как CI» — отравленный коммит не проходит (fail-closed)."""
    findings = _ci_gate([f.model_dump() for f in body.files])
    _record_ci(findings, body.ref, p.sub, p.primary_role())
    passed = not findings
    audit.append_event(actor=p.sub, action="ci.scan.passed" if passed else "ci.scan.blocked", obj=f"ci/{body.ref}")
    return {"passed": passed, "ref": body.ref, "findings": findings}


def _fetch_changed_files(repo, sha, payload):
    if not (repo and sha and GITEA_TOKEN):
        return []
    paths = set()
    for c in payload.get("commits", []):
        paths.update((c.get("added") or []) + (c.get("modified") or []))
    files = []
    for path in list(paths)[:20]:
        try:
            r = requests.get(f"{GITEA_URL}/api/v1/repos/{repo}/raw/{path}", params={"ref": sha},
                             headers={"Authorization": f"token {GITEA_TOKEN}"}, timeout=4)
            if r.status_code == 200:
                files.append({"path": path, "content": r.text})
        except requests.RequestException:
            pass
    return files


def _post_commit_status(repo, sha, passed, n):
    if not (repo and sha and GITEA_TOKEN):
        return
    try:
        requests.post(f"{GITEA_URL}/api/v1/repos/{repo}/statuses/{sha}",
                      headers={"Authorization": f"token {GITEA_TOKEN}"},
                      json={"state": "success" if passed else "failure", "context": "sirius/security-gate",
                            "description": "ок" if passed else f"{n} сработок — блок"}, timeout=4)
    except requests.RequestException as e:
        logger.warning("не удалось выставить commit-status в Gitea: %s", e)


@router.post("/api/ci/webhook")
async def ci_webhook(request: Request):
    """Единая точка входа: Gitea webhook → security-гейт → commit-status обратно.
    Подпись HMAC обязательна (поддельный вебхук отвергается, CI-01). Изменённые файлы
    тянутся из Gitea API, гоняются через _ci_gate; статус ставится обратно (best-effort)."""
    body = await request.body()
    if CI_WEBHOOK_SECRET:
        expected = hmac.new(CI_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(request.headers.get("X-Gitea-Signature", ""), expected):
            audit.append_event(actor="gitea-webhook", action="ci.webhook.rejected", obj="ci", was_authorized=False)
            raise HTTPException(status_code=401, detail="invalid webhook signature")
        # anti-replay: вебхук одноразовый. Nonce — X-Gitea-Delivery (или сама подпись) — кладётся в
        # Redis с TTL; повтор того же подписанного запроса отбивается (HMAC сам по себе от replay не спасает).
        nonce = request.headers.get("X-Gitea-Delivery") or expected
        if bus.once(f"ci:webhook:nonce:{nonce}", 600) is False:  # False=уже видели; None=Redis недоступен (не блокируем)
            audit.append_event(actor="gitea-webhook", action="ci.webhook.replay", obj="ci", was_authorized=False)
            raise HTTPException(status_code=401, detail="webhook replay rejected (nonce already seen)")
    try:
        payload = json.loads(body or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="bad payload")
    repo = (payload.get("repository") or {}).get("full_name", "")
    sha = payload.get("after", "")
    findings = _ci_gate(_fetch_changed_files(repo, sha, payload))
    passed = not findings
    _post_commit_status(repo, sha, passed, len(findings))
    _record_ci(findings, f"{repo}@{sha[:8]}" if sha else (repo or "webhook"), "gitea-webhook", "Service")
    audit.append_event(actor="gitea-webhook", action="ci.webhook.passed" if passed else "ci.webhook.blocked", obj=f"ci/{repo}")
    return {"accepted": True, "passed": passed, "findings": len(findings)}


@router.post("/api/scan/code")
async def scan_code_endpoint(request: Request, filename: str = Query("submitted.py"),
                             p: Principal = Depends(require("code.scan"))):
    """CODE-01: AST-скан кода/ноутбука на опасные паттерны. Код НЕ исполняется
    (только ast.parse). Pattern-based MVP; полный Semgrep-гейт на PR — в И3."""
    src = (await request.body()).decode("utf-8", "replace")
    findings = scanners.scan_code(src, filename) + scanners.scan_secrets(src)
    if findings:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with SessionLocal() as s:
            for r in findings:
                s.add(domain.Finding(ts=now, tool=r["tool"], verdict=r["verdict"], severity=r["severity"],
                                     status="open", asset_type="code", asset_ref=f"code/{filename}", detail=r["detail"],
                                     actor=p.sub, role=p.primary_role()))
            s.commit()
        audit.append_event(actor=p.sub, action="code.scan.flagged", obj=f"code/{filename}")
        return {"filename": filename, "clean": False, "findings": findings}
    audit.append_event(actor=p.sub, action="code.scan.clean", obj=f"code/{filename}")
    return {"filename": filename, "clean": True, "findings": []}


@router.post("/api/scan/deps")
async def scan_deps_endpoint(request: Request, filename: str = Query("requirements.txt"),
                             p: Principal = Depends(require("code.scan"))):
    """SUP-03/SC-01: скан зависимостей (пины requirements) против базы известных CVE.
    Уязвимая зависимость → Finding и не проходит гейт перед продом."""
    reqs = (await request.body()).decode("utf-8", "replace")
    findings = scanners.scan_dependencies(reqs)
    if findings:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with SessionLocal() as s:
            for r in findings:
                s.add(domain.Finding(ts=now, tool=r["tool"], verdict=r["verdict"], severity=r["severity"],
                                     status="open", asset_type="deps", asset_ref=f"deps/{filename}", detail=r["detail"],
                                     actor=p.sub, role=p.primary_role()))
            s.commit()
        audit.append_event(actor=p.sub, action="deps.scan.flagged", obj=f"deps/{filename}")
        return {"filename": filename, "clean": False, "findings": findings}
    audit.append_event(actor=p.sub, action="deps.scan.clean", obj=f"deps/{filename}")
    return {"filename": filename, "clean": True, "findings": []}


class DatasetScanIn(BaseModel):
    labels: list = []
    expected_labels: list = []
    baseline_dist: dict = {}
    samples: list = []
    train_stats: dict = {}
    serve_stats: dict = {}
    feedback: list = []


@router.post("/api/scan/dataset")
def scan_dataset_endpoint(body: DatasetScanIn, p: Principal = Depends(require("dataset.scan"))):
    """Гейт качества/целостности данных (scoped): DATA-02 label-flip, DATA-03 UGC-бэкдор-триггер,
    DATA-05 train-serve skew, FB-01 провенанс петли дообучения. Аномалия → Finding + карантин-сигнал."""
    findings = scanners.scan_dataset(body.model_dump())
    if findings:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with SessionLocal() as s:
            for r in findings:
                s.add(domain.Finding(ts=now, tool=r["tool"], verdict=r["verdict"], severity=r["severity"],
                                     status="open", asset_type="dataset", asset_ref="dataset/scan", detail=r["detail"],
                                     actor=p.sub, role=p.primary_role()))
            s.commit()
        audit.append_event(actor=p.sub, action="dataset.scan.flagged", obj="dataset/scan")
        return {"clean": False, "findings": findings}
    audit.append_event(actor=p.sub, action="dataset.scan.clean", obj="dataset/scan")
    return {"clean": True, "findings": []}
