"""ui.dashboard — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card


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
