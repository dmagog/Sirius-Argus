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
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
import requests
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest
from pydantic import BaseModel

from . import vault
vault.hydrate_env()  # подтянуть секреты из Vault в env ДО импорта signing/auth (фолбэк — env-дефолты)

from . import audit, bus, domain, logging_setup, mapnodes, registry, scanners, signing, storage, ui
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

# Защита от resource-exhaustion: тело запроса больше лимита → 413 (не читаем в память).
MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(25 * 1024 * 1024)))


@app.on_event("startup")
def _startup():
    logging_setup.setup_logging()
    init_db()
    audit.append_event(actor="control-plane", action=f"secrets.loaded.{vault.source()}",
                       obj=("vault" if vault.connected() else "env"))  # CRED-02: источник секретов в аудит


@app.middleware("http")
async def observe_and_audit(request: Request, call_next):
    if request.url.path not in ("/metrics", "/health"):
        logger.info("req %s %s auth=%s", request.method, request.url.path, request.headers.get("authorization", "-"))
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > MAX_UPLOAD_BYTES:  # resource-exhaustion guard: не читаем огромное тело
        try:
            with SessionLocal() as s:
                s.add(domain.Finding(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     tool="sirius-ingress", verdict="oversized-upload", severity="medium", status="open",
                                     asset_type="endpoint", asset_ref=f"endpoint{request.url.path}",
                                     detail=f"тело {int(cl)} Б > лимита {MAX_UPLOAD_BYTES} Б — защита от resource-exhaustion (DoS)",
                                     actor="anonymous", role=""))
                s.commit()
        except Exception:
            pass
        audit.append_event(actor="anonymous", action="upload.oversized.blocked", obj=request.url.path, was_authorized=False)
        _REQS.labels(status="413").inc()
        return JSONResponse(status_code=413, content={"detail": f"payload too large: {int(cl)} > {MAX_UPLOAD_BYTES} bytes (resource-exhaustion guard)"})
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
            "mlflow": {"configured": registry.configured(), "connected": registry.connected()},
            "vault": {"connected": vault.connected(), "secrets_source": vault.source()}}


@app.get("/metrics")
def metrics():
    """Prometheus-метрики (scrape во внутренней сети, наружу не публикуется)."""
    with SessionLocal() as s:
        _FINDINGS_G.set(s.query(domain.Finding).count())
    _AUDIT_OK_G.set(1 if audit.verify_chain() else 0)
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ---------- роутеры (вынесены из main.py) ----------
from .routers import ci_scans_api, ops_api, pages, registry_api
app.include_router(pages.router)
app.include_router(registry_api.router)
app.include_router(ops_api.router)
app.include_router(ci_scans_api.router)
