"""ui.dashboard — read-only ops-консоль: KPI + live-сработки/аудит (дизайн-язык SA)."""
from .layout import _e, _page


def dashboard(kpi):
    """Дашборд безопасности: KPI + live-таблица сработок + аудит-таймлайн (HTMX, every 5s)."""
    chain_ok = kpi.get("audit_chain_ok")
    chain_col = "var(--sa-ok)" if chain_ok else "var(--sa-alert)"
    kpis = (
        f"<div class='sa-kpi'><div class='l'>Покрытие</div>"
        f"<div class='v' style='color:var(--sa-ok)'>{_e(kpi.get('coverage', '—'))}</div><div class='s'>live / всего</div></div>"
        f"<div class='sa-kpi'><div class='l'>Сработки</div><div class='v'>{kpi.get('findings_total', 0)}</div></div>"
        f"<div class='sa-kpi' style='border-color:var(--sa-alert)'><div class='l'>Блокировки</div>"
        f"<div class='v' style='color:var(--sa-alert)'>{kpi.get('blocked_attempts', 0)}</div></div>"
        f"<div class='sa-kpi' style='border-color:var(--sa-warn)'><div class='l'>Отказы доступа</div>"
        f"<div class='v' style='color:var(--sa-warn)'>{kpi.get('access_denied', 0)}</div></div>"
        f"<div class='sa-kpi'><div class='l'>Модели · прод</div>"
        f"<div class='v'>{kpi.get('models', 0)} · {kpi.get('prod_deployments', 0)}</div></div>"
        f"<div class='sa-kpi' style='border-color:{chain_col}'><div class='l'>Аудит-цепочка</div>"
        f"<div class='v' style='color:{chain_col};font-size:19px;display:flex;align-items:center;gap:8px'>"
        f"<i class='bi {'bi-shield-check' if chain_ok else 'bi-shield-exclamation'}'></i>"
        f"{'цела' if chain_ok else 'НАРУШЕНА'}</div></div>"
    )
    body = (
        "<div class='sa-eye'>Sirius Argus · ops-консоль</div>"
        "<h1 class='sa-h1'>Дашборд безопасности</h1>"
        "<p class='sa-sub'>Read-only обзор контура: KPI покрытия, живые сработки и аудит-таймлайн. "
        "Данные обновляются автоматически каждые 5 секунд. Триаж и изменения — через API под authN/RBAC.</p>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0'>"
        f"{kpis}</div>"
        "<div style='display:flex;align-items:baseline;justify-content:space-between;margin:22px 0 10px'>"
        "<h2 class='sa-h1' style='font-size:17px;margin:0'><i class='bi bi-broadcast'></i> Сработки · live</h2>"
        "<a class='sa-mono' style='color:var(--sa-blue);text-decoration:none;font-size:12.5px' href='/findings'>"
        "Все сработки <i class='bi bi-arrow-right'></i></a></div>"
        "<div class='sa-panel' hx-get='/ui/findings' hx-trigger='load, every 5s'>"
        "<div style='padding:18px;color:var(--sa-muted)'>загрузка…</div></div>"
        "<h2 class='sa-h1' style='font-size:17px;margin:22px 0 10px'>"
        "<i class='bi bi-link-45deg'></i> Аудит-таймлайн "
        "<span class='sa-mono' style='color:var(--sa-muted);font-size:12px;font-weight:400'>append-only · hash-chain</span></h2>"
        "<div class='sa-panel' hx-get='/ui/audit' hx-trigger='load, every 5s'>"
        "<div style='padding:18px;color:var(--sa-muted)'>загрузка…</div></div>"
    )
    return _page("Sirius Argus — дашборд", body, "dashboard")
