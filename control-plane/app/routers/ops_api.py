"""Sirius Argus — роутер: ops API (whoami, runtime-события, findings/триаж)."""
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


@router.get("/api/whoami")
def whoami(p: Principal = Depends(get_principal)):
    audit.append_event(actor=p.sub, action="api.whoami")
    return {"sub": p.sub, "roles": sorted(p.roles)}


class RuntimeEventIn(BaseModel):
    type: str
    endpoint: str = ""
    client: str = ""
    count: int = 0


@router.post("/api/runtime/event")
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


@router.get("/api/findings")
def list_findings(p: Principal = Depends(require("finding.read"))):
    with SessionLocal() as s:
        rows = s.query(domain.Finding).order_by(domain.Finding.id.desc()).all()
        return {"findings": [{"id": f.id, "ts": f.ts, "tool": f.tool, "verdict": f.verdict,
                              "severity": f.severity, "status": f.status, "asset": f.asset_ref,
                              "detail": f.detail} for f in rows]}


class TriageIn(BaseModel):
    status: str
    reason: str = ""


@router.post("/api/findings/{finding_id}/triage")
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
