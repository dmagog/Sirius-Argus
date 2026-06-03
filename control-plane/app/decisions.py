"""HITL-решения по версии модели (approve | reject): единый код для API и UI-инспектора.

Запись решения = строка Approval, привязанная к artifact_hash (anti-TOCTOU), + событие
аудита. Право принимать решение — у роли MLSecOps (rbac PERMISSIONS['model.approve']).
Separation of duties (аппрувер ≠ владелец, аппрувер ≠ промоутер) проверяется на
промоушене (registry_api.promote): тот не пройдёт без аппрува ОТ ДРУГОГО MLSecOps,
привязанного к текущему хэшу артефакта, и блокируется, если стоящее решение — reject.
"""
from datetime import datetime, timezone

from fastapi import HTTPException

from . import audit, domain
from .db import SessionLocal

DECISIONS = ("approve", "reject")
# Demo/dev-учётки MLSecOps, от чьего имени принимается решение в инспекторе (у control-plane
# UI нет отдельного логина — SSO живёт у ops-консолей). В проде сюда приходит реальный sub.
UI_APPROVERS = ("mlsecops", "reviewer")


def record_decision(model_id: int, ver: int, approver: str, decision: str, reason: str = "") -> str:
    """Зафиксировать HITL-решение MLSecOps по версии. Возвращает artifact_hash, к которому
    привязано решение. 404 — версии нет; 422 — неизвестное решение или reject без обоснования."""
    if decision not in DECISIONS:
        raise HTTPException(status_code=422, detail="decision must be approve|reject")
    if decision == "reject" and not (reason or "").strip():
        raise HTTPException(status_code=422, detail="reject requires a reason")
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        artifact_hash = mv.artifact_hash or ""
        s.add(domain.Approval(
            model_version_id=mv.id, approver=approver, decision=decision,
            artifact_hash=artifact_hash, reason=reason,
            ts=datetime.now(timezone.utc).isoformat(timespec="seconds")))
        s.commit()
    audit.append_event(actor=approver,
                       action=("model.approve" if decision == "approve" else "model.reject"),
                       obj=f"model/{model_id}/v{ver}")
    return artifact_hash
