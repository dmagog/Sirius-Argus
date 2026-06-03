"""ui.findings — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card


def findings_page(kpi, status="", severity=""):
    """Журнал сработок: KPI + фильтры по статусу + live-таблица. Триаж — через API (VIS-04)."""
    cards = (_card("Всего", kpi.get("total", 0))
             + _card("Open", kpi.get("open", 0), "text-amber-600")
             + _card("TP · подтв.", kpi.get("TP", 0), "text-red-600")
             + _card("FP · ложные", kpi.get("FP", 0)))
    chips = ""
    for label, val in (("все", ""), ("open", "open"), ("triaged", "triaged"), ("TP", "TP"), ("FP", "FP")):
        active = (val == status)
        cls = ("bg-slate-900 text-white" if active
               else "bg-white text-slate-600 border border-slate-200 hover:bg-slate-100")
        href = "/findings" if not val else f"/findings?status={_e(val)}"
        chips += f"<a class='px-3 py-1 rounded-full text-xs {cls}' href='{href}'>{_e(label)}</a>"
    params = []
    if status:
        params.append(f"status={_e(status)}")
    if severity:
        params.append(f"severity={_e(severity)}")
    qs = ("?" + "&".join(params)) if params else ""
    body = ("<h1 class='text-xl font-semibold'>Сработки</h1>"
            "<p class='text-sm text-slate-500'>Полный журнал сработок сканеров и рантайма. "
            "Триаж (смена статуса) — VIS-04: выполняет MLSecOps через API; статус здесь обновляется live.</p>"
            f"<div class='grid grid-cols-2 md:grid-cols-4 gap-3'>{cards}</div>"
            f"<div class='flex flex-wrap gap-2'>{chips}</div>"
            f"<div hx-get='/ui/findings/list{qs}' hx-trigger='load, every 5s' "
            "class='bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>загрузка…</div>")
    return _page("Sirius Argus — сработки", body, "findings")
