"""ui.coverage — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card


def coverage_page(data):
    k = data["kpi"]
    chain = "да" if k.get("audit_chain_ok") else "НЕТ"
    cards = (_card("Покрытие", k.get("coverage", "—"), "text-emerald-600")
             + _card("Сработки", k.get("findings_total", 0))
             + _card("Блокировки", k.get("blocked_attempts", 0), "text-red-600")
             + _card("Аудит цел", chain, "text-emerald-600" if k.get("audit_chain_ok") else "text-red-600"))
    rows = "".join(
        "<tr class='border-t border-slate-100'>"
        f"<td class='px-3 py-1.5 font-mono text-xs'>{_e(c['id'])}</td>"
        f"<td class='px-3 py-1.5'>{_e(c['threat'])}</td>"
        f"<td class='px-3 py-1.5 text-slate-500'>{_e(c['control'])}</td>"
        f"<td class='px-3 py-1.5 text-center'>{'🟢 live' if c['status'] == 'live' else '⚪ ready'} ({c['evidence']})</td></tr>"
        for c in data["controls"]
    )
    table = ("<table class='w-full text-sm bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>"
             "<thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
             "<tr><th class='px-3 py-2 text-left'>сценарий</th><th class='px-3 py-2 text-left'>угроза</th>"
             "<th class='px-3 py-2 text-left'>контроль</th><th class='px-3 py-2 text-left'>статус</th></tr>"
             f"</thead><tbody>{rows}</tbody></table>")
    body = ("<h1 class='text-xl font-semibold'>Карта покрытия угроз — CEO-вью</h1>"
            f"<div class='grid grid-cols-2 md:grid-cols-4 gap-3'>{cards}</div>{table}"
            "<p class='text-xs text-slate-400'>Статус «live» — реальные сработки/блокировки в аудите по этому контролю. "
            "Карта отражает <b>детективные</b> контроли (дают сработку). <b>Превентивные</b> "
            "(output-reduction <code>RT-03/04</code>, сетевая сегментация рантайма <code>RT-06</code>, "
            "fail-closed authN, separation of duties) проверяются приёмочными тестами и не порождают сработок.</p>")
    return _page("Sirius Argus — карта покрытия", body, "coverage")
