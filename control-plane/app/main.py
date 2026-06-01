"""Sirius Argus — Control Plane.

Единственная точка входа для людей: health, дашборд с аудит-таймлайном, защищённый
реестр (датасеты/модели/версии) с zero-trust RBAC, lineage и анализом blast-radius.
AuthN — fail-closed (auth.py). Каждое действие и каждый отказ доступа — в аудит.
"""
import hashlib
import logging
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from . import audit, bus, domain, logging_setup, registry, scanners
from .auth import Principal, get_principal
from .db import SessionLocal, init_db
from .rbac import can_read_sensitivity, require

logger = logging.getLogger("sirius")

app = FastAPI(title="Sirius Argus — Control Plane")


@app.on_event("startup")
def _startup():
    logging_setup.setup_logging()
    init_db()


@app.middleware("http")
async def audit_denied(request: Request, call_next):
    logger.info("req %s %s auth=%s", request.method, request.url.path, request.headers.get("authorization", "-"))
    resp = await call_next(request)
    if request.url.path.startswith("/api/") and resp.status_code in (401, 403):
        audit.append_event(actor="anonymous", action="access.denied", obj=request.url.path, was_authorized=False)
    return resp


# ---------- health & dashboard ----------
@app.get("/health")
def health():
    return {"status": "ok", "service": "control-plane", "audit_chain_ok": audit.verify_chain(),
            "bus": {"connected": bus.connected(), "events": bus.stream_len()},
            "mlflow": {"configured": registry.configured(), "connected": registry.connected()}}


@app.get("/", response_class=HTMLResponse)
def dashboard():
    rows = "".join(
        f"<tr><td>{e.ts}</td><td>{e.actor}</td><td>{e.action}</td>"
        f"<td>{e.obj}</td><td>{'ok' if e.was_authorized else 'DENIED'}</td></tr>"
        for e in audit.recent()
    )
    return (
        "<html><head><title>Sirius Argus</title></head><body>"
        "<h1>Sirius Argus — Control Plane</h1>"
        "<p>Реестр + zero-trust RBAC + аудит (append-only, hash-chain).</p>"
        "<table border='1' cellpadding='4'><tr>"
        "<th>ts</th><th>actor</th><th>action</th><th>object</th><th>authz</th></tr>"
        f"{rows}</table></body></html>"
    )


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
        # MON-02: невоспроизводимое не пускаем в прод (fail-closed)
        missing = [f for f in ("dataset_version_id", "code_commit", "env_lock") if not getattr(mv, f)]
        if missing:
            audit.append_event(actor=p.sub, action="promote.blocked", obj=f"model/{model_id}/v{ver}", was_authorized=False)
            raise HTTPException(status_code=422, detail=f"not reproducible, missing: {missing}")
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
        mv = domain.ModelVersion(model_id=model_id, version=n, stage="dev", artifact_hash=digest,
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
        return {"admitted": True, "version": n, "artifact_hash": digest, "format": assessment["format"]}


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
