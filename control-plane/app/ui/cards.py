"""ui.cards — карточки сущностей (модель, датасет) в дизайн-языке SA."""
from .layout import _e, _page


# ── цвет-токены измерений ────────────────────────────────────────────────────
_CRIT_COL = {
    "regulatory": "var(--sa-alert)",
    "financial": "#fb923c",
    "internal": "var(--sa-muted)",
}
_STAGE_COL = {
    "prod": "var(--sa-ok)",
    "staging": "var(--sa-warn)",
    "dev": "var(--sa-blue)",
    "retired": "var(--sa-muted)",
}
# (цвет, подпись) для состояния версии в гейте
_STATE = {
    "running": ("var(--sa-blue)", "running"),
    "gate": ("var(--sa-warn)", "GATE"),
    "hold": ("var(--sa-warn)", "HOLD"),
    "passed": ("var(--sa-ok)", "passed"),
    "rejected": ("var(--sa-alert)", "rejected"),
    "blocked": ("var(--sa-alert)", "blocked"),
    "retired": ("var(--sa-muted)", "retired"),
}
_SEV_COL = {
    "critical": "var(--sa-alert)",
    "high": "#fb923c",
    "medium": "var(--sa-warn)",
}
# Цвет актора в таймлайне по уровню события.
_LVL_COL = {
    "err": "var(--sa-alert)",
    "sec": "var(--sa-accent-ink)",
    "warn": "var(--sa-warn)",
    "info": "var(--sa-text2)",
}


# ── локальные бейдж-хелперы ──────────────────────────────────────────────────
def _badge(text, col, mono=False):
    cls = "sa-badge sa-mono" if mono else "sa-badge"
    return (f"<span class='{cls}' "
            f"style='color:{col};background:color-mix(in srgb,{col} 15%,transparent)'>"
            f"{text}</span>")


def _stage_badge(stage):
    col = _STAGE_COL.get(stage, "var(--sa-text2)")
    return _badge(_e(stage), col, mono=True)


def _state_badge(state):
    col, label = _STATE.get(state, ("var(--sa-text2)", state))
    return _badge(_e(label), col, mono=True)


def _sev_badge(severity, verdict=""):
    col = _SEV_COL.get(severity, "var(--sa-text2)")
    b = _badge(_e(severity), col)
    if verdict:
        return f"{b} <span style='color:var(--sa-text)'>{_e(verdict)}</span>"
    return b


def _crit_badge(crit):
    col = _CRIT_COL.get(crit, "var(--sa-text2)")
    return _badge(_e(crit), col)


def _actor(actor, role):
    return (f"{_e(actor)} <span class='sa-mono' style='color:var(--sa-accent-ink);"
            f"font-size:11px'>{_e(role)}</span>")


def _owner_link(owner):
    """Владелец → ссылка на карточку актора (если актор известен)."""
    from ..runs import actor_href
    href = actor_href(owner)
    return (f"<a href='{_e(href)}' style='color:var(--sa-accent-ink);text-decoration:none'>{_e(owner)}</a>"
            if href else _e(owner))


def _back_link(href, label):
    return (f"<a href='{_e(href)}' style='display:inline-flex;align-items:center;gap:6px;"
            f"color:var(--sa-muted);font-size:12px;text-decoration:none;margin-bottom:12px'>"
            f"<i class='bi bi-arrow-left'></i>{_e(label)}</a>")


def _kpi(label, value, sub="", accent=""):
    border = f" style='border-color:{accent}'" if accent else ""
    vcol = f" style='color:{accent}'" if accent else ""
    s = f"<div class='s'>{_e(sub)}</div>" if sub else ""
    return (f"<div class='sa-kpi'{border}><div class='l'>{_e(label)}</div>"
            f"<div class='v'{vcol}>{_e(value)}</div>{s}</div>")


def _kpi_grid(cells):
    return ("<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));"
            f"gap:12px;margin:16px 0'>{''.join(cells)}</div>")


def _eye(text):
    return f"<div class='sa-eye'>{_e(text)}</div>"


def _section(title, inner, note=""):
    n = (f"<p class='sa-sub' style='margin:-2px 0 10px'>{_e(note)}</p>") if note else ""
    return (f"<div class='sa-eye' style='margin-top:22px'>{_e(title)}</div>{n}{inner}")


def _empty(text):
    return (f"<div class='sa-panel' style='padding:16px;color:var(--sa-muted);font-size:13px'>"
            f"{_e(text)}</div>")


def _table(head_cells, rows):
    head = "".join(f"<th>{c}</th>" for c in head_cells)
    return ("<div class='sa-panel'><table class='sa-table'><thead><tr>"
            f"{head}</tr></thead><tbody>{rows}</tbody></table></div>")


def _timeline(rows):
    """Компактный терминалоподобный список событий, скроллящийся по высоте.
    Подпись — человекочитаемая (label), рядом приглушённо сырой код для трассы."""
    items = ""
    for r in rows:
        acol = _LVL_COL.get(r.get("lvl"), "var(--sa-text2)")
        items += (
            "<div style='display:flex;gap:12px;align-items:baseline;padding:4px 0;"
            "border-top:1px solid var(--sa-line)'>"
            f"<span class='sa-mono' style='color:var(--sa-muted);font-size:11.5px;"
            f"white-space:nowrap'>{_e(r.get('t'))}</span>"
            f"<span style='color:{acol};font-size:12.5px;white-space:nowrap'>"
            f"{_e(r.get('actor'))} <span class='sa-mono' style='color:var(--sa-text2);"
            f"font-size:11px'>{_e(r.get('role'))}</span></span>"
            f"<span style='color:var(--sa-text);font-size:12px'>"
            f"{_e(r.get('label') or r.get('action'))}</span>"
            f"<span class='sa-mono' style='color:var(--sa-muted);font-size:10px'>"
            f"{_e(r.get('action'))}</span></div>")
    if not items:
        items = ("<div style='color:var(--sa-muted);font-size:13px;padding:4px 0'>"
                 "событий пока нет</div>")
    return ("<div class='sa-panel' style='padding:6px 16px 10px;max-height:320px;"
            f"overflow:auto'>{items}</div>")


def _alertbar(kind, html_inner):
    """Полоса-сводка вверху карточки: alert (проблемы), warn (ждёт решения), ok (спокойно)."""
    col = {"alert": "var(--sa-alert)", "warn": "var(--sa-warn)", "ok": "var(--sa-ok)"}.get(
        kind, "var(--sa-text2)")
    icon = {"alert": "bi-exclamation-octagon-fill", "warn": "bi-hourglass-split",
            "ok": "bi-shield-check"}.get(kind, "bi-info-circle")
    return (f"<div class='sa-alertbar' style='border-color:color-mix(in srgb,{col} 45%,transparent);"
            f"background:color-mix(in srgb,{col} 12%,transparent);color:{col}'>"
            f"<i class='bi {icon}'></i><span style='color:var(--sa-text)'>{html_inner}</span></div>")


# ── карточка модели ──────────────────────────────────────────────────────────
def model_card_page(card):
    """Детальная карточка модели: версии, проблемы, решения гейта, таймлайн."""
    name = card["name"]
    status = card["status"]
    status_col = {
        "проблемы": "var(--sa-alert)",
        "ждёт решения": "var(--sa-warn)",
        "в проде": "var(--sa-ok)",
        "в разработке": "var(--sa-blue)",
    }.get(status, "var(--sa-text2)")

    versions = card.get("versions", [])
    prod_n = sum(1 for v in versions if v.get("stage") == "prod")

    head = (
        _eye("Sirius Argus · карточка модели")
        + _back_link("/registry", "← Реестр моделей")
        + f"<h1 class='sa-h1'>{_e(name)}</h1>"
        + "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-top:8px'>"
        + _crit_badge(card["criticality"])
        + _badge(_e(status), status_col)
        + "</div>"
        + "<p class='sa-sub'>тип · " + _e(card["type"])
        + " · владелец · " + _owner_link(card["owner"])
        + " · открытых проблем: " + _e(card["open"]) + "</p>"
    )

    kpis = _kpi_grid([
        _kpi("Версий", len(versions)),
        _kpi("В проде", prod_n, accent="var(--sa-ok)"),
        _kpi("Открытых проблем", card["open"],
             accent="var(--sa-alert)" if card["open"] else ""),
        _kpi("Решений", len(card.get("decisions", []))),
    ])

    # 1) Версии
    if not versions:
        ver_panel = _empty("версий ещё нет")
    else:
        rows = ""
        for v in versions:
            ds_name = v.get("dataset", "")
            if v.get("dataset_id") is not None:
                data_cell = (f"<a href='/data/dataset/{_e(v['dataset_id'])}' "
                             f"style='color:var(--sa-blue);text-decoration:none'>"
                             f"{_e(ds_name)}</a>")
            else:
                data_cell = f"<span style='color:var(--sa-text2)'>{_e(ds_name)}</span>"
            timing = (f"<span class='sa-mono' style='font-size:11.5px'>"
                      f"{_e(v.get('created'))} → {_e(v.get('promoted') or '—')}</span>"
                      f" <span style='color:var(--sa-muted);font-size:11px'>· "
                      f"{_e(v.get('dur'))}</span>")
            sig = f"<span class='sa-mono' style='font-size:11px'>{_e(v.get('signature'))}</span>"
            findings = v.get("findings", 0)
            f_col = "var(--sa-alert)" if findings else "var(--sa-text2)"
            f_cell = f"<span style='color:{f_col}'>{_e(findings)}</span>"
            deploy = (_badge("active", "var(--sa-ok)", mono=True) if v.get("deployed")
                      else "<span style='color:var(--sa-muted)'>—</span>")
            rows += (
                "<tr>"
                f"<td class='sa-mono' style='color:var(--sa-accent-ink);font-size:11.5px;"
                f"white-space:nowrap'>v{_e(v.get('version'))}</td>"
                f"<td>{_stage_badge(v.get('stage'))}</td>"
                f"<td>{_state_badge(v.get('state'))}</td>"
                f"<td>{data_cell}</td>"
                f"<td style='white-space:nowrap'>{timing}</td>"
                f"<td>{sig}</td>"
                f"<td style='text-align:center'>{f_cell}</td>"
                f"<td>{deploy}</td></tr>")
        ver_panel = _table(
            ["версия", "стадия", "состояние", "данные", "тайминг",
             "подпись", "сработок", "деплой"], rows)

    # 2) Проблемы
    problems = card.get("problems", [])
    if not problems:
        prob_panel = _empty("открытых проблем нет — модель спокойна")
    else:
        rows = ""
        for p in problems:
            rows += (
                "<tr>"
                f"<td class='sa-mono' style='color:var(--sa-muted);font-size:11.5px;"
                f"white-space:nowrap'>{_e(p.get('ts'))}</td>"
                f"<td style='white-space:nowrap'>{_sev_badge(p.get('severity'), p.get('verdict'))}</td>"
                f"<td>{_e(p.get('tool'))}</td>"
                f"<td><span class='sa-mono' style='font-size:11px'>{_e(p.get('asset'))}</span></td>"
                f"<td style='color:var(--sa-text2)'>{_e(p.get('detail'))}</td>"
                f"<td style='white-space:nowrap'>{_actor(p.get('actor'), p.get('role'))}</td></tr>")
        prob_panel = _table(
            ["время", "severity · вердикт", "инструмент", "актив", "детали", "причастен"], rows)

    # 3) Решения аппрув-гейта
    decisions = card.get("decisions", [])
    if not decisions:
        dec_panel = _empty("решений не было")
    else:
        rows = ""
        for d in decisions:
            if d.get("decision") == "approve":
                dec_badge = _badge("аппрув", "var(--sa-ok)")
            else:
                dec_badge = _badge("отклонение", "var(--sa-alert)")
            reason = d.get("reason")
            reason_cell = (f"<span style='font-style:italic;color:var(--sa-text2)'>"
                           f"{_e(reason)}</span>") if reason else \
                "<span style='color:var(--sa-muted)'>—</span>"
            rows += (
                "<tr>"
                f"<td class='sa-mono' style='color:var(--sa-accent-ink);font-size:11.5px;"
                f"white-space:nowrap'>v{_e(d.get('version'))}</td>"
                f"<td>{dec_badge}</td>"
                f"<td style='white-space:nowrap'>{_actor(d.get('approver'), d.get('role'))}</td>"
                f"<td class='sa-mono' style='color:var(--sa-muted);font-size:11.5px;"
                f"white-space:nowrap'>{_e(d.get('ts'))}</td>"
                f"<td>{reason_cell}</td></tr>")
        dec_panel = _table(
            ["версия", "решение", "аппрувер", "время", "обоснование"], rows)

    # алерт-полоса: сводка проблем/ожидания гейта сразу под KPI
    if status == "проблемы":
        bar = _alertbar("alert", f"Есть нерешённые проблемы — открытых сработок: "
                        f"<b>{_e(card['open'])}</b>. Версии с критичными находками заблокированы "
                        "перед продом (PROMOTE-GATE). Детали — в блоке «Проблемы» ниже.")
    elif status == "ждёт решения":
        bar = _alertbar("warn", "Версия ждёт <b>ручного аппрув-гейта</b> перед промоушеном "
                        "в прод. Решение примет уполномоченная роль.")
    else:
        bar = ""

    body = (
        head + kpis + bar
        + _section("Проблемы", prob_panel)
        + _section("Версии", ver_panel)
        + _section("Решения аппрув-гейта", dec_panel)
        + _section("Таймлайн", _timeline(card.get("timeline", [])))
    )
    return _page(f"Sirius Argus — {card['name']}", body, "registry", crumb=name)


# ── карточка датасета ────────────────────────────────────────────────────────
def dataset_card_page(card):
    """Детальная карточка датасета: схема, версии, проблемы, lineage, таймлайн."""
    name = card["name"]
    sens = card["sensitivity"]
    sens_col = {"pii": "#fb923c", "secret": "var(--sa-alert)", "open": "var(--sa-muted)"}.get(
        sens, "var(--sa-text2)")

    status = card["status"]
    if status == "карантин":
        status_badge = _badge(
            "<i class='bi bi-shield-exclamation'></i> карантин", "var(--sa-alert)")
    elif status == "проблемы":
        status_badge = _badge("проблемы", "var(--sa-warn)")
    else:
        status_badge = _badge("ок", "var(--sa-ok)")

    columns = card.get("columns", [])
    pii_n = sum(1 for c in columns if c.get("pii"))
    consumers = card.get("consumers", [])
    versions = card.get("versions", [])

    head = (
        _eye("Sirius Argus · карточка датасета")
        + _back_link("/data", "← Реестр данных")
        + f"<h1 class='sa-h1'>{_e(name)}</h1>"
        + "<div style='display:flex;flex-wrap:wrap;gap:8px;margin-top:8px'>"
        + _badge(_e(sens), sens_col)
        + status_badge
        + "</div>"
        + "<p class='sa-sub'>источник · " + _e(card["source"])
        + " · владелец · " + _owner_link(card["owner"]) + "</p>"
    )

    kpis = _kpi_grid([
        _kpi("Версий", len(versions)),
        _kpi("Колонок", len(columns)),
        _kpi("PII-колонок", pii_n, accent="#fb923c" if pii_n else ""),
        _kpi("Потребителей", len(consumers)),
    ])

    # 1) Доверенность источника
    if card.get("trusted"):
        trust_badge = _badge("доверенный источник", "var(--sa-ok)")
    else:
        trust_badge = _badge("недоверенный → карантин (DATA-01)", "var(--sa-alert)")
    trust_panel = (
        "<div class='sa-panel' style='padding:16px;display:flex;flex-wrap:wrap;"
        "align-items:center;gap:12px'>"
        f"<span class='sa-mono' style='font-size:12.5px;color:var(--sa-text)'>"
        f"{_e(card['source'])}</span>{trust_badge}</div>")

    # 2) Схема
    if not columns:
        schema_panel = _empty("схема не задана")
    else:
        rows = ""
        for c in columns:
            if c.get("pii"):
                pii_cell = _badge("PII", "#fb923c")
            else:
                pii_cell = "<span style='color:var(--sa-muted)'>—</span>"
            rows += (
                "<tr>"
                f"<td style='color:var(--sa-head);font-weight:600'>{_e(c.get('name'))}</td>"
                f"<td>{pii_cell}</td>"
                f"<td class='sa-mono' style='font-size:11.5px;color:var(--sa-text2)'>"
                f"{_e(c.get('sample'))}</td></tr>")
        schema_panel = _table(["колонка", "PII", "пример"], rows)

    # 3) Версии
    if not versions:
        ver_panel = _empty("версий ещё нет")
    else:
        rows = ""
        for v in versions:
            rows += (
                "<tr>"
                f"<td class='sa-mono' style='color:var(--sa-accent-ink);font-size:11.5px;"
                f"white-space:nowrap'>{_e(v.get('id'))}</td>"
                f"<td class='sa-mono' style='font-size:11.5px;color:var(--sa-text2)'>"
                f"{_e(v.get('hash'))}</td></tr>")
        ver_panel = _table(["id", "hash"], rows)

    # 4) Проблемы
    findings = card.get("findings", [])
    if not findings:
        find_panel = _empty("проблем по датасету нет")
    else:
        rows = ""
        for f in findings:
            rows += (
                "<tr>"
                f"<td class='sa-mono' style='color:var(--sa-muted);font-size:11.5px;"
                f"white-space:nowrap'>{_e(f.get('ts'))}</td>"
                f"<td style='white-space:nowrap'>{_sev_badge(f.get('severity'), f.get('verdict'))}</td>"
                f"<td>{_e(f.get('tool'))}</td>"
                f"<td style='color:var(--sa-text2)'>{_e(f.get('detail'))}</td>"
                f"<td><span class='sa-badge' style='color:var(--sa-text2);"
                f"background:color-mix(in srgb,var(--sa-text2) 14%,transparent)'>"
                f"{_e(f.get('status'))}</span></td>"
                f"<td style='white-space:nowrap'>{_actor(f.get('actor'), f.get('role'))}</td></tr>")
        find_panel = _table(
            ["время", "severity · вердикт", "инструмент", "детали", "статус", "причастен"], rows)

    # 5) Потребители (lineage)
    if not consumers:
        cons_panel = _empty("эти данные пока никто не потребил")
    else:
        rows = ""
        for c in consumers:
            model_link = (f"<a href='/registry/model/{_e(c.get('model_id'))}' "
                          f"style='color:var(--sa-blue);text-decoration:none'>"
                          f"{_e(c.get('model'))}</a>")
            rows += (
                "<tr>"
                f"<td style='color:var(--sa-head);font-weight:600'>{model_link}</td>"
                f"<td class='sa-mono' style='color:var(--sa-accent-ink);font-size:11.5px;"
                f"white-space:nowrap'>v{_e(c.get('version'))}</td>"
                f"<td>{_stage_badge(c.get('stage'))}</td></tr>")
        cons_panel = _table(["модель", "версия", "стадия"], rows)

    if status == "карантин":
        bar = _alertbar("alert", "Источник <b>недоверенный</b> — датасет в карантине (DATA-01). "
                        "Обучение на нём требует явного принятия остаточного риска.")
    elif status == "проблемы":
        bar = _alertbar("warn", "Есть открытые проблемы по датасету — см. блок «Проблемы» ниже.")
    else:
        bar = ""

    body = (
        head + kpis + bar
        + _section("Проблемы", find_panel)
        + _section("Доверенность источника", trust_panel)
        + _section("Схема", schema_panel,
                   note=(("PII-значения показаны — у вашей роли есть допуск (DATA-04)."
                          if card.get("pii_unmasked") else
                          "PII-значения замаскированы для вашей роли (DATA-04).")
                         if pii_n else ""))
        + _section("Версии", ver_panel)
        + _section("Потребители (lineage)", cons_panel,
                   note="какие версии моделей обучены на этих данных")
        + _section("Таймлайн", _timeline(card.get("timeline", [])))
    )
    return _page(f"Sirius Argus — {card['name']}", body, "data", crumb=name)


# ── карточка пользователя / актора ────────────────────────────────────────────
_USTATUS_COL = {"есть инциденты": "var(--sa-alert)", "активен": "var(--sa-ok)", "—": "var(--sa-muted)"}


def user_card_page(card):
    """Карточка актора: всё «кто что делал» в одном месте — активность (аудит), инциденты
    (причастность, актив кликабелен), решения (аппрув-гейт + риск), владение (модели/датасеты)."""
    from ..runs import asset_href
    acct, role, status = card["account"], card["role"], card["status"]
    k = card.get("kpi", {})
    scol = _USTATUS_COL.get(status, "var(--sa-muted)")

    def _asset(a):
        href = asset_href(a)
        return (f"<a href='{_e(href)}' class='sa-mono' style='color:var(--sa-blue);font-size:11.5px;"
                f"text-decoration:none'>{_e(a)} <i class='bi bi-box-arrow-up-right' style='font-size:9px'></i></a>"
                if href else f"<span class='sa-mono' style='color:var(--sa-text2);font-size:11.5px'>{_e(a)}</span>")

    # инциденты (причастность)
    if card.get("incidents"):
        rows = "".join(
            "<tr>"
            f"<td class='sa-mono' style='color:var(--sa-muted);white-space:nowrap'>{_e(i['ts'])}</td>"
            f"<td>{_sev_badge(i['severity'], i['verdict'])}</td>"
            f"<td class='sa-mono' style='color:var(--sa-text2);font-size:11.5px'>{_e(i['tool'])}</td>"
            f"<td>{_asset(i['asset'])}</td>"
            f"<td style='color:var(--sa-text2);max-width:360px'>{_e(i['detail'])}</td>"
            f"<td>{_badge(_e(i['status']), 'var(--sa-warn)' if i['status'] == 'open' else 'var(--sa-muted)', mono=True)}</td></tr>"
            for i in card["incidents"])
        inc_panel = _table(["время", "вердикт", "инструмент", "актив", "детали", "статус"], rows)
    else:
        inc_panel = _empty("инцидентов с причастностью нет")

    # решения
    if card.get("decisions"):
        rows = ""
        for d in card["decisions"]:
            if d["kind"] == "gate":
                appr = d["decision"] == "approve"
                badge = _badge("аппрув" if appr else "отклонение",
                               "var(--sa-ok)" if appr else "var(--sa-alert)")
                obj = (f"<a href='/registry/model/{_e(d['model_id'])}' style='color:var(--sa-blue);text-decoration:none'>"
                       f"{_e(d['model'])}</a> v{_e(d['version'])}" if d.get("model_id") is not None
                       else f"{_e(d['model'])} v{_e(d['version'])}")
                detail = _e(d.get("reason") or "—")
            else:
                badge = _badge("принятие риска", "#fb923c")
                obj = f"<span class='sa-mono' style='font-size:11.5px'>{_e(d['ref'])}</span>"
                detail = _e(d.get("justification") or "—")
            rows += (f"<tr><td>{badge}</td><td>{obj}</td>"
                     f"<td class='sa-mono' style='color:var(--sa-muted);white-space:nowrap'>{_e(d['ts'])}</td>"
                     f"<td style='color:var(--sa-text2);max-width:360px'>{detail}</td></tr>")
        dec_panel = _table(["решение", "объект", "время", "обоснование"], rows)
    else:
        dec_panel = _empty("решений не принимал")

    # владение
    if card.get("owns"):
        chips = ""
        for o in card["owns"]:
            if o["kind"] == "model":
                href, ic, tail = f"/registry/model/{o['id']}", "bi-box-seam", _crit_badge(o["crit"])
            else:
                href, ic, tail = f"/data/dataset/{o['id']}", "bi-database", _badge(_e(o["sensitivity"]), "var(--sa-text2)")
            chips += (f"<a href='{href}' style='display:inline-flex;align-items:center;gap:7px;text-decoration:none;"
                      "border:1px solid var(--sa-line);border-radius:9px;padding:7px 11px;background:var(--sa-panel)'>"
                      f"<i class='bi {ic}' style='color:var(--sa-accent-ink)'></i>"
                      f"<span style='color:var(--sa-head);font-weight:600;font-size:12.5px'>{_e(o['name'])}</span>{tail}</a>")
        owns_panel = f"<div style='display:flex;flex-wrap:wrap;gap:10px'>{chips}</div>"
    else:
        owns_panel = _empty("ничего не владеет")

    # активность (аудит) — действия самого актора
    act_items = ""
    for a in card.get("activity", []):
        acol = _LVL_COL.get(a.get("lvl"), "var(--sa-text2)")
        act_items += (
            "<div style='display:flex;gap:12px;align-items:baseline;padding:4px 0;border-top:1px solid var(--sa-line)'>"
            f"<span class='sa-mono' style='color:var(--sa-muted);font-size:11.5px;white-space:nowrap'>{_e(a['t'])}</span>"
            f"<span style='color:{acol};font-size:12px'>{_e(a.get('label') or a['action'])}</span>"
            f"<span class='sa-mono' style='color:var(--sa-muted);font-size:10px'>{_e(a['action'])}</span>"
            f"<span class='sa-mono' style='color:var(--sa-text2);font-size:11px'>{_e(a['obj'])}</span></div>")
    act_panel = (f"<div class='sa-panel' style='padding:6px 16px 10px;max-height:280px;overflow:auto'>{act_items}</div>"
                 if act_items else _empty("действий в аудите нет"))

    body = (
        _eye("Sirius Argus · карточка пользователя")
        + _back_link("/users", "Реестр пользователей")
        + f"<h1 class='sa-h1' style='display:inline'>{_e(acct)}</h1> "
        + f"<span style='margin-left:6px'>{_badge(_e(role), 'var(--sa-accent-ink)')} {_badge(_e(status), scol)}</span>"
        + f"<p class='sa-sub'>актор <span class='sa-mono'>{_e(card['actor'])}</span> · «кто что делал»: "
          "активность, инциденты причастности, решения и владение в одном месте.</p>"
        + _kpi_grid([
            _kpi("Действий", k.get("audit", 0)),
            _kpi("Инцидентов", k.get("incidents", 0)),
            _kpi("Открытых", k.get("open", 0), accent=("var(--sa-alert)" if k.get("open") else "")),
            _kpi("Решений", k.get("decisions", 0)),
            _kpi("Владеет", k.get("owns", 0)),
        ])
        + (_alertbar("alert", f"Причастен к открытым инцидентам: <b>{_e(k.get('open'))}</b> "
                     "(critical/high). Подробности — в блоке «Инциденты» ниже.")
           if k.get("open") else "")
        + _section("Инциденты (причастность)", inc_panel)
        + _section("Решения", dec_panel)
        + _section("Владеет", owns_panel)
        + _section("Активность (аудит)", act_panel)
    )
    return _page(f"Sirius Argus — {acct}", body, "users", crumb=acct)
