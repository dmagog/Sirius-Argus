"""Веб-UI control-plane: Tailwind (CDN) + HTMX (CDN) — без сборки фронта.

Чистые функции рендера: дашборд с live-обновлением сработок/аудита, RBAC-матрица ролей,
карта покрытия. Эндпоинты в main.py отдают эти страницы/фрагменты. Дашборд — read-only
ops-консоль (как и раньше, без логина; API /api/* — под authN/RBAC).
"""
import html

_CDN = ('<script src="https://cdn.tailwindcss.com"></script>'
        '<script src="https://unpkg.com/htmx.org@2.0.3"></script>')

# Пульсирующая подложка под аватар-герб (Tailwind на CDN — кастомную анимацию задаём
# своим CSS). Светлый круг + дышащее золотое свечение; уважает prefers-reduced-motion.
_STYLE = (
    "<style>"
    "@keyframes siriusPulse{"
    "0%,100%{box-shadow:0 0 3px 1px rgba(250,204,21,.20);transform:scale(1)}"
    "50%{box-shadow:0 0 9px 3px rgba(250,204,21,.45);transform:scale(1.04)}}"
    ".sirius-badge{background:radial-gradient(circle at 50% 45%,rgba(248,250,252,.30) 0%,rgba(226,232,240,.12) 60%,rgba(226,232,240,0) 100%);"
    "animation:siriusPulse 5.2s ease-in-out infinite}"
    "@media(prefers-reduced-motion:reduce){.sirius-badge{animation:none}}"
    "</style>"
)

_SEV = {
    "critical": "bg-red-100 text-red-700", "high": "bg-orange-100 text-orange-700",
    "medium": "bg-amber-100 text-amber-700", "low": "bg-slate-100 text-slate-600",
    "info": "bg-slate-100 text-slate-500",
}

_STATUS = {
    "open": "bg-amber-100 text-amber-700", "triaged": "bg-sky-100 text-sky-700",
    "TP": "bg-red-100 text-red-700", "FP": "bg-slate-200 text-slate-500",
}

_CRIT = {
    "regulatory": "bg-red-100 text-red-700", "financial": "bg-orange-100 text-orange-700",
    "internal": "bg-slate-100 text-slate-600",
}

_STAGE = {
    "prod": "bg-emerald-100 text-emerald-700", "dev": "bg-sky-100 text-sky-700",
    "retired": "bg-slate-200 text-slate-500",
}


def _e(s):
    return html.escape(str(s if s is not None else ""))


# Разделы навигации (ключ = активная вкладка). Сервинг — внешний контур (И4),
# поэтому отдельной ссылкой, а не вкладкой каркаса.
_NAV = (
    ("/", "Дашборд", "dashboard"),
    ("/registry", "Реестр", "registry"),
    ("/findings", "Сработки", "findings"),
    ("/coverage", "Карта покрытия", "coverage"),
    ("/serving", "Сервинг", "serving"),
    ("/services", "Сервисы", "services"),
    ("/roles", "Роли (RBAC)", "roles"),
)


def _page(title, body, nav="dashboard"):
    def link(href, label, key):
        cls = ("bg-slate-700 text-white" if key == nav
               else "text-slate-300 hover:text-white hover:bg-slate-800")
        return f'<a class="px-2.5 py-1 rounded-md transition-colors {cls}" href="{href}">{label}</a>'
    tabs = "".join(link(h, l, k) for h, l, k in _NAV)
    return (
        "<!doctype html><html lang=ru><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title>"
        "<link rel=icon type=image/png href='/static/avatar.png'>"
        f"{_CDN}{_STYLE}</head>"
        "<body class='bg-slate-50 text-slate-800'>"
        "<header class='bg-slate-900 text-white px-6 py-3 shadow sticky top-0 z-20 "
        "flex flex-wrap items-center gap-x-5 gap-y-2'>"
        "<a href='/' class='flex items-center gap-2 font-bold tracking-wide hover:opacity-90'>"
        "<span class='sirius-badge relative inline-flex h-8 w-8 items-center justify-center rounded-full'>"
        "<img src='/static/avatar.png' alt='Sirius Argus' width=28 height=28 class='relative h-7 w-7'>"
        "</span>"
        "<span>Sirius Argus</span></a>"
        f"<nav class='flex flex-wrap gap-1 text-sm'>{tabs}</nav></header>"
        f"<main class='max-w-6xl mx-auto p-6 space-y-6'>{body}</main></body></html>"
    )


def _card(label, value, accent="text-slate-900"):
    return (f"<div class='bg-white rounded-xl shadow-sm border border-slate-200 p-4'>"
            f"<div class='text-xs uppercase tracking-wide text-slate-400'>{_e(label)}</div>"
            f"<div class='text-2xl font-semibold {accent}'>{_e(value)}</div></div>")


def dashboard(kpi):
    chain = kpi.get("audit_chain_ok")
    cards = (
        _card("Покрытие (live)", kpi.get("coverage", "—"))
        + _card("Сработки", kpi.get("findings_total", 0))
        + _card("Блокировки", kpi.get("blocked_attempts", 0), "text-red-600")
        + _card("Отказы доступа", kpi.get("access_denied", 0))
        + _card("Модели · прод", f"{kpi.get('models', 0)} · {kpi.get('prod_deployments', 0)}")
        + _card("Аудит цел", "да" if chain else "НЕТ", "text-emerald-600" if chain else "text-red-600")
    )
    body = (
        "<h1 class='text-xl font-semibold'>Дашборд безопасности</h1>"
        f"<div class='grid grid-cols-2 md:grid-cols-6 gap-3'>{cards}</div>"
        "<section><div class='flex items-baseline justify-between mb-2'>"
        "<h2 class='font-semibold'>Сработки (live)</h2>"
        "<a class='text-sm text-sky-600 hover:underline' href='/findings'>Все сработки →</a></div>"
        "<div hx-get='/ui/findings' hx-trigger='load, every 5s' "
        "class='bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>загрузка…</div></section>"
        "<section><h2 class='font-semibold mb-2'>Аудит-таймлайн (append-only, hash-chain)</h2>"
        "<div hx-get='/ui/audit' hx-trigger='load, every 5s' "
        "class='bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>загрузка…</div></section>"
    )
    return _page("Sirius Argus — дашборд", body, "dashboard")


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


def services_page():
    """Карта сервисов системы: внешние (для людей, кликабельно) и внутренние
    (наружу не торчат — zero-trust, доступ только через control-plane, ADR-0005)."""
    external = [
        ("Control-plane", "Хаб видимости и единая точка входа для людей", "http://localhost:8080/", "core", "вы здесь"),
        ("Keycloak", "Identity · OIDC-логин · роли (DS/DE/MLSecOps/Product/CEO)", "http://localhost:8080/auth/", "core", ""),
        ("Serving API", "Инференс 3 моделей за рантайм-защитами — это API, не страница", "http://localhost:8001/models", "core", "API"),
        ("Grafana", "Observability: логи (Loki) + метрики (Prometheus)", "http://localhost:3000/", "full", ""),
        ("Gitea", "Локальный git + CI — единая точка входа в прод", "http://localhost:3001/", "full", ""),
    ]
    internal = [
        ("MLflow", "Бэкенд реестра/трекинга: версии, гиперпараметры, артефакты", ":5000"),
        ("MinIO", "Объектный стор: артефакты моделей и датасеты", ":9001"),
        ("Vault", "Секрет-менеджмент: выдача по AppRole + аудит", ":8200"),
        ("Postgres · Redis", "Метаданные/аудит (hash-chain) · шина событий", "—"),
    ]

    def _prof(p):
        cls = "bg-sky-100 text-sky-700" if p == "core" else "bg-violet-100 text-violet-700"
        return f"<span class='px-2 py-0.5 rounded text-xs {cls}'>{_e(p)}</span>"

    erows = ""
    for name, desc, url, p, tag in external:
        chip = (f" <span class='px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 text-[10px]'>{_e(tag)}</span>"
                if tag else "")
        erows += ("<tr class='border-t border-slate-100 align-top'>"
                  f"<td class='px-3 py-1.5 font-medium'>{_e(name)}{chip}</td>"
                  f"<td class='px-3 py-1.5 text-slate-500'>{_e(desc)}</td>"
                  f"<td class='px-3 py-1.5'><a class='text-sky-600 hover:underline font-mono text-xs' "
                  f"href='{_e(url)}' target=_blank rel=noopener>{_e(url)} ↗</a></td>"
                  f"<td class='px-3 py-1.5'>{_prof(p)}</td></tr>")
    etable = ("<table class='w-full text-sm bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>"
              "<thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
              "<tr><th class='px-3 py-2 text-left'>сервис</th><th class='px-3 py-2 text-left'>назначение</th>"
              "<th class='px-3 py-2 text-left'>адрес</th><th class='px-3 py-2 text-left'>профиль</th>"
              f"</tr></thead><tbody>{erows}</tbody></table>")
    irows = "".join(
        "<tr class='border-t border-slate-100 align-top'>"
        f"<td class='px-3 py-1.5 font-medium'>{_e(name)}</td>"
        f"<td class='px-3 py-1.5 text-slate-500'>{_e(desc)}</td>"
        f"<td class='px-3 py-1.5 font-mono text-xs text-slate-400'>{_e(port)}</td>"
        "<td class='px-3 py-1.5'><span class='px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-600'>внутр. · zero-trust</span></td></tr>"
        for name, desc, port in internal)
    itable = ("<table class='w-full text-sm bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden'>"
              "<thead class='bg-slate-50 text-slate-500 text-xs uppercase'>"
              "<tr><th class='px-3 py-2 text-left'>сервис</th><th class='px-3 py-2 text-left'>назначение</th>"
              "<th class='px-3 py-2 text-left'>порт</th><th class='px-3 py-2 text-left'>доступ</th>"
              f"</tr></thead><tbody>{irows}</tbody></table>")
    body = ("<h1 class='text-xl font-semibold'>Сервисы системы</h1>"
            "<p class='text-sm text-slate-500'>Карта всех сервисов платформы. <b>Внешние</b> открываются по ссылке. "
            "<b>Внутренние</b> наружу не торчат намеренно — доступ к ним только через control-plane "
            "(zero-trust, ADR-0005). Сервисы профиля <span class='font-mono text-xs'>full</span> поднимаются "
            "<span class='font-mono text-xs'>make up-full</span>.</p>"
            f"<section><h2 class='font-semibold mb-2'>Внешние — для людей</h2>{etable}</section>"
            f"<section><h2 class='font-semibold mb-2'>Внутренние — только через control-plane</h2>{itable}</section>")
    return _page("Sirius Argus — сервисы", body, "services")
