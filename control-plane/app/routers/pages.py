"""Sirius Argus — роутер: страницы UI и HTMX-фрагменты (вынесено из main)."""
import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import requests
from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel

from .. import audit, bus, decisions, domain, mapnodes, registry, runs, scanners, signing, storage, ui
from ..auth import Principal, get_principal, revoke
from ..db import AuditEvent, SessionLocal
from ..rbac import PERMISSIONS, can_read_sensitivity, require

logger = logging.getLogger("sirius")
router = APIRouter()


@router.get("/")
def home():
    """Стартовый экран = пайплайн (обзор контура): он отражает ценность платформы."""
    return RedirectResponse(url="/map", status_code=307)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard():
    """Read-only ops-консоль: KPI + live-сработки/аудит (HTMX). API /api/* — под authN/RBAC."""
    return ui.dashboard(_coverage_data()["kpi"])


@router.get("/ui/findings", response_class=HTMLResponse)
def ui_findings():
    """HTMX-фрагмент: последние сработки (детали-метки, без значений секретов — LOG-01)."""
    with SessionLocal() as s:
        rows = s.query(domain.Finding).order_by(domain.Finding.id.desc()).limit(25).all()
        items = [{"ts": f.ts, "tool": f.tool, "verdict": f.verdict, "severity": f.severity,
                  "asset": f.asset_ref, "status": f.status} for f in rows]
    return ui.findings_fragment(items)


def _findings_query(status="", severity=""):
    """Сработки (read-only) с опциональными фильтрами по статусу/критичности."""
    with SessionLocal() as s:
        q = s.query(domain.Finding)
        if status:
            q = q.filter(domain.Finding.status == status)
        if severity:
            q = q.filter(domain.Finding.severity == severity)
        rows = q.order_by(domain.Finding.id.desc()).limit(200).all()
        return [{"ts": f.ts, "tool": f.tool, "verdict": f.verdict, "severity": f.severity,
                 "asset": f.asset_ref, "detail": f.detail, "status": f.status,
                 "actor": f.actor, "role": f.role} for f in rows]


@router.get("/ui/findings/list", response_class=HTMLResponse)
def ui_findings_list(status: str = Query(""), severity: str = Query("")):
    """HTMX-фрагмент для /findings: полный отфильтрованный список (детали + статус)."""
    return ui.findings_table(_findings_query(status, severity))


@router.get("/ui/audit", response_class=HTMLResponse)
def ui_audit():
    """HTMX-фрагмент: хвост аудит-таймлайна (append-only, hash-chain)."""
    return ui.audit_fragment(audit.recent(25))


@router.get("/roles", response_class=HTMLResponse)
def roles_view():
    """Матрица прав (zero-trust RBAC): кто какое действие может выполнить."""
    roles = set().union(*PERMISSIONS.values()) if PERMISSIONS else set()
    return ui.roles_page(PERMISSIONS, roles)


@router.get("/registry", response_class=HTMLResponse)
def registry_view():
    """Read-only витрина реестра (как дашборд, без логина): модели, версии, стадии.
    Чувствительные операции и lineage — через /api/* под RBAC."""
    with SessionLocal() as s:
        models, versions_total, prod, critical = [], 0, 0, 0
        for m in s.query(domain.Model).all():
            vers = (s.query(domain.ModelVersion).filter_by(model_id=m.id)
                    .order_by(domain.ModelVersion.version).all())
            versions_total += len(vers)
            prod += sum(1 for v in vers if v.stage == "prod")
            critical += 1 if m.criticality in ("regulatory", "financial") else 0
            models.append({"id": m.id, "name": m.name, "criticality": m.criticality,
                           "versions": [{"version": v.version, "stage": v.stage} for v in vers]})
    kpi = {"models": len(models), "versions": versions_total, "prod": prod, "critical": critical}
    return ui.registry_page(models, kpi)


@router.get("/services", response_class=HTMLResponse)
def services_view():
    """Карта сервисов системы: что наружу (кликабельно) и что внутри (zero-trust)."""
    return ui.services_page()


_SEVRANK = {"critical": 4, "high": 3, "medium": 2, "low": 1, "info": 0}


def _map_status_dict():
    """Статус каждого узла из open-findings: open-счётчик, max severity, alert/warn/clean."""
    out = {nid: {"label": mapnodes.LABELS[nid], "status": "clean", "open": 0, "sev": None, "last": None}
           for nid in mapnodes.ALL_NODES}
    rank = {nid: -1 for nid in mapnodes.ALL_NODES}
    with SessionLocal() as s:
        rows = s.query(domain.Finding).filter(domain.Finding.status == "open").all()
    for f in rows:
        nid = mapnodes.node_of(f.verdict, f.tool, f.asset_type, f.asset_ref)
        if nid not in out:
            nid = "control-plane"
        o = out[nid]
        o["open"] += 1
        r = _SEVRANK.get(f.severity, 0)
        if r > rank[nid]:
            rank[nid] = r
            o["sev"] = f.severity
            o["last"] = f.ts
    for nid, o in out.items():
        if o["open"] == 0:
            o["status"] = "clean"
        elif rank[nid] >= 3:   # high / critical
            o["status"] = "alert"
        else:
            o["status"] = "warn"
    return out


def _node_findings(node_id, limit=60):
    with SessionLocal() as s:
        rows = s.query(domain.Finding).order_by(domain.Finding.id.desc()).limit(400).all()
    items = []
    for f in rows:
        if mapnodes.node_of(f.verdict, f.tool, f.asset_type, f.asset_ref) == node_id:
            items.append({"id": f.id, "ts": f.ts, "tool": f.tool, "verdict": f.verdict, "severity": f.severity,
                          "asset": f.asset_ref, "detail": f.detail, "status": f.status})
        if len(items) >= limit:
            break
    return items


@router.get("/map", response_class=HTMLResponse)
def map_view():
    """Обзор контура: граф ЖЦ (ветвление сервинг→эндпоинты) + сводка за смену + живой поток.
    Данные реальные: узлы из map-status, эндпоинты из активных деплоев, фид — findings + аудит."""
    st = _map_status_dict()
    pipeline = [{"id": nid, "label": lbl, "gate": gate, **st[nid]} for nid, lbl, gate in mapnodes.PIPELINE]
    infra = [{"id": nid, "label": lbl, **st[nid]} for nid, lbl in mapnodes.INFRA]
    with SessionLocal() as s:
        endpoints = []
        for d in s.query(domain.Deployment).filter_by(status="active").all():
            mv = s.query(domain.ModelVersion).filter_by(id=d.model_version_id).first()
            m = s.query(domain.Model).filter_by(id=mv.model_id).first() if mv else None
            endpoints.append({"id": f"ep-{d.id}", "label": (m.name if m else f"mv{d.model_version_id}"), "state": "clean"})
        sev_counts = {sv: 0 for sv in ("critical", "high", "medium", "low")}
        for (sv,) in s.query(domain.Finding.severity).filter(domain.Finding.status.in_(("open", "TP"))).all():
            if sv in sev_counts:
                sev_counts[sv] += 1
        ep_open = s.query(domain.Finding).filter(domain.Finding.asset_type == "endpoint",
                                                 domain.Finding.status == "open").count()
        recent_f = s.query(domain.Finding).order_by(domain.Finding.id.desc()).limit(18).all()
        feed_f = [{"t": ((f.ts or "").split("T")[-1][:8]), "lvl": ("err" if f.severity in ("critical", "high") else "warn" if f.severity == "medium" else "info"),
                   "src": f.tool or "finding", "msg": f"{f.verdict} · {f.asset_ref}",
                   "node": mapnodes.node_of(f.verdict, f.tool, f.asset_type, f.asset_ref)} for f in recent_f]
    if ep_open and endpoints:
        endpoints[0]["state"] = "alert"
    feed_a = []
    for a in audit.recent(18):
        act = (getattr(a, "action", "") or "")
        lvl = "err" if ("denied" in act or "blocked" in act) else "sec" if ("secret" in act or "auth" in act or "loaded" in act) else "ok"
        feed_a.append({"t": ((getattr(a, "ts", "") or "").split("T")[-1][:8]), "lvl": lvl, "src": (getattr(a, "actor", "-") or "-"), "msg": act, "node": None})
    feed = sorted(feed_f + feed_a, key=lambda x: x["t"])[-44:]
    return ui.map_page(pipeline, infra, endpoints, feed, sev_counts)


@router.get("/api/map/status")
def map_status():
    """JSON для live-поллера карты: статус/open/severity по каждому узлу."""
    return JSONResponse({"nodes": _map_status_dict()})


@router.get("/map/node/{node_id}", response_class=HTMLResponse)
def map_node_view(node_id: str, run: str = ""):
    """Инспектор узла: рейл + шапка + очередь прогонов (ModelVersion) + инспектор выбранного
    прогона (lineage + сработки с причастным + лог). ?run=RUN-<id> — выбор прогона."""
    st = _map_status_dict()
    pipeline = [{"id": nid, "label": lbl, "gate": gate, **st[nid]} for nid, lbl, gate in mapnodes.PIPELINE]
    infra = [{"id": nid, "label": lbl, **st[nid]} for nid, lbl in mapnodes.INFRA]
    alln = {n["id"]: n for n in pipeline + infra}
    node = alln.get(node_id) or pipeline[0]
    rlist = runs.runs_for_node(node_id)
    sel = next((r for r in rlist if r["id"] == run), (rlist[0] if rlist else None))
    detail = runs.run_detail(sel["id"]) if sel else {}
    return ui.map_inspector_page(node, pipeline, infra, rlist, sel, detail)


@router.post("/ui/map/run/{run}/{decision}", response_class=HTMLResponse)
def ui_map_run_decision(run: str, decision: str, approver: str = Form(""), reason: str = Form("")):
    """UI-действие аппрув-гейта из инспектора прогона: зафиксировать решение (approve|reject) и
    вернуть обновлённую внутренность инспектора. У control-plane UI нет отдельного логина
    (SSO — у ops-консолей), поэтому аппрувер выбирается из MLSecOps-учёток; запись идёт
    общим кодом decisions.record_decision (Approval + аудит). Реальный separation of duties
    (аппрувер ≠ владелец, аппрувер ≠ промоутер, привязка к hash) энфорсится на промоушене."""
    if decision not in decisions.DECISIONS:
        raise HTTPException(status_code=422, detail="decision must be approve|reject")
    if approver not in decisions.UI_APPROVERS:
        raise HTTPException(status_code=403, detail="approver must be an MLSecOps account")
    mvid = runs._parse_run_id(run)
    if mvid is None:
        raise HTTPException(status_code=404, detail="run not found")
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(id=mvid).first()
        if not mv:
            raise HTTPException(status_code=404, detail="run not found")
        model_id, ver = mv.model_id, mv.version
    # UI-аппруверы валидированы как MLSecOps-учётки (decisions.UI_APPROVERS) → роль известна
    decisions.record_decision(model_id, ver, approver, decision, reason, "MLSecOps")
    sel = runs.run_summary(run)
    detail = runs.run_detail(run) if sel else {}
    return ui.map_inspector_fragment(sel, detail)


@router.get("/ui/map/node/{node_id}", response_class=HTMLResponse)
def ui_map_node(node_id: str):
    """HTMX-фрагмент drill: контроли узла + его сработки + хвост аудита."""
    label = mapnodes.LABELS.get(node_id, node_id)
    controls = mapnodes.CONTROLS.get(node_id, [])
    return ui.map_node_fragment(node_id, label, controls, _node_findings(node_id), audit.recent(15))


@router.get("/ui/map/incident/{finding_id}", response_class=HTMLResponse)
def ui_map_incident(finding_id: int):
    """HTMX-фрагмент: одна сработка как «инцидент» + окно аудит-таймлайна."""
    with SessionLocal() as s:
        f = s.query(domain.Finding).filter_by(id=finding_id).first()
        fd = ({"id": f.id, "ts": f.ts, "tool": f.tool, "verdict": f.verdict, "severity": f.severity,
               "asset": f.asset_ref, "detail": f.detail, "status": f.status,
               "actor": f.actor, "role": f.role} if f else None)
    return ui.map_incident_fragment(fd, audit.recent(20))


@router.get("/findings", response_class=HTMLResponse)
def findings_view(status: str = Query(""), severity: str = Query("")):
    """Read-only журнал сработок с фильтрами и live-обновлением.
    Триаж (смена статуса) — VIS-04: через /api/findings/{id}/triage под ролью MLSecOps."""
    with SessionLocal() as s:
        statuses = [x for (x,) in s.query(domain.Finding.status).all()]
    kpi = {"total": len(statuses),
           "open": sum(1 for x in statuses if x == "open"),
           "TP": sum(1 for x in statuses if x == "TP"),
           "FP": sum(1 for x in statuses if x == "FP")}
    return ui.findings_page(kpi, status, severity)


@router.get("/serving", response_class=HTMLResponse)
def serving_view():
    """Read-only окно прод-сервинга: активные деплойменты, рантайм-защиты периметра и
    live-сработки эндпоинтов. Инференс отдаёт отдельный serving-API (:8001) — здесь единая
    точка видимости (control-plane), а не сырой JSON."""
    with SessionLocal() as s:
        deps = []
        for d in s.query(domain.Deployment).filter_by(status="active").all():
            mv = s.query(domain.ModelVersion).filter_by(id=d.model_version_id).first()
            if not mv:
                continue
            m = s.query(domain.Model).filter_by(id=mv.model_id).first()
            deps.append({"model": m.name if m else f"model#{mv.model_id}",
                         "type": m.type if m else "", "criticality": m.criticality if m else "internal",
                         "version": mv.version, "stage": mv.stage})
        rt_total = s.query(domain.Finding).filter(domain.Finding.asset_type == "endpoint").count()
        last = (s.query(domain.Finding).filter(domain.Finding.asset_type == "endpoint")
                .order_by(domain.Finding.id.desc()).first())
    kpi = {"deployments": len(deps), "runtime_findings": rt_total, "last": last.verdict if last else "—"}
    return ui.serving_page(deps, kpi)


@router.get("/ui/serving/runtime", response_class=HTMLResponse)
def ui_serving_runtime():
    """HTMX-фрагмент: последние рантайм-сработки сервинга (endpoint-findings, live)."""
    with SessionLocal() as s:
        rows = (s.query(domain.Finding).filter(domain.Finding.asset_type == "endpoint")
                .order_by(domain.Finding.id.desc()).limit(25).all())
        items = [{"ts": f.ts, "verdict": f.verdict, "severity": f.severity,
                  "asset": f.asset_ref, "detail": f.detail, "status": f.status} for f in rows]
    return ui.serving_runtime_fragment(items)


COVERAGE = [
    {"id": "SUP-01", "threat": "вредоносный артефакт модели", "control": "ingestion-скан (pickle-опкоды)", "match": ("verdict", "malicious")},
    {"id": "SUP-07", "threat": "небезопасный формат критичной модели", "control": "политика форматов", "match": ("verdict", "unsafe-format")},
    {"id": "SUP-03", "threat": "уязвимая зависимость (CVE)", "control": "скан зависимостей", "match": ("verdict", "vulnerable-dependency")},
    {"id": "DATA-01", "threat": "недоверенный источник данных", "control": "карантин источника", "match": ("verdict", "untrusted-source")},
    {"id": "CODE-01", "threat": "небезопасный паттерн в коде", "control": "ML-aware AST-SAST", "match": ("verdict", "insecure-code")},
    {"id": "ACC-06", "threat": "утёкший секрет в коде", "control": "скан секретов", "match": ("verdict", "secret-exposed")},
    {"id": "VIS-02", "threat": "расхождение вердиктов / фолз", "control": "триаж сработок", "match": ("verdict", "suspicious")},
    {"id": "RT-01", "threat": "extraction модели в рантайме", "control": "rate-limit + детект", "match": ("verdict", "extraction")},
    {"id": "VIS-03/GOV-01/SUP-04", "threat": "небезопасный промоушен критичной модели", "control": "gated promotion (карта+подпись+ручной аппрув-гейт)", "match": ("prefix", "promote.blocked")},
    {"id": "ACC-01/ESC-01", "threat": "действие вне роли / IDOR", "control": "zero-trust RBAC + object-level", "match": ("prefix", "authz.deny")},
    {"id": "CRED-01/AUTH-01", "threat": "невалидный/поддельный токен", "control": "OIDC fail-closed", "match": ("exact", "access.denied")},
    {"id": "EXF-01", "threat": "инсайдерская эксфильтрация", "control": "детект объёма выгрузок", "match": ("verdict", "bulk-exfiltration")},
    {"id": "MON-03", "threat": "вывод из эксплуатации", "control": "decommission снимает деплои", "match": ("prefix", "model.retire")},
    {"id": "CI-01", "threat": "отравленный коммит / шаг пайплайна", "control": "control-plane как CI + HMAC-вебхук", "match": ("prefix", "ci.")},
    {"id": "RT-02", "threat": "adversarial/OOD-вход в рантайме", "control": "OOD-детект моделью аномалий", "match": ("verdict", "adversarial-suspect")},
    {"id": "DOS-01", "threat": "распределённый DDoS на сервинг", "control": "глобальный load-shedding", "match": ("verdict", "ddos")},
    {"id": "RT-05", "threat": "malformed-запрос (DoS)", "control": "валидация входа (fail-closed 422)", "match": ("verdict", "malformed-input")},
    {"id": "TOCTOU-01", "threat": "подмена артефакта после скана", "control": "ре-верификация hash при загрузке", "match": ("verdict", "artifact-tampered")},
    {"id": "SUP-05", "threat": "перезапись/подмена артефакта", "control": "integrity-проверка hash", "match": ("verdict", "artifact-tampered")},
    {"id": "ACC-03", "threat": "неотозванный доступ (offboarding)", "control": "немедленный отзыв субъекта", "match": ("prefix", "offboard")},
    {"id": "MON-01", "threat": "дрейф данных/концепта", "control": "drift-монитор сервинга (окно vs обучающая база)", "match": ("verdict", "drift")},
    {"id": "SUP-02", "threat": "тайпсквоттинг-зависимость", "control": "allow-list + имя-эвристика", "match": ("verdict", "typosquat-dependency")},
    {"id": "SUP-08", "threat": "dependency confusion", "control": "пины + внутренний индекс", "match": ("verdict", "dependency-confusion")},
    {"id": "ACC-07", "threat": "захардкоженная бизнес-логика", "control": "AST-детект порогов + review-гейт", "match": ("verdict", "hardcoded-logic")},
    {"id": "DATA-02", "threat": "подмена меток поставщиком (label-flip)", "control": "статистика распределения меток", "match": ("verdict", "label-flip")},
    {"id": "DATA-03", "threat": "UGC-бэкдор-триггер", "control": "детект скрытых символов + карантин", "match": ("verdict", "backdoor-trigger")},
    {"id": "DATA-05", "threat": "train-serving skew", "control": "consistency train↔serve", "match": ("verdict", "train-serve-skew")},
    {"id": "FB-01", "threat": "отравление петли дообучения", "control": "провенанс фидбека дообучения", "match": ("verdict", "feedback-poisoning")},
    {"id": "DOW-01", "threat": "denial-of-wallet (исчерпание бюджета)", "control": "стоимостная квота на тенанта", "match": ("verdict", "denial-of-wallet")},
    {"id": "DOS-02", "threat": "оверсайз-загрузка (resource exhaustion)", "control": "лимит размера тела — 413 (Caddy + app)", "match": ("verdict", "oversized-upload")},
    {"id": "GOV-02", "threat": "принятие остаточного риска под условиями", "control": "risk-acceptance (роль+обоснование+срок) → conditional-деплой", "match": ("prefix", "risk.accept")},
    {"id": "CRED-02", "threat": "секреты в env/коде (утечка, нет отзыва)", "control": "Vault: выдача по политике (AppRole) + аудит + revoke/rotate", "match": ("exact", "secrets.loaded.vault")},
]


def _coverage_data():
    with SessionLocal() as s:
        findings = s.query(domain.Finding).all()
        actions = [a for (a,) in s.query(AuditEvent.action).all()]
        by_verdict, by_sev, by_status = defaultdict(int), defaultdict(int), defaultdict(int)
        for f in findings:
            by_verdict[f.verdict] += 1
            by_sev[f.severity] += 1
            by_status[f.status] += 1
        models = s.query(domain.Model).count()
        prod = s.query(domain.Deployment).filter_by(status="active").count()
    controls, live = [], 0
    for c in COVERAGE:
        kind, val = c["match"]
        if kind == "verdict":
            cnt = by_verdict.get(val, 0)
        elif kind == "prefix":
            cnt = sum(1 for a in actions if a.startswith(val))
        else:
            cnt = sum(1 for a in actions if a == val)
        controls.append({"id": c["id"], "threat": c["threat"], "control": c["control"],
                         "evidence": cnt, "status": "live" if cnt else "ready"})
        live += 1 if cnt else 0
    kpi = {"findings_total": len(findings), "by_severity": dict(by_sev), "by_status": dict(by_status),
           "blocked_attempts": sum(1 for a in actions if ".blocked" in a),
           "access_denied": sum(1 for a in actions if a.startswith("authz.deny") or a == "access.denied"),
           "models": models, "prod_deployments": prod,
           "coverage": f"{live}/{len(COVERAGE)}", "audit_chain_ok": audit.verify_chain()}
    return {"controls": controls, "kpi": kpi}


@router.get("/api/coverage")
def coverage(p: Principal = Depends(require("visibility.read"))):
    """VIS-01: карта покрытия (угроза→контроль→live-статус) + KPI поверх реальных Finding/аудита."""
    audit.append_event(actor=p.sub, action="coverage.read")
    return _coverage_data()


@router.get("/coverage", response_class=HTMLResponse)
def coverage_view():
    """CEO-вью: карта покрытия угроз + KPI (read-only экран, money-shot #5)."""
    return ui.coverage_page(_coverage_data())
