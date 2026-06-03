"""ui.fragments — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card


def findings_fragment(findings):
    if not findings:
        return "<div class='p-4 text-slate-400'>сработок пока нет</div>"
    rows = "".join(
        "<tr class='border-t border-slate-100'>"
        f"<td class='px-3 py-1.5 text-slate-400'>{_e(f['ts'])}</td>"
        f"<td class='px-3 py-1.5'>{_e(f['tool'])}</td>"
        f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_SEV.get(f['severity'], 'bg-slate-100')}'>{_e(f['verdict'])}</span></td>"
        f"<td class='px-3 py-1.5'>{_e(f['asset'])}</td>"
        f"<td class='px-3 py-1.5 text-xs text-slate-500'>{_e(f['status'])}</td></tr>"
        for f in findings
    )
    return ("<table class='w-full text-sm'><thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
            "<tr><th class='px-3 py-2 text-left'>время</th><th class='px-3 py-2 text-left'>инструмент</th>"
            "<th class='px-3 py-2 text-left'>вердикт</th><th class='px-3 py-2 text-left'>актив</th>"
            f"<th class='px-3 py-2 text-left'>статус</th></tr></thead><tbody>{rows}</tbody></table>")


def audit_fragment(events):
    if not events:
        return "<div class='p-4 text-slate-400'>событий пока нет</div>"
    rows = "".join(
        "<tr class='border-t border-slate-100'>"
        f"<td class='px-3 py-1.5 text-slate-400'>{_e(e.ts)}</td>"
        f"<td class='px-3 py-1.5'>{_e(e.actor)}</td>"
        f"<td class='px-3 py-1.5 font-mono text-xs'>{_e(e.action)}</td>"
        f"<td class='px-3 py-1.5 text-slate-500'>{_e(e.obj)}</td>"
        f"<td class='px-3 py-1.5'>{'<span class=text-emerald-600>ok</span>' if e.was_authorized else '<span class=text-red-600>DENIED</span>'}</td></tr>"
        for e in events
    )
    return ("<table class='w-full text-sm'><thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
            "<tr><th class='px-3 py-2 text-left'>время</th><th class='px-3 py-2 text-left'>актор</th>"
            "<th class='px-3 py-2 text-left'>действие</th><th class='px-3 py-2 text-left'>объект</th>"
            f"<th class='px-3 py-2 text-left'>authz</th></tr></thead><tbody>{rows}</tbody></table>")


def findings_table(findings):
    """Полный список сработок с деталями и статусом (фрагмент для /findings)."""
    if not findings:
        return "<div class='p-4 text-slate-400'>сработок по фильтру нет</div>"
    rows = "".join(
        "<tr class='border-t border-slate-100 align-top'>"
        f"<td class='px-3 py-1.5 text-slate-400 whitespace-nowrap'>{_e(f['ts'])}</td>"
        f"<td class='px-3 py-1.5'>{_e(f['tool'])}</td>"
        f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_SEV.get(f['severity'], 'bg-slate-100')}'>{_e(f['verdict'])}</span></td>"
        f"<td class='px-3 py-1.5'>{_e(f['asset'])}</td>"
        f"<td class='px-3 py-1.5 text-slate-500'>{_e(f['detail'])}</td>"
        f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_STATUS.get(f['status'], 'bg-slate-100')}'>{_e(f['status'])}</span></td></tr>"
        for f in findings
    )
    return ("<table class='w-full text-sm'><thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
            "<tr><th class='px-3 py-2 text-left'>время</th><th class='px-3 py-2 text-left'>инструмент</th>"
            "<th class='px-3 py-2 text-left'>вердикт</th><th class='px-3 py-2 text-left'>актив</th>"
            "<th class='px-3 py-2 text-left'>детали</th><th class='px-3 py-2 text-left'>статус</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>")
