"""ui.registry — реестр моделей (дизайн-язык SA в рамках общего sidebar)."""
from .layout import _e, _page


# Стадии жизненного цикла версии: цвет через токены SA.
_STAGE_COL = {
    "prod": "var(--sa-ok)",
    "staging": "var(--sa-warn)",
    "dev": "var(--sa-blue)",
    "retired": "var(--sa-muted)",
}
# Критичность модели: regulatory — alert, financial — оранж, internal — приглушённый.
_CRIT_COL = {
    "regulatory": "var(--sa-alert)",
    "financial": "#fb923c",
    "internal": "var(--sa-muted)",
}


def _stage_badge(stage):
    col = _STAGE_COL.get(stage, "var(--sa-text2)")
    return (f"<span class='sa-badge sa-mono' "
            f"style='color:{col};background:color-mix(in srgb,{col} 15%,transparent)'>"
            f"{_e(stage)}</span>")


def registry_page(models, kpi):
    """Read-only витрина реестра: модели, критичность, версии и стадии."""
    kpis = (
        f"<div class='sa-kpi'><div class='l'>Моделей</div><div class='v'>{kpi.get('models', 0)}</div></div>"
        f"<div class='sa-kpi'><div class='l'>Версий</div><div class='v'>{kpi.get('versions', 0)}</div>"
        "<div class='s'>по всем стадиям</div></div>"
        f"<div class='sa-kpi' style='border-color:var(--sa-ok)'><div class='l'>В проде</div>"
        f"<div class='v' style='color:var(--sa-ok)'>{kpi.get('prod', 0)}</div></div>"
        f"<div class='sa-kpi' style='border-color:var(--sa-alert)'><div class='l'>Критичные</div>"
        f"<div class='v' style='color:var(--sa-alert)'>{kpi.get('critical', 0)}</div>"
        "<div class='s'>regulatory / financial</div></div>"
    )

    if not models:
        table = ("<div class='sa-panel' style='padding:18px;color:var(--sa-muted)'>"
                 "в реестре пока нет моделей</div>")
    else:
        rows = ""
        for m in models:
            crit = m["criticality"]
            crit_col = _CRIT_COL.get(crit, "var(--sa-text2)")
            crit_badge = (f"<span class='sa-badge' "
                          f"style='color:{crit_col};background:color-mix(in srgb,{crit_col} 15%,transparent)'>"
                          f"{_e(crit)}</span>")
            if m["versions"]:
                vers = " ".join(
                    f"<span class='sa-mono' style='font-size:11.5px'>v{_e(v['version'])}</span>"
                    f"&nbsp;{_stage_badge(v['stage'])}" for v in m["versions"])
                vers = f"<div style='display:flex;flex-wrap:wrap;gap:8px;align-items:center'>{vers}</div>"
            else:
                vers = "<span style='color:var(--sa-muted);font-size:12px'>нет версий</span>"
            rows += (
                "<tr>"
                f"<td class='sa-mono' style='color:var(--sa-accent-ink);font-size:11.5px;white-space:nowrap'>{_e(m['id'])}</td>"
                f"<td><a href='/registry/model/{_e(m['id'])}' style='color:var(--sa-head);font-weight:600;text-decoration:none'>{_e(m['name'])} "
                f"<i class='bi bi-arrow-right-short' style='color:var(--sa-muted)'></i></a></td>"
                f"<td>{crit_badge}</td>"
                f"<td>{vers}</td></tr>")
        table = ("<div class='sa-panel'><table class='sa-table'><thead><tr>"
                 "<th>id</th><th>модель</th><th>критичность</th><th>версии · стадии</th>"
                 f"</tr></thead><tbody>{rows}</tbody></table></div>")

    body = (
        "<div class='sa-eye'>Sirius Argus · реестр моделей</div>"
        "<h1 class='sa-h1'>Реестр моделей</h1>"
        "<p class='sa-sub'>Защищённый реестр (zero-trust) поверх обёрнутого MLflow. "
        "Чувствительные операции, lineage и blast-radius — через "
        "<span class='sa-mono' style='color:var(--sa-accent-ink)'>/api/*</span> под RBAC. "
        "Клик по модели — карточка с историей, статусом и проблемами; по шапке столбца — сортировка.</p>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0'>"
        f"{kpis}</div>{table}"
    )
    return _page("Sirius Argus — реестр", body, "registry")
