"""ui.serving — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card


def serving_page(deployments, kpi):
    """Прод-сервинг как окно видимости control-plane: активные деплойменты, рантайм-защиты
    периметра и live-сработки. Сам инференс — отдельный serving-API (:8001), это не страница."""
    last = kpi.get("last", "—")
    cards = (_card("Деплойментов", kpi.get("deployments", 0), "text-emerald-600")
             + _card("Рантайм-сработок", kpi.get("runtime_findings", 0),
                     "text-red-600" if kpi.get("runtime_findings") else "text-slate-900")
             + _card("Последняя", last, "text-orange-600" if last != "—" else "text-slate-400")
             + _card("Защит активно", "8"))
    defenses = [
        ("RT-01", "Extraction-детект", "бёрст одного клиента → 429 + Finding"),
        ("DOS-01", "Load-shedding", "распределённый флуд → 503, ядро живо"),
        ("DOW-01", "Стоимостная квота", "бюджет тенанта исчерпан → 429"),
        ("RT-05", "Валидация входа", "malformed → 422, сервис не падает"),
        ("RT-02", "OOD / adversarial", "вход-выброс → suspect + Finding"),
        ("MON-01", "Дрейф данных", "сдвиг распределения окна → Finding"),
        ("RT-03/04", "Output-reduction", "отдаём класс, не вероятности (анти-inversion)"),
        ("RT-06", "Сетевая сегментация", "serving→MLflow/MinIO по per-service кредам"),
    ]
    defs = "".join(
        "<div class='bg-white rounded-xl shadow-sm border border-slate-200 p-3 flex gap-2.5 items-start'>"
        "<span class='text-emerald-500'>✅</span><div>"
        f"<div class='text-sm font-medium'>{_e(name)} "
        f"<span class='font-mono text-[10px] text-slate-400'>{_e(tag)}</span></div>"
        f"<div class='text-xs text-slate-500'>{_e(desc)}</div></div></div>"
        for tag, name, desc in defenses
    )
    if deployments:
        drows = "".join(
            "<tr class='border-t border-slate-100'>"
            f"<td class='px-3 py-1.5 font-medium'>{_e(d['model'])}</td>"
            f"<td class='px-3 py-1.5 text-slate-500'>{_e(d['type'])}</td>"
            f"<td class='px-3 py-1.5'>v{_e(d['version'])}</td>"
            f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_STAGE.get(d['stage'], 'bg-slate-100')}'>{_e(d['stage'])}</span></td>"
            f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_CRIT.get(d['criticality'], 'bg-slate-100 text-slate-600')}'>{_e(d['criticality'])}</span></td></tr>"
            for d in deployments
        )
        dtable = ("<table class='w-full text-sm bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>"
                  "<thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
                  "<tr><th class='px-3 py-2 text-left'>модель</th><th class='px-3 py-2 text-left'>тип</th>"
                  "<th class='px-3 py-2 text-left'>версия</th><th class='px-3 py-2 text-left'>стадия</th>"
                  f"<th class='px-3 py-2 text-left'>критичность</th></tr></thead><tbody>{drows}</tbody></table>")
    else:
        dtable = ("<div class='p-4 text-slate-400 bg-white rounded-xl border border-slate-200'>"
                  "активных деплойментов пока нет — пройди <span class='font-mono text-xs'>make pipeline</span> "
                  "или промоутни версию в прод</div>")
    body = (
        "<h1 class='text-xl font-semibold'>Сервинг — прод-периметр</h1>"
        "<p class='text-sm text-slate-500'>Инференс отдаёт отдельный serving-API "
        "(<a class='text-sky-600 hover:underline font-mono text-xs' href='http://localhost:8001/models' target=_blank rel=noopener>:8001/models ↗</a>) — "
        "это API, не страница. Здесь — единое окно видимости: что в проде, какие рантайм-защиты "
        "сторожат периметр и какие сработки они дали.</p>"
        f"<div class='grid grid-cols-2 md:grid-cols-4 gap-3'>{cards}</div>"
        "<section><h2 class='font-semibold mb-2'>Рантайм-защиты периметра</h2>"
        f"<div class='grid grid-cols-1 md:grid-cols-2 gap-3'>{defs}</div></section>"
        f"<section><h2 class='font-semibold mb-2'>Задеплоено в прод</h2>{dtable}</section>"
        "<section><div class='flex items-baseline justify-between mb-2'>"
        "<h2 class='font-semibold'>Рантайм-сработки (live)</h2>"
        "<a class='text-sm text-sky-600 hover:underline' href='/findings'>Все сработки →</a></div>"
        "<div hx-get='/ui/serving/runtime' hx-trigger='load, every 5s' "
        "class='bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>загрузка…</div></section>"
    )
    return _page("Sirius Argus — сервинг", body, "serving")


def serving_runtime_fragment(findings):
    """HTMX-фрагмент: рантайм-сработки сервинга (endpoint-findings), live."""
    if not findings:
        return "<div class='p-4 text-slate-400'>рантайм-сработок пока нет — периметр спокоен</div>"
    rows = "".join(
        "<tr class='border-t border-slate-100 align-top'>"
        f"<td class='px-3 py-1.5 text-slate-400 whitespace-nowrap'>{_e(f['ts'])}</td>"
        f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_SEV.get(f['severity'], 'bg-slate-100')}'>{_e(f['verdict'])}</span></td>"
        f"<td class='px-3 py-1.5 font-mono text-xs'>{_e(f['asset'])}</td>"
        f"<td class='px-3 py-1.5 text-slate-500'>{_e(f['detail'])}</td>"
        f"<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs {_STATUS.get(f['status'], 'bg-slate-100')}'>{_e(f['status'])}</span></td></tr>"
        for f in findings
    )
    return ("<table class='w-full text-sm'><thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
            "<tr><th class='px-3 py-2 text-left'>время</th><th class='px-3 py-2 text-left'>вердикт</th>"
            "<th class='px-3 py-2 text-left'>эндпоинт</th><th class='px-3 py-2 text-left'>детали</th>"
            f"<th class='px-3 py-2 text-left'>статус</th></tr></thead><tbody>{rows}</tbody></table>")
