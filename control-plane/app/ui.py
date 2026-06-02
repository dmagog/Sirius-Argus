"""Веб-UI control-plane: Tailwind (CDN) + HTMX (CDN) — без сборки фронта.

Чистые функции рендера: дашборд с live-обновлением сработок/аудита, RBAC-матрица ролей,
карта покрытия. Эндпоинты в main.py отдают эти страницы/фрагменты. Дашборд — read-only
ops-консоль (как и раньше, без логина; API /api/* — под authN/RBAC).
"""
import html

_CDN = ('<script src="https://cdn.tailwindcss.com"></script>'
        '<script src="https://unpkg.com/htmx.org@2.0.3"></script>')

_SEV = {
    "critical": "bg-red-100 text-red-700", "high": "bg-orange-100 text-orange-700",
    "medium": "bg-amber-100 text-amber-700", "low": "bg-slate-100 text-slate-600",
    "info": "bg-slate-100 text-slate-500",
}


def _e(s):
    return html.escape(str(s if s is not None else ""))


def _page(title, body, nav="dashboard"):
    def link(href, label, key):
        cls = "text-white" if key == nav else "text-slate-300 hover:text-white"
        return f'<a class="{cls}" href="{href}">{label}</a>'
    return (
        f"<!doctype html><html lang=ru><head><meta charset=utf-8>"
        f"<meta name=viewport content='width=device-width, initial-scale=1'>"
        f"<title>{_e(title)}</title>{_CDN}</head>"
        "<body class='bg-slate-50 text-slate-800'>"
        "<header class='bg-slate-900 text-white px-6 py-3 flex gap-5 items-center shadow'>"
        "<span class='font-bold tracking-wide'>🐕‍🦺 Sirius Argus</span>"
        "<nav class='flex gap-4 text-sm'>"
        f"{link('/', 'Дашборд', 'dashboard')}{link('/coverage', 'Карта покрытия', 'coverage')}"
        f"{link('/roles', 'Роли (RBAC)', 'roles')}"
        "<a class='text-slate-300 hover:text-white' href='http://localhost:8001/models' target=_blank>Сервинг</a>"
        "</nav></header>"
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
        "<section><h2 class='font-semibold mb-2'>Сработки (live)</h2>"
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
            "<p class='text-xs text-slate-400'>Статус «live» — реальные сработки/блокировки в аудите по этому контролю.</p>")
    return _page("Sirius Argus — карта покрытия", body, "coverage")
