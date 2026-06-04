"""ui.fragments — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card


def findings_fragment(findings):
    if not findings:
        return "<div class='p-4 text-slate-400'>сработок пока нет</div>"
    from ..runs import asset_href
    rows = ""
    for f in findings:
        href = asset_href(f.get("asset"))
        asset_cell = (f"<a href='{href}' style='color:var(--sa-blue);text-decoration:none'>{_e(f['asset'])}</a>"
                      if href else _e(f.get("asset", "")))
        rows += (
            "<tr class='border-t border-slate-100'>"
            f"<td class='px-3 py-1.5 text-slate-400'>{_e(f['ts'])}</td>"
            f"<td class='px-3 py-1.5'>{_e(f['tool'])}</td>"
            f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_SEV.get(f['severity'], 'bg-slate-100')}'>{_e(f['verdict'])}</span></td>"
            f"<td class='px-3 py-1.5'>{asset_cell}</td>"
            f"<td class='px-3 py-1.5 text-xs text-slate-500'>{_e(f['status'])}</td></tr>")
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


_F_SEVC = {"critical": "var(--sa-alert)", "high": "#fb923c", "medium": "var(--sa-warn)",
           "low": "var(--sa-muted)", "info": "var(--sa-muted)"}
_F_STC = {"open": ("var(--sa-warn)", "rgba(245,158,11,.16)"), "triaged": ("var(--sa-blue)", "rgba(56,189,248,.16)"),
          "TP": ("var(--sa-alert)", "rgba(239,68,68,.16)"), "FP": ("var(--sa-muted)", "rgba(100,116,139,.16)")}


def findings_table(findings):
    """Полный список сработок (SA-стиль): тяжесть/вердикт, актив, причастный (учётка+роль), статус."""
    if not findings:
        return "<div style='padding:18px;color:var(--sa-muted)'>сработок по фильтру нет</div>"
    from ..runs import asset_href, role_of
    rows = ""
    for f in findings:
        sc = _F_SEVC.get(f["severity"], "var(--sa-muted)")
        col, bg = _F_STC.get(f["status"], ("var(--sa-muted)", "rgba(100,116,139,.16)"))
        acct, role = role_of(f)
        href = asset_href(f.get("asset"))
        asset_cell = (f"<a href='{href}' style='color:var(--sa-blue);text-decoration:none' title='открыть карточку'>"
                      f"{_e(f['asset'])} <i class='bi bi-box-arrow-up-right' style='font-size:9px'></i></a>"
                      if href else _e(f.get("asset", "")))
        rows += (
            "<tr>"
            f"<td class='sa-mono' style='color:var(--sa-muted);white-space:nowrap'>{_e((f['ts'] or '').split('T')[-1][:8])}</td>"
            f"<td class='sa-mono' style='color:var(--sa-text2)'>{_e(f['tool'])}</td>"
            f"<td><span class='sa-badge sa-mono' style='color:{sc};background:rgba(148,163,184,.12)'>{_e(f['severity'])}</span> "
            f"<span class='sa-mono' style='color:{sc};font-weight:600'>{_e(f['verdict'])}</span></td>"
            f"<td class='sa-mono' style='color:var(--sa-text2);font-size:11.5px'>{asset_cell}</td>"
            f"<td style='color:var(--sa-text2);max-width:420px'>{_e(f['detail'])}</td>"
            f"<td class='sa-mono' style='font-size:11px;white-space:nowrap'>{_e(acct)} "
            f"<span style='color:var(--sa-accent-ink);font-weight:600'>{_e(role)}</span></td>"
            f"<td><span class='sa-badge sa-mono' style='color:{col};background:{bg}'>{_e(f['status'])}</span></td></tr>")
    return ("<table class='sa-table'><thead><tr>"
            "<th>время</th><th>инструмент</th><th>вердикт</th><th>актив</th><th>детали</th>"
            "<th>причастен</th><th>статус</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>")
