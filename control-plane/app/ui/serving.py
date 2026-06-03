"""ui.serving — рендер прод-периметра (дизайн-язык SA, в рамках общего sidebar)."""
from .layout import _e, _page


# тяжесть рантайм-сработки → цвет токена SA (для бейджа вердикта)
_SEV_COL = {
    "critical": "var(--sa-alert)", "high": "var(--sa-warn)", "medium": "var(--sa-warn)",
    "low": "var(--sa-text2)", "info": "var(--sa-muted)",
}
# статус сработки → цвет токена SA
_ST_COL = {
    "open": "var(--sa-warn)", "triaged": "var(--sa-blue)",
    "TP": "var(--sa-alert)", "FP": "var(--sa-muted)",
}
# стадия деплоя модели → цвет токена SA
_STAGE_COL = {
    "prod": "var(--sa-ok)", "dev": "var(--sa-blue)", "retired": "var(--sa-muted)",
}
# критичность модели → цвет токена SA
_CRIT_COL = {
    "regulatory": "var(--sa-alert)", "financial": "var(--sa-warn)", "internal": "var(--sa-text2)",
}


def _badge(text, col):
    """sa-badge с инлайн-цветом токена SA и полупрозрачным фоном того же тона."""
    bg = f"color-mix(in srgb, {col} 16%, transparent)"
    return f"<span class='sa-badge' style='color:{col};background:{bg}'>{_e(text)}</span>"


def serving_page(deployments, kpi):
    """Прод-сервинг как окно видимости control-plane: активные деплойменты, рантайм-защиты
    периметра и live-сработки. Сам инференс — отдельный serving-API (:8001), это не страница."""
    last = kpi.get("last", "—")
    rt = kpi.get("runtime_findings", 0)
    kpis = (
        f"<div class='sa-kpi'><div class='l'>Деплойментов</div>"
        f"<div class='v' style='color:var(--sa-ok)'>{kpi.get('deployments', 0)}</div>"
        f"<div class='s'>активно в проде</div></div>"
        f"<div class='sa-kpi'{(' style=border-color:var(--sa-alert)' if rt else '')}>"
        f"<div class='l'>Рантайм-сработок</div>"
        f"<div class='v'{(' style=color:var(--sa-alert)' if rt else '')}>{rt}</div>"
        f"<div class='s'>на периметре эндпоинтов</div></div>"
        f"<div class='sa-kpi'><div class='l'>Последняя</div>"
        f"<div class='v' style='font-size:18px;color:{'var(--sa-warn)' if last != '—' else 'var(--sa-muted)'}'>{_e(last)}</div>"
        f"<div class='s'>свежий вердикт периметра</div></div>"
        f"<div class='sa-kpi'><div class='l'>Защит активно</div>"
        f"<div class='v'>8</div><div class='s'>рантайм-контролей</div></div>"
    )
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
    drows = "".join(
        "<tr>"
        f"<td class='sa-mono' style='color:var(--sa-accent-ink);font-size:11.5px;white-space:nowrap'>{_e(tag)}</td>"
        f"<td style='color:var(--sa-text)'>{_e(name)}</td>"
        f"<td style='color:var(--sa-text2)'>{_e(desc)}</td>"
        f"<td style='text-align:center;color:var(--sa-ok)'><i class='bi bi-shield-check'></i></td></tr>"
        for tag, name, desc in defenses
    )
    defs_table = ("<div class='sa-panel'><table class='sa-table'><thead><tr>"
                  "<th>контроль</th><th>защита</th><th>сценарий</th>"
                  "<th style='text-align:center'>статус</th>"
                  f"</tr></thead><tbody>{drows}</tbody></table></div>")

    if deployments:
        rows = ""
        for d in deployments:
            stage_col = _STAGE_COL.get(d["stage"], "var(--sa-text2)")
            crit_col = _CRIT_COL.get(d["criticality"], "var(--sa-text2)")
            rows += (
                "<tr>"
                f"<td style='color:var(--sa-text);font-weight:600'>{_e(d['model'])}</td>"
                f"<td style='color:var(--sa-text2)'>{_e(d['type'])}</td>"
                f"<td class='sa-mono' style='color:var(--sa-text2)'>v{_e(d['version'])}</td>"
                f"<td>{_badge(d['stage'], stage_col)}</td>"
                f"<td>{_badge(d['criticality'], crit_col)}</td></tr>")
        deps_block = ("<div class='sa-panel'><table class='sa-table'><thead><tr>"
                      "<th>модель</th><th>тип</th><th>версия</th><th>стадия</th><th>критичность</th>"
                      f"</tr></thead><tbody>{rows}</tbody></table></div>")
    else:
        deps_block = ("<div class='sa-panel'><div style='padding:18px;color:var(--sa-muted);font-size:13px'>"
                      "активных деплойментов пока нет — пройди "
                      "<span class='sa-mono' style='color:var(--sa-text2)'>make pipeline</span> "
                      "или промоутни версию в прод</div></div>")

    body = (
        "<div class='sa-eye'>Sirius Argus · прод-периметр сервинга</div>"
        "<h1 class='sa-h1'>Сервинг</h1>"
        "<p class='sa-sub'>Инференс отдаёт отдельный serving-API "
        "(<a class='sa-mono' style='color:var(--sa-accent-ink);text-decoration:none' "
        "href='http://localhost:8001/models' target=_blank rel=noopener>:8001/models <i class='bi bi-box-arrow-up-right'></i></a>) — "
        "это API, не страница. Здесь — единое окно видимости: что в проде, какие рантайм-защиты "
        "сторожат периметр и какие сработки они дали.</p>"
        "<div style='display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px;margin:16px 0'>"
        f"{kpis}</div>"
        "<div class='sa-eye' style='margin-top:8px'>Рантайм-защиты периметра</div>"
        f"{defs_table}"
        "<div class='sa-eye' style='margin-top:22px'>Задеплоено в прод</div>"
        f"{deps_block}"
        "<div style='display:flex;align-items:baseline;justify-content:space-between;margin:22px 0 0'>"
        "<div class='sa-eye' style='margin:0'>Рантайм-сработки · live</div>"
        "<a class='sa-mono' style='font-size:11.5px;color:var(--sa-accent-ink);text-decoration:none' "
        "href='/findings'>Все сработки <i class='bi bi-arrow-right'></i></a></div>"
        "<div class='sa-panel' style='margin-top:10px' hx-get='/ui/serving/runtime' hx-trigger='load, every 5s'>"
        "<div style='padding:18px;color:var(--sa-muted)'>загрузка…</div></div>"
    )
    return _page("Sirius Argus — сервинг", body, "serving")


def serving_runtime_fragment(findings):
    """HTMX-фрагмент: рантайм-сработки сервинга (endpoint-findings), live."""
    if not findings:
        return ("<div style='padding:18px;color:var(--sa-muted);font-size:13px'>"
                "<i class='bi bi-shield-check' style='color:var(--sa-ok)'></i> "
                "рантайм-сработок пока нет — периметр спокоен</div>")
    rows = ""
    for f in findings:
        sev_col = _SEV_COL.get(f["severity"], "var(--sa-text2)")
        st_col = _ST_COL.get(f["status"], "var(--sa-text2)")
        rows += (
            "<tr>"
            f"<td class='sa-mono' style='color:var(--sa-muted);font-size:11.5px;white-space:nowrap'>{_e(f['ts'])}</td>"
            f"<td>{_badge(f['verdict'], sev_col)}</td>"
            f"<td class='sa-mono' style='color:var(--sa-text2);font-size:11.5px'>{_e(f['asset'])}</td>"
            f"<td style='color:var(--sa-text2)'>{_e(f['detail'])}</td>"
            f"<td>{_badge(f['status'], st_col)}</td></tr>")
    return ("<table class='sa-table'><thead><tr>"
            "<th>время</th><th>вердикт</th><th>эндпоинт</th><th>детали</th><th>статус</th>"
            f"</tr></thead><tbody>{rows}</tbody></table>")
