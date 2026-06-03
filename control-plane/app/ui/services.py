"""ui.services — карта сервисов системы (дизайн-язык SA)."""
from .layout import _e, _page

# профиль/SSO-пометки → инлайн-цвета поверх .sa-badge
_BLUE = "color:#38bdf8;background:rgba(56,189,248,.14)"        # core
_VIOLET = "color:#c4b5fd;background:rgba(196,181,253,.14)"     # full
_OK = "color:var(--sa-ok);background:rgba(16,185,129,.14)"     # SSO
_MUTED = "color:var(--sa-muted);background:rgba(100,116,139,.12)"  # внутр. / прочее


def services_page():
    """Карта сервисов системы: внешние (для людей, кликабельно) и внутренние
    (наружу не торчат — zero-trust, доступ только через control-plane, ADR-0005)."""
    # (имя, иконка bi-*, назначение, url, профиль core|full, тег)
    external = [
        ("Control-plane", "bi-diagram-3", "Хаб видимости и единая точка входа для людей",
         "http://localhost:8080/", "core", "вы здесь"),
        ("Keycloak", "bi-person-badge", "Identity · OIDC-логин · роли (DS/DE/MLSecOps/Product/CEO)",
         "http://localhost:8080/auth/admin/", "core", "IdP"),
        ("Serving API", "bi-cpu", "Инференс 3 моделей за рантайм-защитами — это API, не страница",
         "http://localhost:8001/models", "core", "API"),
        ("Grafana", "bi-graph-up", "Observability: логи (Loki) + метрики (Prometheus) · вход через Keycloak",
         "http://localhost:3000/", "full", "SSO"),
        ("Gitea", "bi-git", "Локальный git + CI — единая точка входа в прод · вход через Keycloak",
         "http://localhost:3001/", "full", "SSO"),
        ("MinIO", "bi-hdd-stack", "Объектный стор: артефакты/датасеты · консоль root (OIDC — на S3-STS)",
         "http://localhost:9001/", "core", "ops"),
    ]
    # (имя, иконка bi-*, назначение, порт)
    internal = [
        ("MLflow", "bi-box-seam", "Бэкенд реестра/трекинга: версии, гиперпараметры, артефакты", ":5000"),
        ("Vault", "bi-safe2", "Секрет-менеджмент: выдача по AppRole + аудит", ":8200"),
        ("Postgres · Redis", "bi-database", "Метаданные/аудит (hash-chain) · шина событий", "—"),
    ]

    def _prof(p):
        st = _BLUE if p == "core" else _VIOLET
        return f"<span class='sa-badge sa-mono' style='{st}'>{_e(p)}</span>"

    def _tag(t):
        if not t:
            return ""
        st = _OK if t == "SSO" else _MUTED
        return f" <span class='sa-badge sa-mono' style='{st}'>{_e(t)}</span>"

    def _ico(i):
        return f"<i class='bi {i}' style='color:var(--sa-text2);margin-right:7px'></i>"

    erows = ""
    for name, ico, desc, url, p, tag in external:
        erows += (
            "<tr>"
            f"<td style='color:var(--sa-text);white-space:nowrap'>{_ico(ico)}<b>{_e(name)}</b>{_tag(tag)}</td>"
            f"<td style='color:var(--sa-text2)'>{_e(desc)}</td>"
            f"<td><a class='sa-mono' style='color:var(--sa-blue);font-size:11.5px;text-decoration:none;white-space:nowrap' "
            f"href='{_e(url)}' target='_blank' rel='noopener'>{_e(url)} <i class='bi bi-box-arrow-up-right'></i></a></td>"
            f"<td style='text-align:center'>{_prof(p)}</td></tr>")
    etable = (
        "<div class='sa-panel'><table class='sa-table'><thead><tr>"
        "<th>сервис</th><th>назначение</th><th>адрес</th><th style='text-align:center'>профиль</th>"
        f"</tr></thead><tbody>{erows}</tbody></table></div>")

    irows = "".join(
        "<tr>"
        f"<td style='color:var(--sa-text);white-space:nowrap'>{_ico(ico)}<b>{_e(name)}</b></td>"
        f"<td style='color:var(--sa-text2)'>{_e(desc)}</td>"
        f"<td class='sa-mono' style='color:var(--sa-muted);font-size:11.5px'>{_e(port)}</td>"
        f"<td style='text-align:center'><span class='sa-badge sa-mono' style='{_MUTED}'>"
        "<i class='bi bi-shield-lock'></i> внутр. · zero-trust</span></td></tr>"
        for name, ico, desc, port in internal)
    itable = (
        "<div class='sa-panel'><table class='sa-table'><thead><tr>"
        "<th>сервис</th><th>назначение</th><th>порт</th><th style='text-align:center'>доступ</th>"
        f"</tr></thead><tbody>{irows}</tbody></table></div>")

    body = (
        "<div class='sa-eye'>Sirius Argus · карта сервисов</div>"
        "<h1 class='sa-h1'>Сервисы системы</h1>"
        "<p class='sa-sub'>Карта всех сервисов платформы. <b>Внешние</b> открываются по ссылке. "
        "<b>Внутренние</b> наружу не торчат намеренно — доступ к ним только через control-plane "
        "(zero-trust, ADR-0005). Сервисы профиля <span class='sa-mono'>full</span> поднимаются "
        "командой <span class='sa-mono'>make up-full</span>.</p>"
        "<div class='sa-eye' style='margin-top:22px'>внешние — для людей</div>"
        f"{etable}"
        "<div class='sa-eye' style='margin-top:22px'>внутренние — только через control-plane</div>"
        f"{itable}")
    return _page("Sirius Argus — сервисы", body, "services")
