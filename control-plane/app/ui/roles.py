"""ui.roles — матрица прав RBAC (дизайн-язык SA в рамках общего sidebar)."""
from .layout import _e, _page


def roles_page(permissions, roles):
    """Матрица прав zero-trust RBAC: строки — действия, столбцы — роли, ✓ — доступ."""
    roles = sorted(roles)
    head = "".join(
        f"<th class='sa-mono' style='text-align:center;color:var(--sa-accent-ink)'>{_e(r)}</th>"
        for r in roles)
    rows = ""
    for action in sorted(permissions):
        allowed = permissions[action]
        cells = ""
        for r in roles:
            if r in allowed:
                cell = "<i class='bi bi-check2' style='color:var(--sa-ok);font-size:15px'></i>"
            else:
                cell = "<span style='color:var(--sa-muted)'>—</span>"
            cells += f"<td style='text-align:center'>{cell}</td>"
        rows += (
            "<tr>"
            f"<td class='sa-mono' style='color:var(--sa-text);white-space:nowrap'>{_e(action)}</td>"
            f"{cells}</tr>")
    table = (
        "<div class='sa-panel'><table class='sa-table'><thead><tr>"
        f"<th>действие</th>{head}"
        f"</tr></thead><tbody>{rows}</tbody></table></div>")
    body = (
        "<div class='sa-eye'>Sirius Argus · zero-trust RBAC</div>"
        "<h1 class='sa-h1'>Матрица прав</h1>"
        "<p class='sa-sub'>Кто какое действие может выполнить. Единый источник правды по доступам. "
        "Object-level (по чувствительности артефакта) и separation of duties — поверх этой матрицы.</p>"
        f"<div style='margin-top:16px'>{table}</div>"
    )
    return _page("Sirius Argus — роли", body, "roles")
