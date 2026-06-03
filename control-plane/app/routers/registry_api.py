"""Sirius Argus — роутер: реестр (датасеты/модели/версии/промоушен/подпись/ingest)."""
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

from .. import audit, bus, decisions, domain, mapnodes, registry, scanners, signing, storage, ui
from ..auth import Principal, get_principal, revoke
from ..db import AuditEvent, SessionLocal
from ..rbac import PERMISSIONS, can_read_sensitivity, require

logger = logging.getLogger("sirius")
router = APIRouter()


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


TRUSTED_SOURCE_PREFIXES = ("internal://", "curated://", "trusted:", "s3://sirius-")


def _is_trusted_source(src: str) -> bool:
    return bool(src) and src.startswith(TRUSTED_SOURCE_PREFIXES)


@router.post("/api/datasets")
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
                                 detail=f"источник '{body.source or '—'}' не в доверенном списке → карантин",
                                 actor=p.sub, role=p.primary_role()))
        s.commit()
        audit.append_event(actor=p.sub, action=f"dataset.create:{status}", obj=f"dataset/{ds.id}")
        return {"dataset_id": ds.id, "dataset_version_id": dv.id, "sensitivity": ds.sensitivity, "status": status}


@router.get("/api/datasets/{ds_id}")
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


@router.get("/api/datasets/{ds_id}/schema")
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


@router.post("/api/models")
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


@router.post("/api/models/{model_id}/versions")
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
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
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


def _valid_risk_acceptance(s, ref: str):
    """Действующее (непросроченное) принятие риска для объекта или None."""
    now = datetime.now(timezone.utc)
    for ra in s.query(domain.RiskAcceptance).filter_by(ref=ref, active=True).all():
        if ra.expires_at:
            try:
                exp = datetime.fromisoformat(ra.expires_at)
                exp = exp.replace(tzinfo=timezone.utc) if exp.tzinfo is None else exp
                if exp < now:
                    continue  # просрочено → невалидно
            except ValueError:
                continue
        return ra
    return None


@router.post("/api/models/{model_id}/versions/{ver}/promote")
def promote(model_id: int, ver: int, p: Principal = Depends(require("model.promote"))):
    with SessionLocal() as s:
        # FOR UPDATE: блокируем строку версии на время гейта — сериализует одновременные
        # промоушены, закрывает TOCTOU-гонку (GOV-03). Postgres — row-lock; SQLite — no-op (БД-wide lock).
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).with_for_update().first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        if mv.stage == "retired":  # RB-01: откат на изъятую/уязвимую версию запрещён
            audit.append_event(actor=p.sub, action="promote.blocked.retired", obj=f"model/{model_id}/v{ver}", was_authorized=False)
            raise HTTPException(status_code=409, detail="version retired — rollback to a withdrawn/vulnerable version is blocked (RB-01)")
        if mv.stage == "prod":  # state-machine: dev→prod однократно, без повторного активного деплоя (GOV-03)
            audit.append_event(actor=p.sub, action="promote.blocked.already-prod", obj=f"model/{model_id}/v{ver}", was_authorized=False)
            raise HTTPException(status_code=409, detail="version already in prod — повторный промоушен не требуется (GOV-03)")
        # MON-02: невоспроизводимое не пускаем в прод (fail-closed)
        missing = [f for f in ("dataset_version_id", "code_commit", "env_lock") if not getattr(mv, f)]
        if missing:
            audit.append_event(actor=p.sub, action="promote.blocked", obj=f"model/{model_id}/v{ver}", was_authorized=False)
            raise HTTPException(status_code=422, detail=f"not reproducible, missing: {missing}")
        # open-critical gate: незакрытые critical-сработки на ЭТОЙ версии блокируют промоушен —
        # кроме явного принятия риска уполномоченной ролью (GRC exception, см. /api/risk-acceptance)
        crit = s.query(domain.Finding).filter(
            domain.Finding.asset_ref == f"model/{model_id}/v{ver}",
            domain.Finding.status == "open", domain.Finding.severity == "critical").count()
        risk_accepted = False
        if crit:
            if not _valid_risk_acceptance(s, f"model/{model_id}/v{ver}"):
                audit.append_event(actor=p.sub, action="promote.blocked.open-critical", obj=f"model/{model_id}/v{ver}", was_authorized=False)
                raise HTTPException(status_code=422, detail=f"{crit} незакрытая(ых) critical-сработка(ок) на версии — закрыть или оформить принятие риска (risk.accept)")
            risk_accepted = True
        # policy-матрица для критичных моделей (regulatory/financial): модель-карта + подпись + HITL
        if mv.requires_validation:
            if not (mv.intended_use and mv.limitations):  # GOV-01: полнота модель-карты
                audit.append_event(actor=p.sub, action="promote.blocked.modelcard", obj=f"model/{model_id}/v{ver}", was_authorized=False)
                raise HTTPException(status_code=422, detail="incomplete model card (GOV-01): need intended_use + limitations")
            art_bytes = storage.get(mv.artifact_object_key) if mv.artifact_object_key else None
            if not signing.verify(model_id, ver, mv.artifact_hash or "", mv.signature_bundle or "", art_bytes):  # SUP-04: model-signing над реальным артефактом (admission/verify-on-consume)
                audit.append_event(actor=p.sub, action="promote.blocked.unsigned", obj=f"model/{model_id}/v{ver}", was_authorized=False)
                raise HTTPException(status_code=422, detail="unsigned or invalid signature (SUP-04)")
            # стоящее решение по текущему артефакту: если последнее — reject, промоушен закрыт,
            # пока его не сменит новый аппрув (у отклонения есть «зубы», а не просто запись).
            standing = (s.query(domain.Approval)
                        .filter(domain.Approval.model_version_id == mv.id,
                                domain.Approval.artifact_hash == (mv.artifact_hash or ""))
                        .order_by(domain.Approval.id.desc()).first())
            if standing is not None and standing.decision == "reject":
                audit.append_event(actor=p.sub, action="promote.blocked.rejected", obj=f"model/{model_id}/v{ver}", was_authorized=False)
                raise HTTPException(status_code=422, detail="version rejected by HITL — supersede with a new approval before promotion")
            # VIS-03 (HITL) + ACC-02 (separation of duties): нужен АППРУВ от ДРУГОГО MLSecOps
            others = s.query(domain.Approval).filter(
                domain.Approval.model_version_id == mv.id,
                domain.Approval.approver != p.sub,
                domain.Approval.decision == "approve",
                domain.Approval.artifact_hash == (mv.artifact_hash or "")).count()  # решение привязано к hash (anti-TOCTOU)
            if not others:
                audit.append_event(actor=p.sub, action="promote.blocked.hitl", obj=f"model/{model_id}/v{ver}", was_authorized=False)
                raise HTTPException(status_code=422, detail="HITL approval by a different MLSecOps, bound to current artifact hash, required (VIS-03/ACC-02)")
        mv.stage = "prod"
        mv.promoted_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        # без дубль-деплоя: один активный Deployment на версию (belt-and-suspenders к FOR UPDATE)
        if not s.query(domain.Deployment).filter_by(model_version_id=mv.id, status="active").first():
            s.add(domain.Deployment(model_version_id=mv.id, status="active"))  # активен; «conditional» — в аудите/ответе
        mvid = mv.id  # фиксируем id/имя ДО commit, не полагаемся на состояние объекта после коммита
        m = s.get(domain.Model, model_id)
        name = registry.model_name(model_id, m.name)
        s.commit()
        # отражаем стадию в MLflow по нашему cp_version (fail-soft); рассинхрон фиксируем в аудит
        try:
            mlflow_ver = registry.find_version_by_cp(name, ver)
            if mlflow_ver is not None:
                registry.set_version_tag(name, mlflow_ver, "stage", "prod")
        except registry.RegistryError as e:
            logger.warning("MLflow недоступен при промоуте model/%s v%s: %s", model_id, ver, e)
            audit.append_event(actor="system", action="mlflow.sync.failed", obj=f"model/{model_id}/v{ver}")
        audit.append_event(actor=p.sub, action=("model.promote.risk-accepted" if risk_accepted else "model.promote"),
                            obj=f"model/{model_id}/v{ver}")
        return {"model_version_id": mvid, "stage": "prod", "conditional": risk_accepted}


class ApproveIn(BaseModel):
    reason: str = ""


@router.post("/api/models/{model_id}/versions/{ver}/approve")
def approve_version(model_id: int, ver: int, body: ApproveIn, p: Principal = Depends(require("model.approve"))):
    """VIS-03 HITL: критичную версию вручную одобряет MLSecOps перед промоушеном."""
    artifact_hash = decisions.record_decision(model_id, ver, p.sub, "approve", body.reason)
    return {"approved": True, "version": ver, "approver": p.sub, "artifact_hash": artifact_hash}


@router.post("/api/models/{model_id}/versions/{ver}/reject")
def reject_version(model_id: int, ver: int, body: ApproveIn, p: Principal = Depends(require("model.approve"))):
    """VIS-03 HITL: MLSecOps отклоняет критичную версию (с обязательным обоснованием).
    Решение фиксируется в аудит и блокирует промоушен, пока его не сменит новый аппрув по
    тому же артефакту (promote.blocked.rejected)."""
    artifact_hash = decisions.record_decision(model_id, ver, p.sub, "reject", body.reason)
    return {"rejected": True, "version": ver, "approver": p.sub, "artifact_hash": artifact_hash}


@router.get("/api/models/{model_id}/versions/{ver}/review")
def review_bundle(model_id: int, ver: int, p: Principal = Depends(require("finding.read"))):
    """Evidence-based HITL: всё для информированного решения аппрувера — сработки, модель-карта,
    lineage/воспроизводимость, статус подписи, аппрувы. Не «слепой аппрув», а решение по доказательствам."""
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        m = s.get(domain.Model, model_id)
        findings = s.query(domain.Finding).filter(domain.Finding.asset_ref.like(f"model/{model_id}%")).all()
        approvals = s.query(domain.Approval).filter_by(model_version_id=mv.id).all()
        reproducible = all(getattr(mv, f) for f in ("dataset_version_id", "code_commit", "env_lock"))
        open_critical = sum(1 for f in findings if f.status == "open" and f.severity == "critical")
        audit.append_event(actor=p.sub, action="model.review.read", obj=f"model/{model_id}/v{ver}")
        return {
            "model": m.name, "version": ver, "stage": mv.stage, "criticality": m.criticality,
            "artifact_hash": mv.artifact_hash, "persisted": bool(mv.artifact_object_key),
            "model_card": {"intended_use": mv.intended_use, "limitations": mv.limitations,
                           "complete": bool(mv.intended_use and mv.limitations)},
            "lineage": {"dataset_version_id": mv.dataset_version_id, "code_commit": mv.code_commit,
                        "env_lock": mv.env_lock, "reproducible": reproducible},
            "signature": {"signed": bool(mv.signature_bundle), "tool": mv.signature or None},
            "open_critical": open_critical,
            "findings": [{"tool": f.tool, "verdict": f.verdict, "severity": f.severity, "status": f.status} for f in findings],
            "approvals": [{"approver": a.approver, "decision": (a.decision or "approve"), "ts": a.ts,
                           "reason": a.reason, "artifact_hash": a.artifact_hash} for a in approvals],
        }


class RiskAcceptanceIn(BaseModel):
    scope: str = "version"
    ref: str
    justification: str
    conditions: str = ""
    expires_at: str = ""


@router.post("/api/risk-acceptance")
def accept_risk(body: RiskAcceptanceIn, p: Principal = Depends(require("risk.accept"))):
    """GRC exception: уполномоченная старшая роль (CEO) формально принимает остаточный риск /
    проваленный контроль — с обоснованием, условиями и сроком. Промоушен при проваленном
    open-critical гейте проходит только при валидном непросроченном принятии → деплой
    помечается risk-accepted (conditional). Всё в аудит, отдельно от того, кто промоутит."""
    if not body.justification:
        raise HTTPException(status_code=422, detail="justification required")
    with SessionLocal() as s:
        ra = domain.RiskAcceptance(scope=body.scope, ref=body.ref, accepted_by=p.sub,
                                   justification=body.justification, conditions=body.conditions, expires_at=body.expires_at,
                                   ts=datetime.now(timezone.utc).isoformat(timespec="seconds"), active=True)
        s.add(ra)
        s.commit()
        rid = ra.id
    audit.append_event(actor=p.sub, action="risk.accept", obj=body.ref)
    return {"accepted": True, "id": rid, "ref": body.ref, "conditions": body.conditions, "expires_at": body.expires_at}


@router.post("/api/models/{model_id}/versions/{ver}/retire")
def retire_version(model_id: int, ver: int, p: Principal = Depends(require("decommission"))):
    """Вывод версии из эксплуатации: снимает активные деплои и помечает retired.
    После этого откат на неё в прод запрещён (RB-01)."""
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        mv.stage = "retired"
        mv.retired_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        for d in s.query(domain.Deployment).filter_by(model_version_id=mv.id, status="active").all():
            d.status = "retired"
        s.commit()
        audit.append_event(actor=p.sub, action="model.retire", obj=f"model/{model_id}/v{ver}")
        return {"version": ver, "stage": "retired"}


@router.post("/api/models/{model_id}/versions/{ver}/sign")
def sign_version(model_id: int, ver: int, p: Principal = Depends(require("model.sign"))):
    """SUP-04 (ADR-0006): подпись версии через OpenSSF model-signing (офлайн-ключ) над
    РЕАЛЬНЫМ артефактом из карантин-стора (или манифестом, если байты не сохранены).
    Без валидной подписи промоушен критичной модели не проходит (admission-control)."""
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        art_bytes = storage.get(mv.artifact_object_key) if mv.artifact_object_key else None
        mv.signature_bundle = signing.sign(model_id, ver, mv.artifact_hash or "", art_bytes)  # подпись реальных байтов (или манифеста, если артефакт не сохранён)
        mv.signature = "model-signing/" + ("artifact" if art_bytes else "manifest")
        s.commit()
        audit.append_event(actor=p.sub, action="model.sign", obj=f"model/{model_id}/v{ver}")
        return {"signed": True, "version": ver, "tool": "model-signing", "over": "artifact" if art_bytes else "manifest"}


@router.post("/api/models/{model_id}/versions/{ver}/verify-artifact")
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
                                 detail="hash при загрузке ≠ зарегистрированного (TOCTOU-01/SUP-05)",
                                 actor=p.sub, role=p.primary_role()))
            s.commit()
            audit.append_event(actor=p.sub, action="artifact.tamper.detected", obj=f"model/{model_id}/v{ver}", was_authorized=False)
            raise HTTPException(status_code=409, detail="artifact integrity violation (TOCTOU-01/SUP-05): hash mismatch")
    audit.append_event(actor=p.sub, action="artifact.verify.ok", obj=f"model/{model_id}/v{ver}")
    return {"verified": True, "version": ver}


@router.post("/api/prod/verify-signatures")
def verify_prod_signatures(p: Principal = Depends(require("prod.verify"))):
    """MON-05 — непрерывная проверка прода (verify-on-prod): подпись и целостность
    перепроверяются не только на промоушене (admission, SUP-04), но и для версий, УЖЕ
    стоящих в проде. Подмена байтов/реестра после деплоя → Finding(prod-artifact-tampered,
    critical) + audit. Сервер-сайд по сохранённым байтам (storage), без участия клиента.
    Запускается периодически (роль Service) или вручную (MLSecOps)."""
    with SessionLocal() as s:
        items = []
        for d in s.query(domain.Deployment).filter_by(status="active").all():
            mv = s.get(domain.ModelVersion, d.model_version_id)
            if mv and mv.stage == "prod":
                items.append((mv.model_id, mv.version, mv.artifact_hash or "",
                              mv.artifact_object_key, mv.signature_bundle or ""))
    checked, tampered = 0, []
    for model_id, ver, reg_hash, obj_key, sig in items:
        checked += 1
        art_bytes = storage.get(obj_key) if obj_key else None
        reason = ""
        if reg_hash and art_bytes is not None and hashlib.sha256(art_bytes).hexdigest() != reg_hash:
            reason = "sha сохранённого артефакта ≠ зарегистрированного"
        elif sig and not signing.verify(model_id, ver, reg_hash, sig, art_bytes):
            reason = "подпись прод-версии больше не сходится"
        if reason:
            tampered.append({"model_id": model_id, "version": ver, "reason": reason})
            with SessionLocal() as s:
                s.add(domain.Finding(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     tool="sirius-prod-verify", verdict="prod-artifact-tampered", severity="critical",
                                     status="open", asset_type="model", asset_ref=f"model/{model_id}/v{ver}",
                                     detail=f"прод-ре-верификация: {reason} (MON-05)",
                                     actor=p.sub, role=p.primary_role()))
                s.commit()
            audit.append_event(actor=p.sub, action="prod.verify.tampered", obj=f"model/{model_id}/v{ver}", was_authorized=False)
    audit.append_event(actor=p.sub, action="prod.verify.run", obj=f"checked={checked} tampered={len(tampered)}")
    return {"checked": checked, "tampered": tampered}


class OffboardIn(BaseModel):
    actor: str


@router.post("/api/offboard")
def offboard(body: OffboardIn, p: Principal = Depends(require("offboard"))):
    """ACC-03: вывод сотрудника — доступ субъекта отзывается немедленно (fail-closed на всех эндпоинтах)."""
    revoke(body.actor)
    audit.append_event(actor=p.sub, action="offboard", obj=f"actor/{body.actor}")
    return {"offboarded": body.actor}


_EXPORT_WINDOW_S = 60.0


_EXPORT_THRESHOLD = 15


_exports = defaultdict(list)


_exfil_reported = set()


@router.get("/api/models/{model_id}/export")
def export_model(model_id: int, p: Principal = Depends(require("registry.read"))):
    """Выгрузка артефакта модели. EXF-01: аномальный объём выгрузок одним актором
    за окно → Finding(bulk-exfiltration) + audit + троттлинг (429)."""
    with SessionLocal() as s:
        m = s.get(domain.Model, model_id)
        if not m:
            raise HTTPException(status_code=404, detail="model not found")
        last = s.query(domain.ModelVersion).filter_by(model_id=model_id).order_by(domain.ModelVersion.version.desc()).first()
        digest = last.artifact_hash if last else ""
    # EXF-01: счётчик выгрузок в общем Redis (sliding window) — нельзя обойти, размазав
    # запросы по соединениям/воркерам. Фолбэк на in-memory, если Redis недоступен (тогда
    # корректно лишь при одном воркере). Wall-clock time.time() — общий для всех процессов.
    now = time.time()
    count = bus.rate_hit(f"exfil:hits:{p.sub}", _EXPORT_WINDOW_S, now)
    if count is None:  # Redis недоступен → in-memory per-worker фолбэк
        dq = [t for t in _exports[p.sub] if now - t <= _EXPORT_WINDOW_S]
        dq.append(now)
        _exports[p.sub] = dq
        count = len(dq)
    if count > _EXPORT_THRESHOLD:
        first = bus.once(f"exfil:reported:{p.sub}", _EXPORT_WINDOW_S)
        if first is None:  # Redis недоступен → in-memory дедуп сработки
            first = p.sub not in _exfil_reported
            if first:
                _exfil_reported.add(p.sub)
        if first:
            with SessionLocal() as s:
                s.add(domain.Finding(ts=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                                     tool="sirius-exfil", verdict="bulk-exfiltration", severity="high",
                                     status="open", asset_type="actor", asset_ref=f"actor/{p.sub}",
                                     detail=f"{count} выгрузок за {int(_EXPORT_WINDOW_S)}s",
                                     actor=p.sub, role=p.primary_role()))
                s.commit()
        audit.append_event(actor=p.sub, action="exfil.blocked", obj=f"actor/{p.sub}", was_authorized=False)
        raise HTTPException(status_code=429, detail=f"bulk export limit: {count} за {int(_EXPORT_WINDOW_S)}s — троттлинг (EXF-01)")
    audit.append_event(actor=p.sub, action="model.export", obj=f"model/{model_id}")
    return {"model_id": model_id, "artifact_hash": digest, "exported_by": p.sub}


@router.get("/api/registry")
def list_registry(p: Principal = Depends(require("registry.read"))):
    with SessionLocal() as s:
        out = []
        for m in s.query(domain.Model).all():
            versions = s.query(domain.ModelVersion).filter_by(model_id=m.id).all()
            out.append({"id": m.id, "name": m.name, "criticality": m.criticality,
                        "versions": [{"version": v.version, "stage": v.stage} for v in versions]})
        return {"models": out}


@router.get("/api/models/{model_id}/versions/{ver}/lineage")
def lineage(model_id: int, ver: int, p: Principal = Depends(require("registry.read"))):
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(model_id=model_id, version=ver).first()
        if not mv:
            raise HTTPException(status_code=404, detail="version not found")
        return {"model_id": model_id, "version": ver, "dataset_version_id": mv.dataset_version_id,
                "code_commit": mv.code_commit, "env_lock": mv.env_lock, "stage": mv.stage}


@router.get("/api/impact")
def impact(dataset_version_id: int = Query(...), p: Principal = Depends(require("registry.read"))):
    """Blast-radius: какие версии моделей и прод-деплои зависят от версии датасета."""
    with SessionLocal() as s:
        mvs = s.query(domain.ModelVersion).filter_by(dataset_version_id=dataset_version_id).all()
        affected = []
        for mv in mvs:
            deps = s.query(domain.Deployment).filter_by(model_version_id=mv.id, status="active").count()
            affected.append({"model_id": mv.model_id, "version": mv.version, "stage": mv.stage, "active_deployments": deps})
        return {"dataset_version_id": dataset_version_id, "affected": affected}


@router.get("/api/models/{model_id}/backend")
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


@router.post("/api/models/{model_id}/ingest")
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
                                 detail=r["detail"], actor=p.sub, role=p.primary_role()))
        if not assessment["admit"]:
            s.commit()
            audit.append_event(actor=p.sub, action="model.ingest.blocked", obj=f"model/{model_id}")
            raise HTTPException(status_code=422, detail={"blocked": True, "format": assessment["format"],
                                                         "tools": [r["tool"] for r in assessment["findings"]]})
        n = s.query(domain.ModelVersion).filter_by(model_id=model_id).count() + 1
        obj_key = storage.put(f"models/{model_id}/v{n}/artifact.bin", body)  # карантин-стор проверенных байтов
        mv = domain.ModelVersion(model_id=model_id, version=n, stage="dev", artifact_hash=digest,
                                 artifact_object_key=obj_key,
                                 requires_validation=(m.criticality in ("regulatory", "financial")),
                                 created_at=now)
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
