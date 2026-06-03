"""ui.registry — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card


def registry_page(models, kpi):
    """Read-only витрина реестра: модели, критичность, версии и стадии."""
    cards = (_card("Модели", kpi.get("models", 0))
             + _card("Версии", kpi.get("versions", 0))
             + _card("В проде", kpi.get("prod", 0), "text-emerald-600")
             + _card("Критичные", kpi.get("critical", 0), "text-red-600"))
    if not models:
        table = ("<div class='p-4 text-slate-400 bg-white rounded-xl border border-slate-200'>"
                 "в реестре пока нет моделей</div>")
    else:
        rows = ""
        for m in models:
            crit = _CRIT.get(m["criticality"], "bg-slate-100 text-slate-600")
            if m["versions"]:
                vers = " ".join(
                    f"<span class='px-1.5 py-0.5 rounded text-xs {_STAGE.get(v['stage'], 'bg-slate-100')}'>"
                    f"v{_e(v['version'])}·{_e(v['stage'])}</span>" for v in m["versions"])
            else:
                vers = "<span class='text-slate-400 text-xs'>нет версий</span>"
            rows += (
                "<tr class='border-t border-slate-100 align-top'>"
                f"<td class='px-3 py-1.5 text-slate-400'>{_e(m['id'])}</td>"
                f"<td class='px-3 py-1.5 font-medium'>{_e(m['name'])}</td>"
                f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {crit}'>{_e(m['criticality'])}</span></td>"
                f"<td class='px-3 py-1.5 space-x-1'>{vers}</td></tr>")
        table = ("<table class='w-full text-sm bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>"
                 "<thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
                 "<tr><th class='px-3 py-2 text-left'>id</th><th class='px-3 py-2 text-left'>модель</th>"
                 "<th class='px-3 py-2 text-left'>критичность</th><th class='px-3 py-2 text-left'>версии · стадии</th>"
                 f"</tr></thead><tbody>{rows}</tbody></table>")
    body = ("<h1 class='text-xl font-semibold'>Реестр моделей</h1>"
            "<p class='text-sm text-slate-500'>Защищённый реестр (zero-trust) поверх обёрнутого MLflow. "
            "Чувствительные операции, lineage и blast-radius — через <span class='font-mono text-xs'>/api/*</span> под RBAC.</p>"
            f"<div class='grid grid-cols-2 md:grid-cols-4 gap-3'>{cards}</div>{table}")
    return _page("Sirius Argus — реестр", body, "registry")
