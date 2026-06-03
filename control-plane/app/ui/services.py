"""ui.services — рендер (вынесено из ui.py)."""
from .layout import _CDN, _STYLE, _SEV, _STATUS, _CRIT, _STAGE, _e, _NAV, _page, _card


def services_page():
    """Карта сервисов системы: внешние (для людей, кликабельно) и внутренние
    (наружу не торчат — zero-trust, доступ только через control-plane, ADR-0005)."""
    external = [
        ("Control-plane", "Хаб видимости и единая точка входа для людей", "http://localhost:8080/", "core", "вы здесь"),
        ("Keycloak", "Identity · OIDC-логин · роли (DS/DE/MLSecOps/Product/CEO)", "http://localhost:8080/auth/admin/", "core", ""),
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
