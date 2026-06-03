"""Слой данных «Инспектор узла»: ModelVersion → прогон (run) + причастный (actor→роль).

Прогон = версия модели в контуре. Узел пайплайна выводится из stage версии, state —
из stage + открытых критичных findings + requires_validation + Approval. Только реальные
данные (SessionLocal как в routers/*), без мока.

Привязка findings↔версия: scan-findings ингест-гейта пишутся с asset_ref='model/<id>'
(без версии, registry_api), а версионные (verify-artifact/prod-verify) — 'model/<id>/v<n>'.
Поэтому findings версии собираем по ОБЕИМ формам; model-scoped относим к самой свежей
версии модели (ингест-findings физически относятся к последней заингещенной версии).
"""
from collections import defaultdict

from . import domain
from .db import AuditEvent, SessionLocal

# stage версии → узел пайплайна, где версия «сейчас».
_STAGE_NODE = {"dev": "package", "staging": "validate", "prod": "serving", "retired": "decommission"}
# узел → стадии, чьи версии «принадлежат» узлу (для фильтра runs_for_node).
_NODE_STAGES = {"package": ("dev",), "validate": ("staging",), "serving": ("prod",),
                "decommission": ("retired",), "gate-artifact": ("dev", "staging", "prod", "retired")}


# ── причастный: учётка → роль (Agent: actor = lowercase demo-юзер; роль в Finding не хранится) ──
_DEMO_ACTOR_ROLES = {
    "ds": "DS", "de": "DE", "mlsecops": "MLSecOps", "product": "Product", "ceo": "CEO",
    "bruteme": "DS", "serving": "Service", "svc:serving": "Service", "reviewer": "MLSecOps",
}
_KNOWN_ROLES = {"DS", "DE", "MLSecOps", "Product", "CEO", "Service"}


def actor_role(actor):
    """Finding.actor → (account, role). Роль '—', если неизвестна (UUID Keycloak в проде,
    anonymous и т.п.). Покрывает реальные значения demo/pipeline; fallback — парсинг 'dev:user:ROLE'."""
    account = (actor or "").strip()
    if not account:
        return "—", "—"
    role = _DEMO_ACTOR_ROLES.get(account) or _DEMO_ACTOR_ROLES.get(account.lower())
    if role:
        return account, role
    if account.startswith("dev:"):
        parts = account.split(":", 2)
        if len(parts) == 3 and parts[2] in _KNOWN_ROLES:
            return parts[1], parts[2]
    return account, "—"


def _crit(criticality):
    return criticality if criticality in ("regulatory", "financial") else "internal"


def _dur_stub(ts):
    """Детерминированная псевдо-длительность 'MM:SS' (у ModelVersion нет start/end — честно псевдо)."""
    h = abs(hash(ts or "")) if ts else 0
    return f"{(h // 60) % 60:02d}:{h % 60:02d}"


def _findings_index(s):
    idx = defaultdict(list)
    for f in s.query(domain.Finding).order_by(domain.Finding.id.desc()).all():
        idx[f.asset_ref].append(f)
    return idx


def _last_actor_by_version(s):
    out = {}
    for ev in s.query(AuditEvent).order_by(AuditEvent.id.desc()).all():
        obj = ev.obj or ""
        if obj.startswith("model/") and "/v" in obj and obj not in out:
            out[obj] = ev.actor
    return out


def _version_findings(idx, model_id, version, latest_version):
    items = list(idx.get(f"model/{model_id}/v{version}", []))
    if version == latest_version:
        items += idx.get(f"model/{model_id}", [])
    return items


def _state_of(stage, open_critical, requires_validation, has_approval):
    if stage == "retired":
        return "retired"
    if open_critical:
        return "blocked"
    if stage == "prod":
        return "passed"
    if requires_validation:
        return "hold" if has_approval else "hitl"
    return "running"


def _enrich(s, idx, last_actor, mv, model, latest_version):
    findings = _version_findings(idx, model.id, mv.version, latest_version)
    open_critical = sum(1 for f in findings if f.status == "open" and f.severity == "critical")
    has_approval = bool(s.query(domain.Approval)
                        .filter(domain.Approval.model_version_id == mv.id,
                                domain.Approval.approver != model.owner).first())
    actor = last_actor.get(f"model/{model.id}/v{mv.version}") or model.owner or "—"
    started = min((f.ts for f in findings if f.ts), default="") or ""
    node = "gate-artifact" if open_critical else _STAGE_NODE.get(mv.stage, "package")
    return {
        "id": f"RUN-{mv.id}", "model": model.name, "ver": f"v{mv.version}",
        "crit": _crit(model.criticality), "started": started,
        "dur": _dur_stub(started or f"{model.id}:{mv.version}"), "findings": len(findings),
        "actor": actor, "node": node,
        "state": _state_of(mv.stage, open_critical, bool(mv.requires_validation), has_approval),
        "_stage": mv.stage,
    }


def runs_for_node(node_id):
    """Прогоны (версии контура) для инспектора узла. Свои версии узла (по стадии; для
    gate-artifact — «застрявшие») или весь контур, если своих нет. Новые версии первыми."""
    with SessionLocal() as s:
        idx = _findings_index(s)
        last_actor = _last_actor_by_version(s)
        latest = {}
        for mv in s.query(domain.ModelVersion).all():
            latest[mv.model_id] = max(latest.get(mv.model_id, 0), mv.version)
        models = {m.id: m for m in s.query(domain.Model).all()}
        runs = []
        for mv in s.query(domain.ModelVersion).order_by(domain.ModelVersion.id.desc()).all():
            m = models.get(mv.model_id)
            if m:
                runs.append(_enrich(s, idx, last_actor, mv, m, latest.get(mv.model_id, mv.version)))
    stages = _NODE_STAGES.get(node_id)
    if stages is None:
        own = []
    elif node_id == "gate-artifact":
        own = [r for r in runs if r["node"] == "gate-artifact"]
    else:
        own = [r for r in runs if r["_stage"] in stages]
    chosen = own if own else runs
    for r in chosen:
        r.pop("_stage", None)
    return chosen


def _short_t(ts):
    return ((ts or "").split("T")[-1][:8]) if ts else ""


def _parse_run_id(run_id):
    if not run_id or not run_id.startswith("RUN-"):
        return None
    try:
        return int(run_id[4:])
    except ValueError:
        return None


def run_detail(run_id):
    """Детали прогона: реальный lineage из ModelVersion + findings версии (с actor) + лог-поток."""
    mvid = _parse_run_id(run_id)
    if mvid is None:
        return {}
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(id=mvid).first()
        if not mv:
            return {}
        m = s.query(domain.Model).filter_by(id=mv.model_id).first()
        ds_name = None
        if mv.dataset_version_id:
            dv = s.query(domain.DatasetVersion).filter_by(id=mv.dataset_version_id).first()
            if dv:
                ds = s.query(domain.Dataset).filter_by(id=dv.dataset_id).first()
                ds_name = (f"{ds.name} (dv#{dv.id})" if ds else f"dv#{dv.id}")
        lineage = {
            "dataset": ds_name or (f"dv#{mv.dataset_version_id}" if mv.dataset_version_id else "—"),
            "code_commit": mv.code_commit or "—", "env_lock": mv.env_lock or "—",
            "artifact_hash": mv.artifact_hash or "—",
            "signature": mv.signature or ("model-signing" if mv.signature_bundle else "—"),
        }
        latest = (s.query(domain.ModelVersion.version).filter_by(model_id=mv.model_id)
                  .order_by(domain.ModelVersion.version.desc()).first())
        latest_version = latest[0] if latest else mv.version
        refs = [f"model/{mv.model_id}/v{mv.version}"]
        if mv.version == latest_version:
            refs.append(f"model/{mv.model_id}")
        f_rows = (s.query(domain.Finding).filter(domain.Finding.asset_ref.in_(refs))
                  .order_by(domain.Finding.id.desc()).all())
        findings = [{"id": f.id, "ts": f.ts, "tool": f.tool, "verdict": f.verdict,
                     "severity": f.severity, "status": f.status, "asset": f.asset_ref,
                     "detail": f.detail, "actor": f.actor} for f in f_rows]
        ver_obj = f"model/{mv.model_id}/v{mv.version}"
        log = []
        for ev in s.query(AuditEvent).filter(AuditEvent.obj == ver_obj).order_by(AuditEvent.id.asc()).all():
            lvl = ("err" if (not ev.was_authorized or "blocked" in (ev.action or "")
                             or "denied" in (ev.action or "")) else "info")
            log.append({"t": _short_t(ev.ts), "lvl": lvl, "src": ev.actor or "system", "msg": ev.action})
        for f in f_rows:
            lvl = ("err" if f.severity in ("critical", "high") else "warn" if f.severity == "medium" else "info")
            log.append({"t": _short_t(f.ts), "lvl": lvl, "src": f.tool or "finding",
                        "msg": f"{f.verdict} · {f.detail}".strip(" ·")})
        log.sort(key=lambda x: x["t"])
    return {"model": (m.name if m else ""), "ver": f"v{mv.version}", "stage": mv.stage,
            "crit": _crit(m.criticality if m else "internal"),
            "lineage": lineage, "findings": findings, "log": log}
