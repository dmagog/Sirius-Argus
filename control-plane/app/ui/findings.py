"""ui.findings — журнал сработок (дизайн-язык SA в рамках общего sidebar)."""
from .layout import _e, _page


def findings_page(kpi, status="", severity=""):
    """Журнал сработок: KPI + фильтры по статусу + live-таблица. Триаж — через API (VIS-04)."""
    kpis = (
        f"<div class='sa-kpi'><div class='l'>Всего сработок</div><div class='v'>{kpi.get('total', 0)}</div></div>"
        f"<div class='sa-kpi' style='border-color:var(--sa-warn)'><div class='l'>Open</div>"
        f"<div class='v' style='color:var(--sa-warn)'>{kpi.get('open', 0)}</div><div class='s'>в триаж-очереди</div></div>"
        f"<div class='sa-kpi' style='border-color:var(--sa-alert)'><div class='l'>TP · подтверждённые</div>"
        f"<div class='v' style='color:var(--sa-alert)'>{kpi.get('TP', 0)}</div></div>"
        f"<div class='sa-kpi'><div class='l'>FP · ложные</div><div class='v'>{kpi.get('FP', 0)}</div></div>"
    )
    chips = ""
    for label, val in (("все", ""), ("open", "open"), ("triaged", "triaged"), ("TP", "TP"), ("FP", "FP")):
        on = " on" if val == status else ""
        href = "/findings" if not val else f"/findings?status={_e(val)}"
        chips += f"<a class='sa-chip2{on}' href='{href}'>{_e(label)}</a>"
    params = []
    if status:
        params.append(f"status={_e(status)}")
    if severity:
        params.append(f"severity={_e(severity)}")
    qs = ("?" + "&".join(params)) if params else ""
    body = (
        "<div class='sa-eye'>Sirius Argus · контроль сработок</div>"
        "<h1 class='sa-h1'>Сработки</h1>"
        "<p class='sa-sub'>Полный журнал сработок сканеров и рантайма. Триаж (смена статуса) — VIS-04: "
        "выполняет MLSecOps через API; статус здесь обновляется live. Клик по шапке столбца — сортировка.</p>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin-top:16px'>"
        f"{kpis}</div>"
        f"<div style='display:flex;flex-wrap:wrap;gap:8px;margin:16px 0'>{chips}</div>"
        f"<div class='sa-panel' hx-get='/ui/findings/list{qs}' hx-trigger='load, every 5s'>"
        "<div style='padding:18px;color:var(--sa-muted)'>загрузка…</div></div>"
    )
    return _page("Sirius Argus — сработки", body, "findings")
