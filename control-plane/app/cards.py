"""Слой данных: реестры (данные, решения) + карточки сущностей (модель, датасет).

Карточка = единая «история» актива по реальным данным: текущий статус, версии,
lineage (данные↔модели), проблемы (findings — где и какие), решения ручного
аппрув-гейта и таймлайн аудита. Источник — только SessionLocal (как routers/*).
Переиспользует агрегаторы runs.py, чтобы статусы считались единообразно с инспектором.
"""
from collections import defaultdict

from . import domain
from .db import AuditEvent, SessionLocal
from .runs import _crit, _duration, _short_t, _standing_decision, _state_of, actor_role, role_of

TRUSTED_PREFIXES = ("internal://", "curated://", "trusted:", "s3://sirius-")


def _trusted(src):
    return bool(src) and src.startswith(TRUSTED_PREFIXES)


def _lvl(severity, status):
    if status in ("FP",):
        return "info"
    return "err" if severity in ("critical", "high") else "warn" if severity == "medium" else "info"


# Машинный код события аудита → человекочитаемая подпись (сырой код остаётся рядом для трассы).
_ACT_LABELS = {
    "model.register": "модель зарегистрирована",
    "model.version": "загружена версия",
    "model.sign": "артефакт подписан",
    "model.promote": "промоушен в прод",
    "model.promote.risk-accepted": "промоушен с принятием риска",
    "model.retire": "версия выведена",
    "promote.blocked.open-critical": "промоушен заблокирован: открытый critical",
    "promote.blocked": "промоушен заблокирован",
    "artifact.tamper.detected": "обнаружена подмена артефакта",
    "gate.approve": "аппрув гейта",
    "gate.reject": "отклонение гейта",
    "risk.accept": "принятие остаточного риска",
    "dataset.create": "датасет создан",
    "dataset.scan.flagged": "скан данных: аномалия",
    "dataset.scan.clean": "скан данных: чисто",
    "deps.scan.flagged": "скан зависимостей: уязвимость",
    "deps.scan.clean": "скан зависимостей: чисто",
    "dataset.read": "чтение датасета",
    "dataset.read.deny": "чтение датасета отклонено",
    "dataset.schema.read": "чтение схемы",
}


def _humanize(action):
    """Подпись события на естественном языке (без знания внутренней номенклатуры)."""
    a = action or ""
    if a in _ACT_LABELS:
        return _ACT_LABELS[a]
    base = a.split(":", 1)[0]                      # dataset.create:active → dataset.create
    if base in _ACT_LABELS:
        return _ACT_LABELS[base]
    for k, v in _ACT_LABELS.items():
        if a.startswith(k):
            return v
    return a.replace(".", " · ").replace("_", " ") or "—"


def _audit_timeline(s, like):
    """События аудита по объекту (obj LIKE), отсортированные по времени — «что происходило»."""
    out = []
    for ev in s.query(AuditEvent).filter(AuditEvent.obj.like(like)).order_by(AuditEvent.id.asc()).all():
        act = ev.action or ""
        lvl = ("err" if (not ev.was_authorized or "blocked" in act or "denied" in act or "reject" in act)
               else "sec" if ("sign" in act or "approve" in act or "promote" in act) else "info")
        acct, rl = actor_role(ev.actor)
        out.append({"t": _short_t(ev.ts), "actor": acct, "role": rl, "action": act,
                    "label": _humanize(act), "obj": ev.obj or "", "lvl": lvl})
    return out


# ─────────────────────────── РЕЕСТР МОДЕЛЕЙ ───────────────────────────
def model_registry():
    """Список моделей со сводкой: критичность, версии·стадии, владелец и число
    открытых критичных/high-проблем (чтобы «кто требует внимания» был виден сразу)."""
    with SessionLocal() as s:
        models = s.query(domain.Model).order_by(domain.Model.id.desc()).all()
        ver_by_m = defaultdict(list)
        for mv in s.query(domain.ModelVersion).all():
            ver_by_m[mv.model_id].append(mv)
        open_by_m = defaultdict(int)
        for f in (s.query(domain.Finding)
                  .filter(domain.Finding.status == "open",
                          domain.Finding.severity.in_(("critical", "high"))).all()):
            ref = (f.asset_ref or "").split("/")
            if len(ref) >= 2 and ref[0] == "model" and ref[1].isdigit():
                open_by_m[int(ref[1])] += 1
        rows, vt, prod, crit = [], 0, 0, 0
        for m in models:
            vers = sorted(ver_by_m.get(m.id, []), key=lambda v: v.version)
            vt += len(vers)
            prod += sum(1 for v in vers if v.stage == "prod")
            crit += 1 if m.criticality in ("regulatory", "financial") else 0
            rows.append({"id": m.id, "name": m.name, "criticality": m.criticality,
                         "owner": m.owner or "—", "open": open_by_m.get(m.id, 0),
                         "versions": [{"version": v.version, "stage": v.stage} for v in vers]})
    kpi = {"models": len(rows), "versions": vt, "prod": prod, "critical": crit,
           "problems": sum(1 for r in rows if r["open"])}
    return rows, kpi


# ─────────────────────────── РЕЕСТР ДАННЫХ ───────────────────────────
def data_registry():
    """Список датасетов со сводкой: чувствительность, доверенность источника, версии,
    PII-колонки, открытые проблемы, число моделей-потребителей."""
    with SessionLocal() as s:
        datasets = s.query(domain.Dataset).order_by(domain.Dataset.id.desc()).all()
        ver_by_ds = defaultdict(int)
        dv_to_ds = {}
        for dv in s.query(domain.DatasetVersion).all():
            ver_by_ds[dv.dataset_id] += 1
            dv_to_ds[dv.id] = dv.dataset_id
        pii_by_ds, col_by_ds = defaultdict(int), defaultdict(int)
        for c in s.query(domain.DatasetColumn).all():
            col_by_ds[c.dataset_id] += 1
            if c.is_pii:
                pii_by_ds[c.dataset_id] += 1
        open_by_ds = defaultdict(int)
        for f in s.query(domain.Finding).filter(domain.Finding.asset_type == "dataset",
                                                domain.Finding.status == "open").all():
            ref = (f.asset_ref or "").split("/", 1)
            if len(ref) == 2 and ref[0] == "dataset" and ref[1].isdigit():
                open_by_ds[int(ref[1])] += 1
        cons_by_ds = defaultdict(set)
        for mv in s.query(domain.ModelVersion).all():
            ds_id = dv_to_ds.get(mv.dataset_version_id)
            if ds_id is not None:
                cons_by_ds[ds_id].add(mv.model_id)
        rows = []
        for d in datasets:
            rows.append({"id": d.id, "name": d.name, "sensitivity": d.sensitivity,
                         "source": d.source, "trusted": _trusted(d.source),
                         "versions": ver_by_ds.get(d.id, 0), "columns": col_by_ds.get(d.id, 0),
                         "pii": pii_by_ds.get(d.id, 0), "open": open_by_ds.get(d.id, 0),
                         "consumers": len(cons_by_ds.get(d.id, set()))})
        # Scoped-сканы качества/целостности (DATA-02/03/05): сканируют полезную нагрузку,
        # а не зарегистрированный датасет → asset_ref="dataset/scan" без id. Показываем
        # отдельно, чтобы такие находки не «терялись» вне карточек.
        scans = []
        for f in (s.query(domain.Finding).filter(domain.Finding.asset_ref == "dataset/scan")
                  .order_by(domain.Finding.id.desc()).all()):
            acct, rl = role_of({"actor": f.actor, "role": f.role})
            scans.append({"id": f.id, "ts": _short_t(f.ts), "tool": f.tool, "verdict": f.verdict,
                          "severity": f.severity, "status": f.status, "detail": f.detail,
                          "actor": acct, "role": rl})
    kpi = {"datasets": len(rows), "quarantined": sum(1 for r in rows if not r["trusted"]),
           "pii": sum(1 for r in rows if r["pii"]), "open": sum(r["open"] for r in rows),
           "scoped_scans": sum(1 for x in scans if x["status"] == "open")}
    return rows, kpi, scans


# ─────────────────────────── КАРТОЧКА ДАТАСЕТА ───────────────────────────
def dataset_card(dataset_id):
    """История датасета: версии, схема (PII), доверенность источника, проблемы,
    модели-потребители (lineage), таймлайн аудита."""
    with SessionLocal() as s:
        d = s.get(domain.Dataset, dataset_id)
        if not d:
            return None
        versions = (s.query(domain.DatasetVersion).filter_by(dataset_id=dataset_id)
                    .order_by(domain.DatasetVersion.id.asc()).all())
        dv_ids = [dv.id for dv in versions]
        columns = s.query(domain.DatasetColumn).filter_by(dataset_id=dataset_id).all()
        f_rows = (s.query(domain.Finding).filter(domain.Finding.asset_ref == f"dataset/{dataset_id}")
                  .order_by(domain.Finding.id.desc()).all())
        findings = [{"id": f.id, "ts": _short_t(f.ts), "tool": f.tool, "verdict": f.verdict,
                     "severity": f.severity, "status": f.status, "detail": f.detail,
                     **dict(zip(("actor", "role"), role_of({"actor": f.actor, "role": f.role})))}
                    for f in f_rows]
        consumers = []
        if dv_ids:
            for mv in (s.query(domain.ModelVersion)
                       .filter(domain.ModelVersion.dataset_version_id.in_(dv_ids))
                       .order_by(domain.ModelVersion.id.desc()).all()):
                m = s.get(domain.Model, mv.model_id)
                consumers.append({"model_id": mv.model_id, "model": (m.name if m else f"#{mv.model_id}"),
                                  "version": mv.version, "stage": mv.stage,
                                  "dataset_version_id": mv.dataset_version_id})
        timeline = _audit_timeline(s, f"dataset/{dataset_id}")
        open_crit = sum(1 for f in f_rows if f.status == "open" and f.severity in ("critical", "high"))
        trusted = _trusted(d.source)
        status = ("карантин" if not trusted else "проблемы" if open_crit else "ок")
        card = {
            "id": d.id, "name": d.name, "sensitivity": d.sensitivity, "source": d.source or "—",
            "owner": d.owner or "—", "trusted": trusted, "status": status,
            "versions": [{"id": dv.id, "hash": dv.hash or "—"} for dv in versions],
            # AUD-07: UI-карточка без идентичности — PII-сэмплы маскируем по умолчанию (как заявляет note
            # в ui/cards.py). Снятие маски для допущенных ролей — на пути с forward_auth (см. рунбук).
            "columns": [{"name": c.name, "pii": bool(c.is_pii),
                         "sample": ("***" if c.is_pii else (c.sample or "—"))} for c in columns],
            "findings": findings, "consumers": consumers, "timeline": timeline,
            "open": sum(1 for f in f_rows if f.status == "open"),
        }
    return card


# ─────────────────────────── КАРТОЧКА МОДЕЛИ ───────────────────────────
def model_card(model_id):
    """История модели: версии (стадия, тайминг, lineage, подпись, состояние аппрув-гейта),
    проблемы (findings по версиям), решения аппрув-гейта, источники данных, таймлайн аудита."""
    with SessionLocal() as s:
        m = s.get(domain.Model, model_id)
        if not m:
            return None
        mvs = (s.query(domain.ModelVersion).filter_by(model_id=model_id)
               .order_by(domain.ModelVersion.version.desc()).all())
        mv_ids = [mv.id for mv in mvs]
        # findings по версиям и model-scoped
        f_all = (s.query(domain.Finding).filter(domain.Finding.asset_ref.like(f"model/{model_id}%"))
                 .order_by(domain.Finding.id.desc()).all())
        f_by_ref = defaultdict(list)
        for f in f_all:
            f_by_ref[f.asset_ref].append(f)
        # решения по версиям
        appr_by_mv = defaultdict(list)
        if mv_ids:
            for a in (s.query(domain.Approval).filter(domain.Approval.model_version_id.in_(mv_ids))
                      .order_by(domain.Approval.id.asc()).all()):
                appr_by_mv[a.model_version_id].append(a)
        # активные деплои
        active_dep = {d.model_version_id for d in
                      s.query(domain.Deployment).filter_by(status="active").all()
                      if d.model_version_id in set(mv_ids)}
        # имена датасетов для lineage
        ds_name = {}
        for dv in s.query(domain.DatasetVersion).all():
            ds = s.get(domain.Dataset, dv.dataset_id)
            ds_name[dv.id] = {"dataset_id": dv.dataset_id, "name": (ds.name if ds else f"dv#{dv.id}")}

        versions, decisions, problems = [], [], []
        for mv in mvs:
            vfind = f_by_ref.get(f"model/{model_id}/v{mv.version}", [])
            open_crit = sum(1 for f in vfind if f.status == "open" and f.severity == "critical")
            standing = _standing_decision(s, mv, m.owner)
            has_appr = bool(standing) and standing.decision == "approve"
            rejected = bool(standing) and standing.decision == "reject"
            state = _state_of(mv.stage, open_crit, bool(mv.requires_validation), has_appr, rejected)
            ds = ds_name.get(mv.dataset_version_id)
            versions.append({
                "version": mv.version, "stage": mv.stage, "state": state,
                "created": _short_t(mv.created_at), "promoted": _short_t(mv.promoted_at),
                "retired": _short_t(mv.retired_at),
                "dur": _duration(mv.created_at, mv.retired_at or mv.promoted_at, f"{model_id}:{mv.version}"),
                "dataset": (ds["name"] if ds else "—"), "dataset_id": (ds["dataset_id"] if ds else None),
                "code_commit": mv.code_commit or "—", "env_lock": mv.env_lock or "—",
                "signature": mv.signature or ("model-signing" if mv.signature_bundle else "—"),
                "requires_validation": bool(mv.requires_validation), "findings": len(vfind),
                "deployed": mv.id in active_dep,
            })
            for a in appr_by_mv.get(mv.id, []):
                _acct, _rl = role_of({"actor": a.approver, "role": a.role})
                decisions.append({"version": mv.version, "decision": (a.decision or "approve"),
                                  "approver": _acct, "role": _rl, "ts": _short_t(a.ts),
                                  "reason": a.reason or ""})
        # проблемы: открытые findings по всей модели (версионные + model-scoped)
        for f in f_all:
            if f.status == "open" and f.severity in ("critical", "high", "medium"):
                _acct, _rl = role_of({"actor": f.actor, "role": f.role})
                problems.append({"id": f.id, "ts": _short_t(f.ts), "tool": f.tool, "verdict": f.verdict,
                                 "severity": f.severity, "asset": f.asset_ref, "detail": f.detail,
                                 "actor": _acct, "role": _rl})
        timeline = _audit_timeline(s, f"model/{model_id}%")
        # сводный статус модели
        any_prod = any(v["stage"] == "prod" for v in versions)
        any_open_crit = any(f.status == "open" and f.severity == "critical" for f in f_all)
        any_gate = any(v["state"] == "gate" for v in versions)
        any_reject = any(v["state"] == "rejected" for v in versions)
        status = ("проблемы" if any_open_crit or any_reject else "ждёт решения" if any_gate
                  else "в проде" if any_prod else "в разработке")
        card = {"id": m.id, "name": m.name, "type": m.type or "—", "criticality": _crit(m.criticality),
                "owner": m.owner or "—", "status": status, "versions": versions,
                "decisions": decisions, "problems": problems, "timeline": timeline,
                "open": sum(1 for f in f_all if f.status == "open")}
    return card


# ─────────────────────────── РЕЕСТР РЕШЕНИЙ (аппрув-гейт + GRC) ───────────────────────────
def decisions_ledger():
    """Governance system-of-record: решения ручного аппрув-гейта (Approval) и принятия
    остаточного риска (RiskAcceptance) — кто/когда/что решил по какой версии, с обоснованием."""
    with SessionLocal() as s:
        mv_ref = {}
        for mv in s.query(domain.ModelVersion).all():
            m = s.get(domain.Model, mv.model_id)
            mv_ref[mv.id] = {"model_id": mv.model_id, "model": (m.name if m else f"#{mv.model_id}"),
                             "version": mv.version}
        decisions = []
        for a in s.query(domain.Approval).order_by(domain.Approval.id.desc()).all():
            ref = mv_ref.get(a.model_version_id, {})
            acct, rl = role_of({"actor": a.approver, "role": a.role})
            decisions.append({"decision": (a.decision or "approve"), "approver": acct, "role": rl,
                              "ts": _short_t(a.ts), "model_id": ref.get("model_id"),
                              "model": ref.get("model", "—"), "version": ref.get("version", "—"),
                              "reason": a.reason or ""})
        risks = []
        for r in s.query(domain.RiskAcceptance).order_by(domain.RiskAcceptance.id.desc()).all():
            acct, rl = actor_role(r.accepted_by)
            risks.append({"scope": r.scope, "ref": r.ref, "by": acct, "role": rl, "ts": _short_t(r.ts),
                          "justification": r.justification or "", "conditions": r.conditions or "—",
                          "expires": r.expires_at or "бессрочно", "active": bool(r.active)})
    kpi = {"total": len(decisions), "approve": sum(1 for d in decisions if d["decision"] == "approve"),
           "reject": sum(1 for d in decisions if d["decision"] == "reject"), "risk": len(risks)}
    return decisions, risks, kpi


# ─────────────────────────── РЕЕСТР ПОЛЬЗОВАТЕЛЕЙ / АКТОРОВ ───────────────────────────
def users_registry():
    """Реестр акторов (люди и сервис-аккаунты), собранный из аудита / findings / решений /
    владения. Для каждого — роль и счётчики: действий (аудит), инцидентов (причастность),
    открытых критичных, решений, владения. «Кто что делал» в одном месте."""
    with SessionLocal() as s:
        agg = {}

        def touch(a):
            a = (a or "").strip()
            if not a:
                return None
            return agg.setdefault(a, {"actor": a, "audit": 0, "findings": 0, "open": 0,
                                      "decisions": 0, "owns": 0, "role": "", "last": ""})
        for f in s.query(domain.Finding).all():
            d = touch(f.actor)
            if d:
                d["findings"] += 1
                if f.status == "open" and f.severity in ("critical", "high"):
                    d["open"] += 1
                if f.role and not d["role"]:
                    d["role"] = f.role
        for ev in s.query(AuditEvent).all():
            d = touch(ev.actor)
            if d:
                d["audit"] += 1
                if (ev.ts or "") > d["last"]:
                    d["last"] = ev.ts or ""
        for a in s.query(domain.Approval).all():
            d = touch(a.approver)
            if d:
                d["decisions"] += 1
                if a.role and not d["role"]:
                    d["role"] = a.role
        for r in s.query(domain.RiskAcceptance).all():
            d = touch(r.accepted_by)
            if d:
                d["decisions"] += 1
        for m in s.query(domain.Model).all():
            d = touch(m.owner)
            if d:
                d["owns"] += 1
        for ds in s.query(domain.Dataset).all():
            d = touch(ds.owner)
            if d:
                d["owns"] += 1
        rows = []
        for a, d in agg.items():
            acct, heur = actor_role(a)
            rows.append({**d, "account": acct, "role": (d["role"] or heur), "last": _short_t(d["last"])})
    rows.sort(key=lambda r: -(r["audit"] + r["findings"] * 3 + r["decisions"] * 2))
    kpi = {"users": len(rows), "with_incidents": sum(1 for r in rows if r["open"]),
           "decision_makers": sum(1 for r in rows if r["decisions"]),
           "owners": sum(1 for r in rows if r["owns"])}
    return rows, kpi


# ─────────────────────────── КАРТОЧКА ПОЛЬЗОВАТЕЛЯ / АКТОРА ───────────────────────────
def user_card(actor):
    """История актора в одном месте: активность (аудит), инциденты (сработки причастности,
    актив кликабелен), решения (аппрув-гейт + принятие риска), владение (модели/датасеты).
    Кросс-ссылки на карточки сущностей. None — если актор нигде не встречается."""
    actor = (actor or "").strip()
    if not actor:
        return None
    with SessionLocal() as s:
        f_rows = (s.query(domain.Finding).filter(domain.Finding.actor == actor)
                  .order_by(domain.Finding.id.desc()).all())
        ev_rows = (s.query(AuditEvent).filter(AuditEvent.actor == actor)
                   .order_by(AuditEvent.id.desc()).limit(150).all())
        appr = (s.query(domain.Approval).filter(domain.Approval.approver == actor)
                .order_by(domain.Approval.id.desc()).all())
        risks = (s.query(domain.RiskAcceptance).filter(domain.RiskAcceptance.accepted_by == actor)
                 .order_by(domain.RiskAcceptance.id.desc()).all())
        own_m = s.query(domain.Model).filter(domain.Model.owner == actor).all()
        own_d = s.query(domain.Dataset).filter(domain.Dataset.owner == actor).all()
        if not (f_rows or ev_rows or appr or risks or own_m or own_d):
            return None
        role = next((f.role for f in f_rows if f.role), "") or next((a.role for a in appr if a.role), "")
        acct, heur = actor_role(actor)
        role = role or heur
        mv_ref = {}
        for a in appr:
            mv = s.get(domain.ModelVersion, a.model_version_id)
            if mv:
                m = s.get(domain.Model, mv.model_id)
                mv_ref[a.model_version_id] = {"model_id": mv.model_id, "model": (m.name if m else "—"),
                                              "version": mv.version}
        incidents = [{"id": f.id, "ts": _short_t(f.ts), "tool": f.tool, "verdict": f.verdict,
                      "severity": f.severity, "status": f.status, "asset": f.asset_ref, "detail": f.detail}
                     for f in f_rows]
        activity = []
        for ev in ev_rows:
            act = ev.action or ""
            lvl = ("err" if (not ev.was_authorized or "blocked" in act or "denied" in act or "reject" in act)
                   else "sec" if ("sign" in act or "approve" in act or "promote" in act or "secret" in act) else "info")
            activity.append({"t": _short_t(ev.ts), "action": act, "label": _humanize(act),
                             "obj": ev.obj or "", "lvl": lvl})
        decisions = []
        for a in appr:
            ref = mv_ref.get(a.model_version_id, {})
            decisions.append({"kind": "gate", "decision": (a.decision or "approve"), "ts": _short_t(a.ts),
                              "model_id": ref.get("model_id"), "model": ref.get("model", "—"),
                              "version": ref.get("version", "—"), "reason": a.reason or ""})
        for r in risks:
            decisions.append({"kind": "risk", "ref": r.ref, "ts": _short_t(r.ts),
                              "justification": r.justification or "", "active": bool(r.active)})
        owns = ([{"kind": "model", "id": m.id, "name": m.name, "crit": _crit(m.criticality)} for m in own_m]
                + [{"kind": "dataset", "id": dd.id, "name": dd.name, "sensitivity": dd.sensitivity} for dd in own_d])
        open_inc = sum(1 for f in f_rows if f.status == "open" and f.severity in ("critical", "high"))
        status = "есть инциденты" if open_inc else ("активен" if ev_rows else "—")
        card = {"actor": actor, "account": acct, "role": role, "status": status,
                "incidents": incidents, "activity": activity, "decisions": decisions, "owns": owns,
                "kpi": {"audit": len(ev_rows), "incidents": len(f_rows), "open": open_inc,
                        "decisions": len(appr) + len(risks), "owns": len(owns)}}
    return card
