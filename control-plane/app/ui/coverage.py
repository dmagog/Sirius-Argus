"""ui.coverage — карта покрытия угроз (CEO-вью), дизайн-язык SA."""
from .layout import _e, _page


def coverage_page(data):
    """Угроза → контроль → live-статус по реальным сработкам/блокировкам в аудите (VIS-01)."""
    k = data["kpi"]
    chain_ok = k.get("audit_chain_ok")
    chain_col = "var(--sa-ok)" if chain_ok else "var(--sa-alert)"
    kpis = (
        f"<div class='sa-kpi'><div class='l'>Покрытие контролей</div>"
        f"<div class='v' style='color:var(--sa-ok)'>{_e(k.get('coverage', '—'))}</div><div class='s'>live / всего</div></div>"
        f"<div class='sa-kpi'><div class='l'>Сработок</div><div class='v'>{k.get('findings_total', 0)}</div></div>"
        f"<div class='sa-kpi' style='border-color:var(--sa-alert)'><div class='l'>Блокировок</div>"
        f"<div class='v' style='color:var(--sa-alert)'>{k.get('blocked_attempts', 0)}</div></div>"
        f"<div class='sa-kpi' style='border-color:{chain_col}'><div class='l'>Аудит-цепочка</div>"
        f"<div class='v' style='color:{chain_col};font-size:19px;display:flex;align-items:center;gap:8px'>"
        f"<i class='bi {'bi-shield-check' if chain_ok else 'bi-shield-exclamation'}'></i>{'цела' if chain_ok else 'НАРУШЕНА'}</div></div>"
    )
    rows = ""
    for c in data["controls"]:
        live = c["status"] == "live"
        col = "var(--sa-ok)" if live else "var(--sa-muted)"
        bg = "rgba(16,185,129,.14)" if live else "rgba(100,116,139,.12)"
        badge = (f"<span class='sa-badge sa-mono' style='color:{col};background:{bg}'>"
                 f"<i class='bi {'bi-broadcast' if live else 'bi-circle'}'></i> {'live' if live else 'ready'} · {c['evidence']}</span>")
        rows += (
            "<tr>"
            f"<td class='sa-mono' style='color:var(--sa-accent-ink);font-size:11.5px;white-space:nowrap'>{_e(c['id'])}</td>"
            f"<td style='color:var(--sa-text)'>{_e(c['threat'])}</td>"
            f"<td style='color:var(--sa-text2)'>{_e(c['control'])}</td>"
            f"<td style='text-align:center'>{badge}</td></tr>")
    table = ("<div class='sa-panel'><table class='sa-table'><thead><tr>"
             "<th>сценарий</th><th>угроза</th><th>контроль</th><th style='text-align:center'>статус</th>"
             f"</tr></thead><tbody>{rows}</tbody></table></div>")
    body = (
        "<div class='sa-eye'>Sirius Argus · карта покрытия угроз</div>"
        "<h1 class='sa-h1'>Карта покрытия — CEO-вью</h1>"
        "<p class='sa-sub'>Угроза → контроль → live-статус по реальным сработкам и блокировкам в аудите. "
        "Клик по шапке столбца — сортировка.</p>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0'>"
        f"{kpis}</div>{table}"
        "<p class='sa-sub' style='margin-top:14px'>Статус «live» — реальные сработки/блокировки в аудите по контролю. "
        "Карта отражает <b>детективные</b> контроли (дают сработку). <b>Превентивные</b> "
        "(output-reduction <span class='sa-mono'>RT-03/04</span>, сетевая сегментация <span class='sa-mono'>RT-06</span>, "
        "fail-closed authN, separation of duties) проверяются приёмочными тестами и не порождают сработок.</p>"
    )
    return _page("Sirius Argus — карта покрытия", body, "coverage")
