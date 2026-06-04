"""Слой данных «Инспектор узла»: ModelVersion → прогон (run) + причастный (actor→роль).

Прогон = версия модели в контуре. Узел пайплайна выводится из stage версии, state —
из stage + открытых критичных findings + requires_validation + Approval. Только реальные
данные (SessionLocal как в routers/*), без мока.

Привязка findings↔версия: все версионные findings пишутся с asset_ref='model/<id>/v<n>'
(ингест admitted, verify-artifact, prod-verify), поэтому findings версии собираем строго
по 'model/<id>/v<n>' — без эвристик. Model-scoped 'model/<id>' остаётся только у findings
заблокированного ингеста (вредоносный артефакт — версия не создаётся): это «отклонённая
попытка», она видна в журнале/на гейте, но намеренно не относится ни к одному прогону.
"""
from collections import defaultdict
from datetime import datetime, timezone

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


def role_of(item):
    """(account, role) для отображения «причастен». Предпочитает РОЛЬ, сохранённую в записи
    (Finding.role) — она надёжна и в проде, где actor = UUID Keycloak; иначе fallback на
    эвристику actor_role по actor (старые записи / не-Finding акторы)."""
    if isinstance(item, dict):
        actor = item.get("actor")
        stored = (item.get("role") or "").strip()
        if stored:
            return ((actor or "").strip() or "—"), stored
        return actor_role(actor)
    return actor_role(item)


def asset_href(asset_ref):
    """URL карточки сущности по asset_ref, иначе None — для кликабельных активов в журнале/инциденте.
    model/<id>[/v<n>] → карточка модели; dataset/<id> → карточка датасета. Прочее
    (endpoint/code/ci/deps/actor/dataset/scan) карточки не имеет → None (остаётся текстом)."""
    parts = (asset_ref or "").split("/")
    if len(parts) >= 2 and parts[0] == "model" and parts[1].isdigit():
        return f"/registry/model/{parts[1]}"
    if len(parts) == 2 and parts[0] == "dataset" and parts[1].isdigit():
        return f"/data/dataset/{parts[1]}"
    return None


def _crit(criticality):
    return criticality if criticality in ("regulatory", "financial") else "internal"


def _dur_stub(ts):
    """Детерминированная псевдо-длительность 'MM:SS' — fallback для легаси-версий без created_at."""
    h = abs(hash(ts or "")) if ts else 0
    return f"{(h // 60) % 60:02d}:{h % 60:02d}"


def _parse_iso(s):
    try:
        return datetime.fromisoformat(s) if s else None
    except (ValueError, TypeError):
        return None


def _fmt_dur(secs):
    secs = int(max(0, secs))
    if secs < 3600:
        return f"{secs // 60:02d}:{secs % 60:02d}"
    if secs < 86400:
        return f"{secs // 3600}ч {(secs % 3600) // 60:02d}м"
    return f"{secs // 86400}д {(secs % 86400) // 3600}ч"


def _duration(created, terminal, seed):
    """Настоящая длительность по timestamps версии: created → (promoted|retired|сейчас).
    Если created_at нет (легаси-версия) — честная детерминированная псевдо-длительность."""
    start = _parse_iso(created)
    if start is None:
        return _dur_stub(seed)
    end = _parse_iso(terminal) or datetime.now(timezone.utc)
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return _fmt_dur((end - start).total_seconds())


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


def _version_findings(idx, model_id, version):
    return list(idx.get(f"model/{model_id}/v{version}", []))


def _state_of(stage, open_critical, requires_validation, has_approval, rejected=False):
    if stage == "retired":
        return "retired"
    if open_critical:
        return "blocked"
    if stage == "prod":
        return "passed"
    if requires_validation:
        if rejected:
            return "rejected"
        return "hold" if has_approval else "gate"
    return "running"


def _standing_decision(s, mv, owner):
    """Стоящее решение аппрув-гейта по версии: последнее (по id) решение ОТ ДРУГОГО, чем владелец,
    привязанное к текущему артефакту. Совпадает с логикой гейта promote (anti-TOCTOU)."""
    return (s.query(domain.Approval)
            .filter(domain.Approval.model_version_id == mv.id,
                    domain.Approval.approver != (owner or ""),
                    domain.Approval.artifact_hash == (mv.artifact_hash or ""))
            .order_by(domain.Approval.id.desc()).first())


def _enrich(s, idx, last_actor, mv, model):
    findings = _version_findings(idx, model.id, mv.version)
    open_critical = sum(1 for f in findings if f.status == "open" and f.severity == "critical")
    standing = _standing_decision(s, mv, model.owner)
    has_approval = bool(standing) and standing.decision == "approve"
    rejected = bool(standing) and standing.decision == "reject"
    actor = last_actor.get(f"model/{model.id}/v{mv.version}") or model.owner or "—"
    started = mv.created_at or (min((f.ts for f in findings if f.ts), default="") or "")
    node = "gate-artifact" if open_critical else _STAGE_NODE.get(mv.stage, "package")
    return {
        "id": f"RUN-{mv.id}", "model": model.name, "ver": f"v{mv.version}",
        "crit": _crit(model.criticality), "started": started,
        "dur": _duration(mv.created_at, mv.retired_at or mv.promoted_at, f"{model.id}:{mv.version}"),
        "findings": len(findings),
        "actor": actor, "node": node,
        "state": _state_of(mv.stage, open_critical, bool(mv.requires_validation), has_approval, rejected),
        "_stage": mv.stage,
    }


def run_summary(run_id):
    """Сводка одного прогона (тот же dict, что в очереди узла) — для рефреша инспектора
    после действия аппрув-гейта. Переиспользует _enrich, чтобы state считался единообразно."""
    mvid = _parse_run_id(run_id)
    if mvid is None:
        return None
    with SessionLocal() as s:
        mv = s.query(domain.ModelVersion).filter_by(id=mvid).first()
        if not mv:
            return None
        m = s.query(domain.Model).filter_by(id=mv.model_id).first()
        if not m:
            return None
        idx = _findings_index(s)
        last_actor = _last_actor_by_version(s)
        r = _enrich(s, idx, last_actor, mv, m)
    r.pop("_stage", None)
    return r


def runs_for_node(node_id):
    """Прогоны (версии контура) для инспектора узла. Свои версии узла (по стадии; для
    gate-artifact — «застрявшие») или весь контур, если своих нет. Новые версии первыми."""
    with SessionLocal() as s:
        idx = _findings_index(s)
        last_actor = _last_actor_by_version(s)
        models = {m.id: m for m in s.query(domain.Model).all()}
        runs = []
        for mv in s.query(domain.ModelVersion).order_by(domain.ModelVersion.id.desc()).all():
            m = models.get(mv.model_id)
            if m:
                runs.append(_enrich(s, idx, last_actor, mv, m))
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
        f_rows = (s.query(domain.Finding)
                  .filter(domain.Finding.asset_ref == f"model/{mv.model_id}/v{mv.version}")
                  .order_by(domain.Finding.id.desc()).all())
        findings = [{"id": f.id, "ts": f.ts, "tool": f.tool, "verdict": f.verdict,
                     "severity": f.severity, "status": f.status, "asset": f.asset_ref,
                     "detail": f.detail, "actor": f.actor, "role": f.role} for f in f_rows]
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
        decision = _decision_block(s, mv, m, f_rows)
        timing = {"created": mv.created_at or "", "promoted": mv.promoted_at or "",
                  "retired": mv.retired_at or "",
                  "dur": _duration(mv.created_at, mv.retired_at or mv.promoted_at, f"{mv.model_id}:{mv.version}")}
    return {"model": (m.name if m else ""), "ver": f"v{mv.version}", "stage": mv.stage,
            "crit": _crit(m.criticality if m else "internal"),
            "lineage": lineage, "findings": findings, "log": log, "decision": decision, "timing": timing}


def _decision_block(s, mv, m, f_rows):
    """Сводка ручного аппрув-гейта для инспектора: «почему требует внимания» (чеклист гейта
    promote по доказательствам) + принятые решения + что нужно для действия. Гейт зеркалит
    promote: модель-карта (GOV-01), воспроизводимость (MON-02), подпись (SUP-04), нет открытых
    critical (GRC), аппрув другим MLSecOps (VIS-03/ACC-02)."""
    owner = (m.owner if m else "") or ""
    open_critical = sum(1 for f in f_rows if f.status == "open" and f.severity == "critical")
    missing_lin = [x for x in ("dataset_version_id", "code_commit", "env_lock") if not getattr(mv, x)]
    card_ok = bool(mv.intended_use and mv.limitations)
    signed = bool(mv.signature_bundle)
    appr_rows = (s.query(domain.Approval).filter(domain.Approval.model_version_id == mv.id)
                 .order_by(domain.Approval.id.asc()).all())
    standing = _standing_decision(s, mv, owner)
    has_approval = bool(standing) and standing.decision == "approve"
    rejected = bool(standing) and standing.decision == "reject"
    state = _state_of(mv.stage, open_critical, bool(mv.requires_validation), has_approval, rejected)
    if has_approval:
        approval_detail = f"одобрено: {standing.approver}"
    elif rejected:
        approval_detail = f"отклонено: {standing.approver}"
    else:
        approval_detail = "ожидает решения MLSecOps"
    gate = [
        {"key": "card", "label": "Модель-карта (GOV-01)", "ok": card_ok,
         "detail": "intended_use + limitations заполнены" if card_ok else "не хватает intended_use / limitations"},
        {"key": "repro", "label": "Воспроизводимость (MON-02)", "ok": not missing_lin,
         "detail": "dataset + commit + env-lock зафиксированы" if not missing_lin else f"нет: {', '.join(missing_lin)}"},
        {"key": "sign", "label": "Подпись артефакта (SUP-04)", "ok": signed,
         "detail": (mv.signature or "model-signing") if signed else "версия не подписана"},
        {"key": "crit", "label": "Нет открытых critical (GRC)", "ok": open_critical == 0,
         "detail": "критичных открытых сработок нет" if open_critical == 0 else f"{open_critical} открытая(ых) critical"},
        {"key": "approval", "label": "Аппрув другим MLSecOps (VIS-03/ACC-02)", "ok": has_approval,
         "detail": approval_detail},
    ]
    dlist = [{"approver": a.approver, "role": (a.role or actor_role(a.approver)[1]), "ts": _short_t(a.ts),
              "reason": a.reason or "", "decision": (a.decision or "approve")} for a in appr_rows]
    return {"model_id": mv.model_id, "version": mv.version, "state": state,
            "requires_validation": bool(mv.requires_validation),
            "criticality": _crit(m.criticality if m else "internal"), "owner": owner,
            "artifact_hash": mv.artifact_hash or "", "gate": gate, "decisions": dlist,
            "blockers": sum(1 for g in gate if not g["ok"])}
