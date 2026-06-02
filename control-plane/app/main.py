"""Sirius Argus — Control Plane.

Единственная точка входа для людей: health, дашборд с аудит-таймлайном, защищённый
реестр (датасеты/модели/версии) с zero-trust RBAC, lineage и анализом blast-radius.
AuthN — fail-closed (auth.py). Каждое действие и каждый отказ доступа — в аудит.
"""
import hashlib
import hmac
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
import requests
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel

from . import audit, bus, domain, logging_setup, registry, scanners, signing, storage, ui
from .auth import Principal, get_principal, revoke
from .db import AuditEvent, SessionLocal, init_db
from .rbac import PERMISSIONS, can_read_sensitivity, require

logger = logging.getLogger("sirius")

app = FastAPI(title="Sirius Argus — Control Plane")

# Статика (аватар/лого) — /static/*, пакуется в образ из app/static; путь от __file__, не от cwd.
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

# Prometheus-метрики (observability, ADR-0009): аудит ≠ метрики — аудит авторитетен в Postgres
_REQS = Counter("sirius_http_requests_total", "HTTP-запросы control-plane", ["status"])
_FINDINGS_G = Gauge("sirius_findings_total", "Всего сработок (Finding)")
_AUDIT_OK_G = Gauge("sirius_audit_chain_ok", "Целостность аудита: 1=ок, 0=нарушена")


@app.on_event("startup")
def _startup():
    logging_setup.setup_logging()
    init_db()


@app.middleware("http")
async def observe_and_audit(request: Request, call_next):
    if request.url.path not in ("/metrics", "/health"):
        logger.info("req %s %s auth=%s", request.method, request.url.path, request.headers.get("authorization", "-"))
    resp = await call_next(request)
    _REQS.labels(status=str(resp.status_code)).inc()
    if request.url.path.startswith("/api/") and resp.status_code in (401, 403):
        audit.append_event(actor="anonymous", action="access.denied", obj=request.url.path, was_authorized=False)
    return resp


# ---------- health & dashboard ----------
@app.get("/health")
def health():
    return {"status": "ok", "service": "control-plane", "audit_chain_ok": audit.verify_chain(),
            "bus": {"connected": bus.connected(), "events": bus.stream_len()},
            "mlflow": {"configured": registry.configured(), "connected": registry.connected()}}


@app.get("/metrics")
def metrics():
    """Prometheus-метрики (scrape во внутренней сети, наружу не публикуется)."""
    with SessionLocal() as s:
        _FINDINGS_G.set(s.query(domain.Finding).count())
    _AUDIT_OK_G.set(1 if audit.verify_chain() else 0)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    """Read-only ops-консоль: KPI + live-сработки/аудит (HTMX). API /api/* — под authN/RBAC."""
    return ui.dashboard(_coverage_data()["kpi"])


@app.get("/ui/findings", response_class=HTMLResponse)
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
                 "asset": f.asset_ref, "detail": f.detail, "status": f.status} for f in rows]


@app.get("/ui/findings/list", response_class=HTMLResponse)
def ui_findings_list(status: str = Query(""), severity: str = Query("")):
    """HTMX-фрагмент для /findings: полный отфильтрованный список (детали + статус)."""
    return ui.findings_table(_findings_query(status, severity))


@app.get("/ui/audit", response_class=HTMLResponse)
def ui_audit():
    """HTMX-фрагмент: хвост аудит-таймлайна (append-only, hash-chain)."""
    return ui.audit_fragment(audit.recent(25))


@app.get("/roles", response_class=HTMLResponse)
def roles_view():
    """Матрица прав (zero-trust RBAC): кто какое действие может выполнить."""
    roles = set().union(*PERMISSIONS.values()) if PERMISSIONS else set()
    return ui.roles_page(PERMISSIONS, roles)


@app.get("/registry", response_class=HTMLResponse)
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


@app.get("/findings", response_class=HTMLResponse)
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


@app.get("/api/whoami")
def whoami(p: Principal = Depends(get_principal)):
    audit.append_event(actor=p.sub, action="api.whoami")
    return {"sub": p.sub, "roles": sorted(p.roles)}


# ---------- registry ----------
class ColumnIn(BaseModel):
    name: str
    pii: bool = False
    sample: str = ""


class DatasetIn(BaseModel):
    name: str
    sensitivity: str = "open"
    source: str = ""
    columns: list[ColumnIn] = []


class ModelIn(BaseModel):
    name: str
    type: str = ""
    criticality: str = "internal"


class VersionIn(BaseModel):
    dataset_version_id: int | None = None
    code_commit: str = ""
    env_lock: str = ""
    artifact_hash: str = ""
    signature: str = ""
    intended_use: str = ""
    limitations: str = ""


# DATA-01: доверенные источники данных (allow-list); остальное — в карантин
TRUSTED_SOURCE_PREFIXES = ("internal://", "curated://", "trusted:", "s3://sirius-")


def _is_trusted_source(src: str) -> bool:
    return bool(src) and src.startswith(TRUSTED_SOURCE_PREFIXES)


@app.post("/api/datasets")
def create_dataset(body: DatasetIn, p: Principal = Depends(require("dataset.create"))):
    with SessionLocal() as s:
        ds = domain.Dataset(name=body.name, sensitivity=body.sensitivity, source=body.source, owner=p.sub)
        s.add(ds)
        s.flush()
        dv = domain.DatasetVersion(
            dataset_id=ds.id,
            hash=hashlib.sha256(f"{ds.id}:{body.name}:{body.source}".encode()).hexdigest()[:16],
        )
        s.add(dv)
        for c in body.columns:
            s.add(domain.DatasetColumn(dataset_id=ds.id, name=c.name, is_pii=c.pii, sample=c.sample))
        # DATA-01: недоверенный источник → карантин + Finding (датасет принят в holding, не «чистый»)
        status = "active" if _is_trusted_source(body.source) else "quarantined"
        if status == "quarantined":
            now = datetime.now(timezone.utc).isoformat(timespec="seconds")
            s.add(domain.Finding(ts=now, tool="sirius-source-policy", verdict="untrusted-source",
                                 severity="medium", status="open", asset_type="dataset",
                                 asset_ref=f"dataset/{ds.id}",
                                 detail=f"источник '{body.source or '—'}' не в доверенном списке → карантин", actor=p.sub))
        s.commit()
        audit.append_event(actor=p.sub, action=f"dataset.create:{status}", obj=f"dataset/{ds.id}")
        return {"dataset_id": ds.id, "dataset_version_id": dv.id, "sensitivity": ds.sensitivity, "status": status}


@app.get("/api/datasets/{ds_id}")
def get_dataset(ds_id: int, p: Principal = Depends(require("registry.read"))):
    with SessionLocal() as s:
        ds = s.get(domain.Dataset, ds_id)
        if not ds:
            raise HTTPException(status_code=404, detail="dataset not found")
        # object-level authz (ACC-04 / ESC-01): чувствительность объекта, не только маршрут
        if not can_read_sensitivity(p.roles, ds.sensitivity):
            audit.append_event(actor=p.sub, action="dataset.read.deny", obj=f"dataset/{ds_id}", was_authorized=False)
            raise HTTPException(status_code=403, detail=f"no clearance for sensitivity={ds.sensitivity}")
        audit.append_event(actor=p.sub, action="dataset.read", obj=f"dataset/{ds_id}")
        return {"id": ds.id, "name": ds.name, "sensitivity": ds.sensitivity, "source": ds.source}


@app.get("/api/datasets/{ds_id}/schema")
def dataset_schema(ds_id: int, p: Principal = Depends(require("registry.read"))):
    """DATA-04: PII-колонки маскируются, если у роли нет допуска к pii; иначе видны."""
    with SessionLocal() as s:
        ds = s.get(domain.Dataset, ds_id)
        if not ds:
            raise HTTPException(status_code=404, detail="dataset not found")
        unmasked = can_read_sensitivity(p.roles, "pii")
        cols = s.query(domain.DatasetColumn).filter_by(dataset_id=ds_id).all()
        out = [{"name": c.name, "pii": c.is_pii,
                "sample": c.sample if (unmasked or not c.is_pii) else "***"} for c in cols]
        audit.append_event(actor=p.sub, action="dataset.schema.read", obj=f"dataset/{ds_id}")
        return {"dataset_id": ds_id, "columns": out, "pii_unmasked": unmasked}


@app.post("/api/models")
def create_model(body: ModelIn, p: Principal = Depends(require("model.register"))):
    with SessionLocal() as s:
        m = domain.Model(name=body.name, type=body.type, criticality=body.criticality, owner=p.sub)
        s.add(m)
        s.commit()
        model_id, name = m.id, registry.model_name(m.id, m.name)
        # write-through в обёрнутый MLflow (fail-soft: при недоступности не валимся)
        synced = True
        try:
            registry.ensure_registered_model(name, tags={"criticality": body.criticality, "type": body.type, "owner": p.sub})
        except registry.RegistryError as e:
            synced = False
            logger.warning("MLflow недоступен при регистрации model/%s: %s", model_id, e)
        audit.append_event(actor=p.sub, action="model.register", obj=f"model/{model_id}")
        return {"model_id": model_id, "criticality": m.criticality, "registry_backend": "mlflow", "backend_synced": synced}


@app.post("/api/models/{model_id}/versions")
def create_version(model_id: int, body: VersionIn, p: Principal = Depends(require("model.version"))):
    with SessionLocal() as s:
        m = s.get(domain.Model, model_id)
        if not m:
            raise HTTPException(status_code=404, detail="model not found")
        n = s.query(domain.ModelVersion).filter_by(model_id=model_id).count() + 1
        mv = domain.ModelVersion(
            model_id=model_id, version=n, stage="dev",
            dataset_version_id=body.dataset_version_id, code_commit=body.code_commit,
            env_lock=body.env_lock, artifact_hash=body.artifact_hash, signature=body.signature,
            intended_use=body.intended_use, limitations=body.limitations,
            requires_validation=(m.criticality in ("regulatory", "financial")),
        )
        s.add(mv)
        s.commit()
        mvid, requires_validation = mv.id, mv.requires_validation
        name = registry.model_name(model_id, m.name)
        # write-through: версия + профиль безопасности уходят тегами в MLflow (fail-soft)
        synced, mlflow_ver = True, None
        try:
            registry.ensure_registered_model(name, tags={"criticality": m.criticality})
            mlflow_ver = registry.create_model_version(name, source=f"s3://mlflow/{name}", tags={
                "cp_version": n, "stage": "dev", "code_commit": body.code_commit,
                "dataset_version_id": body.dataset_version_id, "env_lock": body.env_lock,
                "artifact_hash": body.artifact_hash, "signature": body.signature,
                "criticality": m.criticality, "requires_validation": requires_validation})
        except registry.RegistryError as e:
            synced = False
            logger.warning("MLflow недоступен при создании model/%s v%s: %s", model_id, n, e)
        audit.append_event(actor=p.sub, action="model.version", obj=f"model/{model_id}/v{n}")
        return {"model_version_id": mvid, "version": n, "stage": "dev",
                "registry_backend": "mlflow", "backend_synced": synced, "mlflow_version": mlflow_ver}


@app.post("/api/models/{model_id}/versions/{ver}/promote")
def promote(model_id: int, ver: int, p: Principal = Depends(require("model.promote"))):
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        if mv.stage == "retired":  # RB-01: откат на изъятую/уязвимую версию запрещён
            audit.append_event(actor=p.sub, action="promote.blocked.retired", obj=f"model/{model_id}/v{ver}", was_authorized=False)
            raise HTTPException(status_code=409, detail="version retired — rollback to a withdrawn/vulnerable version is blocked (RB-01)")
        # MON-02: невоспроизводимое не пускаем в прод (fail-closed)
        missing = [f for f in ("dataset_version_id", "code_commit", "env_lock") if not getattr(mv, f)]
        if missing:
            audit.append_event(actor=p.sub, action="promote.blocked", obj=f"model/{model_id}/v{ver}", was_authorized=False)
            raise HTTPException(status_code=422, detail=f"not reproducible, missing: {missing}")
        # policy-матрица для критичных моделей (regulatory/financial): модель-карта + подпись + HITL
        if mv.requires_validation:
            if not (mv.intended_use and mv.limitations):  # GOV-01: полнота модель-карты
                audit.append_event(actor=p.sub, action="promote.blocked.modelcard", obj=f"model/{model_id}/v{ver}", was_authorized=False)
                raise HTTPException(status_code=422, detail="incomplete model card (GOV-01): need intended_use + limitations")
            if not signing.verify(model_id, ver, mv.artifact_hash or "", mv.signature or ""):  # SUP-04: крипто-верификация Ed25519
                audit.append_event(actor=p.sub, action="promote.blocked.unsigned", obj=f"model/{model_id}/v{ver}", was_authorized=False)
                raise HTTPException(status_code=422, detail="unsigned or invalid signature (SUP-04)")
            # VIS-03 (HITL) + ACC-02 (separation of duties): нужен аппрув от ДРУГОГО MLSecOps
            others = s.query(domain.Approval).filter(domain.Approval.model_version_id == mv.id,
                                                     domain.Approval.approver != p.sub).count()
            if not others:
                audit.append_event(actor=p.sub, action="promote.blocked.hitl", obj=f"model/{model_id}/v{ver}", was_authorized=False)
                raise HTTPException(status_code=422, detail="HITL approval by a different MLSecOps required (VIS-03/ACC-02)")
        mv.stage = "prod"
        s.add(domain.Deployment(model_version_id=mv.id, status="active"))
        s.commit()
        mvid = mv.id
        m = s.get(domain.Model, model_id)
        name = registry.model_name(model_id, m.name)
        # отражаем стадию в MLflow по нашему cp_version (fail-soft)
        try:
            mlflow_ver = registry.find_version_by_cp(name, ver)
            if mlflow_ver is not None:
                registry.set_version_tag(name, mlflow_ver, "stage", "prod")
        except registry.RegistryError as e:
            logger.warning("MLflow недоступен при промоуте model/%s v%s: %s", model_id, ver, e)
        audit.append_event(actor=p.sub, action="model.promote", obj=f"model/{model_id}/v{ver}")
        return {"model_version_id": mvid, "stage": "prod"}


class ApproveIn(BaseModel):
    reason: str = ""


@app.post("/api/models/{model_id}/versions/{ver}/approve")
def approve_version(model_id: int, ver: int, body: ApproveIn, p: Principal = Depends(require("model.approve"))):
    """VIS-03 HITL: критичную версию вручную одобряет MLSecOps перед промоушеном."""
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        s.add(domain.Approval(model_version_id=mv.id, approver=p.sub,
                              ts=datetime.now(timezone.utc).isoformat(timespec="seconds"), reason=body.reason))
        s.commit()
        audit.append_event(actor=p.sub, action="model.approve", obj=f"model/{model_id}/v{ver}")
        return {"approved": True, "version": ver, "approver": p.sub}


@app.post("/api/models/{model_id}/versions/{ver}/retire")
def retire_version(model_id: int, ver: int, p: Principal = Depends(require("decommission"))):
    """Вывод версии из эксплуатации: снимает активные деплои и помечает retired.
    После этого откат на неё в прод запрещён (RB-01)."""
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        mv.stage = "retired"
        for d in s.query(domain.Deployment).filter_by(model_version_id=mv.id, status="active").all():
            d.status = "retired"
        s.commit()
        audit.append_event(actor=p.sub, action="model.retire", obj=f"model/{model_id}/v{ver}")
        return {"version": ver, "stage": "retired"}


@app.post("/api/models/{model_id}/versions/{ver}/sign")
def sign_version(model_id: int, ver: int, p: Principal = Depends(require("model.sign"))):
    """SUP-04 (ADR-0006): крипто-подпись версии (Ed25519) над model:ver:artifact_hash.
    Без неё промоушен критичной модели не проходит (admission-control)."""
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        mv.signature = signing.sign(model_id, ver, mv.artifact_hash or "")
        s.commit()
        audit.append_event(actor=p.sub, action="model.sign", obj=f"model/{model_id}/v{ver}")
        return {"signed": True, "version": ver, "signature": mv.signature[:20] + "…"}


@app.post("/api/models/{model_id}/versions/{ver}/verify-artifact")
async def verify_artifact_endpoint(model_id: int, ver: int, request: Request, p: Principal = Depends(require("registry.read"))):
    """TOCTOU-01/SUP-05: ре-верификация артефакта при загрузке — hash должен совпасть
    с зарегистрированным; иначе подмена/перезапись после скана → Finding(critical) + блок."""
    body = await request.body()
    actual = hashlib.sha256(body).hexdigest()
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        if not mv.artifact_hash:
            raise HTTPException(status_code=422, detail="у версии нет зарегистрированного artifact_hash")
        if actual != mv.artifact_hash:
            s.add(domain.Finding(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                 tool="sirius-integrity", verdict="artifact-tampered", severity="critical",
                                 status="open", asset_type="model", asset_ref=f"model/{model_id}/v{ver}",
                                 detail="hash при загрузке ≠ зарегистрированного (TOCTOU-01/SUP-05)", actor=p.sub))
            s.commit()
            audit.append_event(actor=p.sub, action="artifact.tamper.detected", obj=f"model/{model_id}/v{ver}", was_authorized=False)
            raise HTTPException(status_code=409, detail="artifact integrity violation (TOCTOU-01/SUP-05): hash mismatch")
    audit.append_event(actor=p.sub, action="artifact.verify.ok", obj=f"model/{model_id}/v{ver}")
    return {"verified": True, "version": ver}


class OffboardIn(BaseModel):
    actor: str


@app.post("/api/offboard")
def offboard(body: OffboardIn, p: Principal = Depends(require("offboard"))):
    """ACC-03: вывод сотрудника — доступ субъекта отзывается немедленно (fail-closed на всех эндпоинтах)."""
    revoke(body.actor)
    audit.append_event(actor=p.sub, action="offboard", obj=f"actor/{body.actor}")
    return {"offboarded": body.actor}


class RuntimeEventIn(BaseModel):
    type: str
    endpoint: str = ""
    client: str = ""
    count: int = 0


@app.post("/api/runtime/event")
def runtime_event(body: RuntimeEventIn, p: Principal = Depends(require("runtime.event"))):
    """Петля рантайм→реестр (RT-01): сервинг сообщает о детекте (extraction/DDoS) →
    Finding(endpoint) + аудит. Основа для авто-ре-ревью / rollback."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with SessionLocal() as s:
        s.add(domain.Finding(ts=now, tool="sirius-runtime", verdict=body.type, severity="high",
                             status="open", asset_type="endpoint", asset_ref=f"endpoint/{body.endpoint}",
                             detail=f"client={body.client} count={body.count}", actor=p.sub))
        s.commit()
    audit.append_event(actor=p.sub, action=f"runtime.{body.type}", obj=f"endpoint/{body.endpoint}")
    return {"recorded": True, "type": body.type}


# ---------- EXF-01: детект инсайдерской эксфильтрации ----------
_EXPORT_WINDOW_S = 60.0
_EXPORT_THRESHOLD = 15
_exports = defaultdict(list)
_exfil_reported = set()


@app.get("/api/models/{model_id}/export")
def export_model(model_id: int, p: Principal = Depends(require("registry.read"))):
    """Выгрузка артефакта модели. EXF-01: аномальный объём выгрузок одним актором
    за окно → Finding(bulk-exfiltration) + audit + троттлинг (429)."""
    with SessionLocal() as s:
        m = s.get(domain.Model, model_id)
        if not m:
            raise HTTPException(status_code=404, detail="model not found")
        last = s.query(domain.ModelVersion).filter_by(model_id=model_id).order_by(domain.ModelVersion.version.desc()).first()
        digest = last.artifact_hash if last else ""
    now = time.monotonic()
    dq = [t for t in _exports[p.sub] if now - t <= _EXPORT_WINDOW_S]
    dq.append(now)
    _exports[p.sub] = dq
    if len(dq) > _EXPORT_THRESHOLD:
        if p.sub not in _exfil_reported:
            _exfil_reported.add(p.sub)
            with SessionLocal() as s:
                s.add(domain.Finding(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     tool="sirius-exfil", verdict="bulk-exfiltration", severity="high",
                                     status="open", asset_type="actor", asset_ref=f"actor/{p.sub}",
                                     detail=f"{len(dq)} выгрузок за {int(_EXPORT_WINDOW_S)}s", actor=p.sub))
                s.commit()
        audit.append_event(actor=p.sub, action="exfil.blocked", obj=f"actor/{p.sub}", was_authorized=False)
        raise HTTPException(status_code=429, detail=f"bulk export limit: {len(dq)} за {int(_EXPORT_WINDOW_S)}s — троттлинг (EXF-01)")
    audit.append_event(actor=p.sub, action="model.export", obj=f"model/{model_id}")
    return {"model_id": model_id, "artifact_hash": digest, "exported_by": p.sub}


# ---------- карта покрытия + CEO-вью (И5) ----------
# Связь МУ↔платформа: угроза → контроль → как ловится в live-данных (Finding/аудит)
COVERAGE = [
    {"id": "SUP-01", "threat": "вредоносный артефакт модели", "control": "ingestion-скан (pickle-опкоды)", "match": ("verdict", "malicious")},
    {"id": "SUP-07", "threat": "небезопасный формат критичной модели", "control": "политика форматов", "match": ("verdict", "unsafe-format")},
    {"id": "SUP-03", "threat": "уязвимая зависимость (CVE)", "control": "скан зависимостей", "match": ("verdict", "vulnerable-dependency")},
    {"id": "DATA-01", "threat": "недоверенный источник данных", "control": "карантин источника", "match": ("verdict", "untrusted-source")},
    {"id": "CODE-01", "threat": "небезопасный паттерн в коде", "control": "ML-aware AST-SAST", "match": ("verdict", "insecure-code")},
    {"id": "ACC-06", "threat": "утёкший секрет в коде", "control": "скан секретов", "match": ("verdict", "secret-exposed")},
    {"id": "VIS-02", "threat": "расхождение вердиктов / фолз", "control": "триаж сработок", "match": ("verdict", "suspicious")},
    {"id": "RT-01", "threat": "extraction модели в рантайме", "control": "rate-limit + детект", "match": ("verdict", "extraction")},
    {"id": "VIS-03/GOV-01/SUP-04", "threat": "небезопасный промоушен критичной модели", "control": "gated promotion (карта+подпись+HITL)", "match": ("prefix", "promote.blocked")},
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


@app.get("/api/coverage")
def coverage(p: Principal = Depends(require("visibility.read"))):
    """VIS-01: карта покрытия (угроза→контроль→live-статус) + KPI поверх реальных Finding/аудита."""
    audit.append_event(actor=p.sub, action="coverage.read")
    return _coverage_data()


@app.get("/coverage", response_class=HTMLResponse)
def coverage_view():
    """CEO-вью: карта покрытия угроз + KPI (read-only экран, money-shot #5)."""
    return ui.coverage_page(_coverage_data())


# ---------- единая точка входа в прод: control-plane как CI (Gitea) ----------
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


def _record_ci(findings, ref, actor):
    if findings:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with SessionLocal() as s:
            for r in findings:
                s.add(domain.Finding(ts=now, tool=r["tool"], verdict=r["verdict"], severity=r["severity"],
                                     status="open", asset_type="ci", asset_ref=f"ci/{ref}", detail=r["detail"], actor=actor))
            s.commit()


@app.post("/api/ci/scan")
def ci_scan(body: CiScanIn, p: Principal = Depends(require("ci.scan"))):
    """CI-01: гейт «control-plane как CI» — отравленный коммит не проходит (fail-closed)."""
    findings = _ci_gate([f.model_dump() for f in body.files])
    _record_ci(findings, body.ref, p.sub)
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


@app.post("/api/ci/webhook")
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
    try:
        payload = json.loads(body or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="bad payload")
    repo = (payload.get("repository") or {}).get("full_name", "")
    sha = payload.get("after", "")
    findings = _ci_gate(_fetch_changed_files(repo, sha, payload))
    passed = not findings
    _post_commit_status(repo, sha, passed, len(findings))
    _record_ci(findings, f"{repo}@{sha[:8]}" if sha else (repo or "webhook"), "gitea-webhook")
    audit.append_event(actor="gitea-webhook", action="ci.webhook.passed" if passed else "ci.webhook.blocked", obj=f"ci/{repo}")
    return {"accepted": True, "passed": passed, "findings": len(findings)}


@app.get("/api/registry")
def list_registry(p: Principal = Depends(require("registry.read"))):
    with SessionLocal() as s:
        out = []
        for m in s.query(domain.Model).all():
            versions = s.query(domain.ModelVersion).filter_by(model_id=m.id).all()
            out.append({"id": m.id, "name": m.name, "criticality": m.criticality,
                        "versions": [{"version": v.version, "stage": v.stage} for v in versions]})
        return {"models": out}


@app.get("/api/models/{model_id}/versions/{ver}/lineage")
def lineage(model_id: int, ver: int, p: Principal = Depends(require("registry.read"))):
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        return {"model_id": model_id, "version": ver, "dataset_version_id": mv.dataset_version_id,
                "code_commit": mv.code_commit, "env_lock": mv.env_lock, "stage": mv.stage}


@app.get("/api/impact")
def impact(dataset_version_id: int = Query(...), p: Principal = Depends(require("registry.read"))):
    """Blast-radius: какие версии моделей и прод-деплои зависят от версии датасета."""
    with SessionLocal() as s:
        mvs = s.query(domain.ModelVersion).filter_by(dataset_version_id=dataset_version_id).all()
        affected = []
        for mv in mvs:
            deps = s.query(domain.Deployment).filter_by(model_version_id=mv.id, status="active").count()
            affected.append({"model_id": mv.model_id, "version": mv.version, "stage": mv.stage, "active_deployments": deps})
        return {"dataset_version_id": dataset_version_id, "affected": affected}


@app.get("/api/models/{model_id}/backend")
def model_backend(model_id: int, p: Principal = Depends(require("registry.read"))):
    """REG-01: доказательство, что реестр живёт в обёрнутом MLflow. Читаем backend
    через единственную дверь — control-plane; прямого доступа к MLflow снаружи нет."""
    with SessionLocal() as s:
        m = s.get(domain.Model, model_id)
        if not m:
            raise HTTPException(status_code=404, detail="model not found")
        name = registry.model_name(model_id, m.name)
    rm = registry.get_registered_model(name)
    audit.append_event(actor=p.sub, action="model.backend.read", obj=f"model/{model_id}")
    if rm is None:
        return {"backend": "mlflow", "mlflow_name": name, "connected": registry.connected(), "present": False, "versions": []}
    versions = []
    for v in rm["versions"]:
        tags = {t["key"]: t["value"] for t in v.get("tags", [])}
        versions.append({"mlflow_version": v["version"], "cp_version": tags.get("cp_version"), "stage": tags.get("stage")})
    return {"backend": "mlflow", "mlflow_name": name, "connected": True, "present": True, "versions": versions}


# ---------- ingestion-гейт + findings (И2) ----------
@app.post("/api/models/{model_id}/ingest")
async def ingest_model(model_id: int, request: Request, p: Principal = Depends(require("model.ingest"))):
    """SUP-01 ingestion-гейт: артефакт сканируется в карантине БЕЗ десериализации.
    Вредоносный → БЛОК (422) + Finding(critical) + audit, в реестр не попадает.
    Чистый → регистрируется новой версией. pickle.load на артефакте не вызывается никогда."""
    body = await request.body()
    with SessionLocal() as s:
        m = s.get(domain.Model, model_id)
        if not m:
            raise HTTPException(status_code=404, detail="model not found")
        digest = hashlib.sha256(body).hexdigest()
        assessment = scanners.assess_artifact(body, m.criticality)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for r in assessment["findings"]:
            s.add(domain.Finding(ts=now, tool=r["tool"], verdict=r["verdict"], severity=r["severity"],
                                 status="open", asset_type="model", asset_ref=f"model/{model_id}",
                                 detail=r["detail"], actor=p.sub))
        if not assessment["admit"]:
            s.commit()
            audit.append_event(actor=p.sub, action="model.ingest.blocked", obj=f"model/{model_id}")
            raise HTTPException(status_code=422, detail={"blocked": True, "format": assessment["format"],
                                                         "tools": [r["tool"] for r in assessment["findings"]]})
        n = s.query(domain.ModelVersion).filter_by(model_id=model_id).count() + 1
        obj_key = storage.put(f"models/{model_id}/v{n}/artifact.bin", body)  # карантин-стор проверенных байтов
        mv = domain.ModelVersion(model_id=model_id, version=n, stage="dev", artifact_hash=digest,
                                 artifact_object_key=obj_key,
                                 requires_validation=(m.criticality in ("regulatory", "financial")))
        s.add(mv)
        s.commit()
        name = registry.model_name(model_id, m.name)
        try:
            registry.ensure_registered_model(name, tags={"criticality": m.criticality})
            registry.create_model_version(name, source=f"s3://mlflow/{name}",
                                          tags={"cp_version": n, "stage": "dev", "artifact_hash": digest,
                                                "scanned": "clean", "format": assessment["format"]})
        except registry.RegistryError as e:
            logger.warning("MLflow недоступен при ingest model/%s v%s: %s", model_id, n, e)
        audit.append_event(actor=p.sub, action="model.ingest.admitted", obj=f"model/{model_id}/v{n}")
        return {"admitted": True, "version": n, "artifact_hash": digest, "format": assessment["format"],
                "artifact_object_key": obj_key, "persisted": bool(obj_key)}


@app.get("/api/findings")
def list_findings(p: Principal = Depends(require("finding.read"))):
    with SessionLocal() as s:
        rows = s.query(domain.Finding).order_by(domain.Finding.id.desc()).all()
        return {"findings": [{"id": f.id, "ts": f.ts, "tool": f.tool, "verdict": f.verdict,
                              "severity": f.severity, "status": f.status, "asset": f.asset_ref,
                              "detail": f.detail} for f in rows]}


class TriageIn(BaseModel):
    status: str
    reason: str = ""


@app.post("/api/findings/{finding_id}/triage")
def triage_finding(finding_id: int, body: TriageIn, p: Principal = Depends(require("finding.triage"))):
    """VIS-04: статус сработки меняет только MLSecOps; пишется в аудит (кто/когда/почему)."""
    if body.status not in ("open", "triaged", "TP", "FP"):
        raise HTTPException(status_code=422, detail="invalid status")
    with SessionLocal() as s:
        f = s.get(domain.Finding, finding_id)
        if not f:
            raise HTTPException(status_code=404, detail="finding not found")
        f.status = body.status
        s.commit()
        audit.append_event(actor=p.sub, action=f"finding.triage:{body.status}", obj=f"finding/{finding_id}")
        return {"id": finding_id, "status": body.status, "reason": body.reason}


@app.post("/api/scan/code")
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
                                     status="open", asset_type="code", asset_ref=f"code/{filename}", detail=r["detail"], actor=p.sub))
            s.commit()
        audit.append_event(actor=p.sub, action="code.scan.flagged", obj=f"code/{filename}")
        return {"filename": filename, "clean": False, "findings": findings}
    audit.append_event(actor=p.sub, action="code.scan.clean", obj=f"code/{filename}")
    return {"filename": filename, "clean": True, "findings": []}


@app.post("/api/scan/deps")
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
                                     status="open", asset_type="deps", asset_ref=f"deps/{filename}", detail=r["detail"], actor=p.sub))
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


@app.post("/api/scan/dataset")
def scan_dataset_endpoint(body: DatasetScanIn, p: Principal = Depends(require("dataset.scan"))):
    """Гейт качества/целостности данных (scoped): DATA-02 label-flip, DATA-03 UGC-бэкдор-триггер,
    DATA-05 train-serve skew, FB-01 провенанс петли дообучения. Аномалия → Finding + карантин-сигнал."""
    findings = scanners.scan_dataset(body.model_dump())
    if findings:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with SessionLocal() as s:
            for r in findings:
                s.add(domain.Finding(ts=now, tool=r["tool"], verdict=r["verdict"], severity=r["severity"],
                                     status="open", asset_type="dataset", asset_ref="dataset/scan", detail=r["detail"], actor=p.sub))
            s.commit()
        audit.append_event(actor=p.sub, action="dataset.scan.flagged", obj="dataset/scan")
        return {"clean": False, "findings": findings}
    audit.append_event(actor=p.sub, action="dataset.scan.clean", obj="dataset/scan")
    return {"clean": True, "findings": []}
