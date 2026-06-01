"""Sirius Argus — Control Plane (И0, walking skeleton).

Единственная точка входа для людей: health, дашборд с аудит-таймлайном, защищённый API.
AuthN — fail-closed (auth.py). Каждое действие и каждый отказ доступа — в аудит.
"""
from fastapi import Depends, FastAPI, Request
from fastapi.responses import HTMLResponse

from . import audit
from .auth import Principal, get_principal
from .db import init_db

app = FastAPI(title="Sirius Argus — Control Plane")


@app.on_event("startup")
def _startup():
    init_db()


@app.middleware("http")
async def audit_denied(request: Request, call_next):
    resp = await call_next(request)
    if request.url.path.startswith("/api/") and resp.status_code in (401, 403):
        audit.append_event(actor="anonymous", action="access.denied", obj=request.url.path, was_authorized=False)
    return resp


@app.get("/health")
def health():
    return {"status": "ok", "service": "control-plane", "audit_chain_ok": audit.verify_chain()}


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
        "<p>Walking skeleton (И0). Аудит-таймлайн (append-only, hash-chain):</p>"
        "<table border='1' cellpadding='4'><tr>"
        "<th>ts</th><th>actor</th><th>action</th><th>object</th><th>authz</th></tr>"
        f"{rows}</table></body></html>"
    )


@app.get("/api/whoami")
def whoami(p: Principal = Depends(get_principal)):
    audit.append_event(actor=p.sub, action="api.whoami", was_authorized=True)
    return {"sub": p.sub, "roles": sorted(p.roles)}
