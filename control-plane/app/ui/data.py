"""ui.data — реестр данных (дизайн-язык SA в рамках общего sidebar)."""
from .layout import _e, _page, _toolbar


# Чувствительность датасета: pii — оранж, secret — alert, open — приглушённый.
_SENS_COL = {
    "pii": "#fb923c",
    "secret": "var(--sa-alert)",
    "open": "var(--sa-muted)",
}
_SEV_COL = {"critical": "var(--sa-alert)", "high": "#fb923c", "medium": "var(--sa-warn)"}


def _sens_badge(sens):
    col = _SENS_COL.get(sens, "var(--sa-text2)")
    return (f"<span class='sa-badge' "
            f"style='color:{col};background:color-mix(in srgb,{col} 15%,transparent)'>"
            f"{_e(sens)}</span>")


def _trust_badge(trusted):
    if trusted:
        col, lbl = "var(--sa-ok)", "доверенный"
    else:
        col, lbl = "var(--sa-alert)", "карантин"
    return (f"<span class='sa-badge' "
            f"style='color:{col};background:color-mix(in srgb,{col} 15%,transparent)'>"
            f"{lbl}</span>")


def _scans_panel(scans):
    """Scoped-сканы качества/целостности данных: сканируют полезную нагрузку, а не
    зарегистрированный датасет (нет id) — поэтому их нет в карточках. Показываем здесь,
    чтобы такие находки оставались видимы и атрибутируемы причастному."""
    rows = ""
    for f in scans:
        sc = _SEV_COL.get(f["severity"], "var(--sa-muted)")
        st_col = "var(--sa-warn)" if f["status"] == "open" else "var(--sa-muted)"
        rows += (
            "<tr>"
            f"<td class='sa-mono' style='color:var(--sa-muted);font-size:11.5px;white-space:nowrap'>{_e(f['ts'])}</td>"
            f"<td style='white-space:nowrap'><span class='sa-badge' style='color:{sc};"
            f"background:color-mix(in srgb,{sc} 15%,transparent)'>{_e(f['severity'])}</span> "
            f"<span class='sa-mono' style='color:{sc};font-weight:600'>{_e(f['verdict'])}</span></td>"
            f"<td class='sa-mono' style='color:var(--sa-text2);font-size:11.5px'>{_e(f['tool'])}</td>"
            f"<td style='color:var(--sa-text2)'>{_e(f['detail'])}</td>"
            f"<td class='sa-mono' style='font-size:11px;white-space:nowrap'>{_e(f['actor'])} "
            f"<span style='color:var(--sa-accent-ink);font-weight:600'>{_e(f['role'])}</span></td>"
            f"<td><span class='sa-badge sa-mono' style='color:{st_col};"
            f"background:color-mix(in srgb,{st_col} 15%,transparent)'>{_e(f['status'])}</span></td></tr>")
    return ("<div class='sa-eye' style='margin-top:26px'>scoped-сканы данных (DATA-02/03/05)</div>"
            "<p class='sa-sub' style='margin:-2px 0 10px'>гейт качества/целостности сканирует "
            "полезную нагрузку, а не конкретный датасет реестра — поэтому находки попадают сюда, "
            "а не в карточку. Привязать к датасету можно, передав <span class='sa-mono'>dataset_id</span> в скан.</p>"
            "<div class='sa-panel'><table class='sa-table'><thead><tr>"
            "<th>время</th><th>severity · вердикт</th><th>инструмент</th><th>детали</th>"
            "<th>причастен</th><th>статус</th>"
            f"</tr></thead><tbody>{rows}</tbody></table></div>")


def data_page(datasets, kpi, scans=None):
    """Read-only витрина реестра данных: датасеты, чувствительность, источник и lineage."""
    scans = scans or []
    quarantined = kpi.get("quarantined", 0)
    open_issues = kpi.get("open", 0)
    scoped = kpi.get("scoped_scans", 0)
    q_border = " style='border-color:var(--sa-alert)'" if quarantined > 0 else ""
    q_val = " style='color:var(--sa-alert)'" if quarantined > 0 else ""
    o_val = "var(--sa-warn)" if open_issues > 0 else "var(--sa-head)"
    kpis = (
        f"<div class='sa-kpi'><div class='l'>Датасетов</div><div class='v'>{kpi.get('datasets', 0)}</div></div>"
        f"<div class='sa-kpi'{q_border}><div class='l'>В карантине</div>"
        f"<div class='v'{q_val}>{quarantined}</div>"
        "<div class='s'>недоверенный источник</div></div>"
        f"<div class='sa-kpi'><div class='l'>С PII</div>"
        f"<div class='v' style='color:#fb923c'>{kpi.get('pii', 0)}</div></div>"
        f"<div class='sa-kpi'><div class='l'>Открытых проблем</div>"
        f"<div class='v' style='color:{o_val}'>{open_issues}</div>"
        "<div class='s'>привязанных к датасету</div></div>"
        f"<div class='sa-kpi'><div class='l'>Scoped-сканы</div>"
        f"<div class='v' style='color:{'var(--sa-warn)' if scoped else 'var(--sa-muted)'}'>{scoped}</div>"
        "<div class='s'>без привязки к датасету</div></div>"
    )

    if not datasets:
        toolbar = ""
        table = ("<div class='sa-panel' style='padding:18px;color:var(--sa-muted)'>"
                 "в реестре данных пока нет датасетов</div>")
    else:
        rows = ""
        for d in datasets:
            did = d["id"]
            name_link = (f"<a href='/data/dataset/{_e(did)}' "
                         "style='color:var(--sa-head);font-weight:600;text-decoration:none'>"
                         f"{_e(d['name'])}</a>")
            src = (f"<div style='display:flex;flex-direction:column;gap:4px'>"
                   f"{_trust_badge(d['trusted'])}"
                   f"<span class='sa-mono' title='{_e(d['source'])}' style='font-size:11px;"
                   f"color:var(--sa-muted);max-width:240px;overflow:hidden;text-overflow:ellipsis;"
                   f"white-space:nowrap'>{_e(d['source'])}</span></div>")
            cols = f"<span class='sa-mono' style='font-size:12px'>{_e(d['columns'])}</span>"
            if d["pii"] > 0:
                cols += (f"&nbsp;<span class='sa-badge' "
                         f"style='color:#fb923c;background:color-mix(in srgb,#fb923c 15%,transparent)'>"
                         f"{_e(d['pii'])} PII</span>")
            if d["open"] > 0:
                issues = (f"<span class='sa-mono' style='color:var(--sa-warn);font-weight:700'>"
                          f"&#9679; {_e(d['open'])}</span>")
            else:
                issues = "<span style='color:var(--sa-muted)'>&mdash;</span>"
            rows += (
                "<tr>"
                f"<td class='sa-mono' style='color:var(--sa-accent-ink);font-size:11.5px;white-space:nowrap'>{_e(did)}</td>"
                f"<td>{name_link}</td>"
                f"<td>{_sens_badge(d['sensitivity'])}</td>"
                f"<td>{src}</td>"
                f"<td class='sa-mono' style='font-size:12px'>{_e(d['versions'])}</td>"
                f"<td>{cols}</td>"
                f"<td style='text-align:center'>{issues}</td>"
                f"<td class='sa-mono' style='font-size:12px'>{_e(d['consumers'])}</td>"
                "</tr>")
        toolbar = _toolbar("reg-data", len(datasets), "датасетов", "поиск по имени, источнику, id…")
        table = ("<div class='sa-scroll'><table id='reg-data' class='sa-table'><thead><tr>"
                 "<th>id</th><th>датасет</th><th>чувствительность</th><th>источник</th>"
                 "<th>версии</th><th>колонки</th><th>проблемы</th><th>потребители</th>"
                 f"</tr></thead><tbody>{rows}</tbody></table></div>")

    scans_block = _scans_panel(scans) if scans else ""

    body = (
        "<div class='sa-eye'>Sirius Argus · реестр данных</div>"
        "<h1 class='sa-h1'>Реестр данных</h1>"
        "<p class='sa-sub'>Реестр цепочки поставки данных: датасеты, их чувствительность, "
        "доверенность источника (<span class='sa-mono' style='color:var(--sa-accent-ink)'>DATA-01</span>), "
        "PII-схема (<span class='sa-mono' style='color:var(--sa-accent-ink)'>DATA-04</span>) и какие "
        "модели на них обучены (lineage). "
        "Клик по датасету — карточка с историей и проблемами; по шапке столбца — сортировка.</p>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0'>"
        f"{kpis}</div>{toolbar}{table}{scans_block}"
    )
    return _page("Sirius Argus — реестр данных", body, "data")
