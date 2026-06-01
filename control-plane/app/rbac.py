"""Zero-trust RBAC: матрица «действие → роли» + object-level авторизация.

Keycloak даёт роль (authN), а право на конкретный объект решаем здесь (ESC-01/IDOR).
Любой отказ — 403 + запись в аудит.
"""
from fastapi import Depends, HTTPException

from . import audit
from .auth import Principal, get_principal

PERMISSIONS = {
    "dataset.create": {"DE", "MLSecOps"},
    "model.register": {"DS"},
    "model.version": {"DS"},
    "model.promote": {"MLSecOps"},
    "model.approve": {"MLSecOps"},
    "runtime.event": {"MLSecOps"},
    "decommission": {"MLSecOps"},
    "model.ingest": {"DS", "MLSecOps"},
    "code.scan": {"DS", "DE", "MLSecOps"},
    "finding.read": {"DS", "DE", "MLSecOps", "Product", "CEO"},
    "finding.triage": {"MLSecOps"},
    "registry.read": {"DS", "DE", "MLSecOps", "Product", "CEO"},
    "visibility.read": {"DS", "DE", "MLSecOps", "Product", "CEO"},
}

# Допуск к данным по чувствительности (object-level, ACC-04)
SENSITIVITY_CLEARANCE = {
    "open": {"DS", "DE", "MLSecOps", "Product", "CEO"},
    "pii": {"DE", "MLSecOps"},
    "secret": {"MLSecOps"},
}


def require(action: str):
    """Зависимость: пускает, только если у актора есть роль для действия (иначе 403 + аудит)."""
    def _dep(p: Principal = Depends(get_principal)) -> Principal:
        if not (p.roles & PERMISSIONS.get(action, set())):
            audit.append_event(actor=p.sub, action=f"authz.deny:{action}", was_authorized=False)
            raise HTTPException(status_code=403, detail=f"role not permitted for {action}")
        return p
    return _dep


def can_read_sensitivity(roles, sensitivity: str) -> bool:
    return bool(set(roles) & SENSITIVITY_CLEARANCE.get(sensitivity, {"MLSecOps"}))
