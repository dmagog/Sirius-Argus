"""ui.users — реестр пользователей/акторов (дизайн-язык SA)."""
from urllib.parse import quote

from .layout import _e, _page

# роль → цвет (люди и сервис-акторы)
_ROLE_COL = {"MLSecOps": "var(--sa-accent-ink)", "CEO": "var(--sa-alert)", "Product": "#fb923c",
             "DE": "var(--sa-blue)", "DS": "var(--sa-blue)", "Service": "var(--sa-muted)"}


def _role_badge(role):
    col = _ROLE_COL.get(role, "var(--sa-text2)")
    return (f"<span class='sa-badge' style='color:{col};"
            f"background:color-mix(in srgb,{col} 15%,transparent)'>{_e(role)}</span>")


def users_page(rows, kpi):
    """Реестр акторов: люди и сервис-аккаунты, собранные из аудита/findings/решений/владения.
    Для каждого — роль и счётчики активности и инцидентов. Клик по актору — карточка."""
    kpis = (
        f"<div class='sa-kpi'><div class='l'>Акторов</div><div class='v'>{_e(kpi.get('users', 0))}</div>"
        "<div class='s'>люди + сервис-аккаунты</div></div>"
        f"<div class='sa-kpi'{' style=border-color:var(--sa-alert)' if kpi.get('with_incidents') else ''}>"
        "<div class='l'>С инцидентами</div>"
        f"<div class='v'{' style=color:var(--sa-alert)' if kpi.get('with_incidents') else ''}>{_e(kpi.get('with_incidents', 0))}</div>"
        "<div class='s'>откр. critical/high</div></div>"
        f"<div class='sa-kpi'><div class='l'>Принимали решения</div><div class='v'>{_e(kpi.get('decision_makers', 0))}</div>"
        "<div class='s'>аппрув-гейт / риск</div></div>"
        f"<div class='sa-kpi'><div class='l'>Владельцев</div><div class='v'>{_e(kpi.get('owners', 0))}</div>"
        "<div class='s'>моделей / датасетов</div></div>"
    )

    if not rows:
        table = ("<div class='sa-panel' style='padding:18px;color:var(--sa-muted)'>"
                 "акторов пока нет</div>")
    else:
        trs = ""
        for r in rows:
            href = "/users/" + quote(r["actor"], safe="")
            open_cell = (f"<span class='sa-mono' style='color:var(--sa-alert);font-weight:700'>● {_e(r['open'])}</span>"
                         if r.get("open") else "<span style='color:var(--sa-muted)'>—</span>")
            dec_cell = (f"<span class='sa-mono'>{_e(r['decisions'])}</span>" if r.get("decisions")
                        else "<span style='color:var(--sa-muted)'>—</span>")
            owns_cell = (f"<span class='sa-mono'>{_e(r['owns'])}</span>" if r.get("owns")
                         else "<span style='color:var(--sa-muted)'>—</span>")
            trs += (
                "<tr>"
                f"<td><a href='{href}' style='color:var(--sa-head);font-weight:600;text-decoration:none'>"
                f"{_e(r['account'])} <i class='bi bi-arrow-right-short' style='color:var(--sa-muted)'></i></a></td>"
                f"<td>{_role_badge(r['role'])}</td>"
                f"<td class='sa-mono' style='color:var(--sa-text2)'>{_e(r['audit'])}</td>"
                f"<td class='sa-mono' style='color:var(--sa-text2)'>{_e(r['findings'])}</td>"
                f"<td>{open_cell}</td>"
                f"<td>{dec_cell}</td>"
                f"<td>{owns_cell}</td>"
                f"<td class='sa-mono' style='color:var(--sa-muted);font-size:11px;white-space:nowrap'>{_e(r['last'])}</td></tr>")
        table = ("<div class='sa-panel'><table class='sa-table'><thead><tr>"
                 "<th>актор</th><th>роль</th><th>действий</th><th>инцидентов</th><th>открытых</th>"
                 "<th>решений</th><th>владеет</th><th>посл. активность</th>"
                 f"</tr></thead><tbody>{trs}</tbody></table></div>")

    body = (
        "<div class='sa-eye'>Sirius Argus · реестр пользователей</div>"
        "<h1 class='sa-h1'>Пользователи и акторы</h1>"
        "<p class='sa-sub'>Все акторы контура — люди (DS/DE/MLSecOps/Product/CEO) и сервис-аккаунты "
        "(serving, CI, control-plane) — собранные из аудита, сработок, решений и владения. "
        "По каждому видно роль и активность; клик по актору — карточка «кто что делал»: "
        "его действия, инциденты причастности, решения и что он владеет.</p>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0'>"
        f"{kpis}</div>{table}"
    )
    return _page("Sirius Argus — пользователи", body, "users")
