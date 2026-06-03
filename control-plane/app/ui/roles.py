"""ui.roles — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card


def roles_page(permissions, roles):
    roles = sorted(roles)
    head = "".join(f"<th class='px-3 py-2 text-center'>{_e(r)}</th>" for r in roles)
    rows = ""
    for action in sorted(permissions):
        allowed = permissions[action]
        cells = "".join(
            f"<td class='px-3 py-1.5 text-center'>{'✅' if r in allowed else '·'}</td>" for r in roles)
        rows += f"<tr class='border-t border-slate-100'><td class='px-3 py-1.5 font-mono text-xs'>{_e(action)}</td>{cells}</tr>"
    table = ("<table class='w-full text-sm bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>"
             "<thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
             f"<tr><th class='px-3 py-2 text-left'>действие</th>{head}</tr></thead><tbody>{rows}</tbody></table>")
    body = ("<h1 class='text-xl font-semibold'>Матрица прав (zero-trust RBAC)</h1>"
            "<p class='text-sm text-slate-500'>Кто что может. Object-level (по чувствительности) и separation of duties — поверх этой матрицы.</p>"
            f"{table}")
    return _page("Sirius Argus — роли", body, "roles")
