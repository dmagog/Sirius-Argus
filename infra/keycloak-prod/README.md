# Прод-realm Keycloak (AUD-01)

Этот каталог монтируется в Keycloak вместо `../keycloak/` на боевом пути
(`docker-compose.prod.yml` / `docker-compose.production.yml`). Отличия от dev-realm:

- **Нет демо-персон** `ds/de/mlsecops/product/ceo/bruteme` с паролем = логину. В dev они
  нужны тестам (ROPC-логин в pytest-bdd), в проде — это закоммиченные в публичный репозиторий
  рабочие учётки (включая security-роль `mlsecops`), то есть прямой захват API.
- **Клиент `sirius` не выпускает токены по паролю**: `directAccessGrantsEnabled=false`,
  `standardFlowEnabled=false`, `publicClient=false`, без wildcard-redirect. ROPC закрыт в корне.
- `sslRequired=external` (вместо `none`).

Имя realm — то же (`sirius`), поэтому `KEYCLOAK_JWKS_URL` control-plane менять не нужно.

## Когда понадобится реальный вход операторов

Для пути с SSO в UI (`docker-compose.production.yml` + oauth2-proxy) заведите confidential-клиент
`sirius-ui` (redirect `/oauth2/callback`) и источник пользователей (федерация LDAP/AD или внешний
IdP) — здесь они намеренно не зашиты, чтобы realm не нёс статичных учёток. ops-консоли
(Grafana/Gitea/MinIO) подключаются как и в dev — через `keycloak-init` (Admin API), не из этого файла.

> Импорт срабатывает только при первом старте Keycloak (пустая БД). `deploy_netangels.sh`
> авто-`down -v` не делает (это ручная подсказка в выводе скрипта/рунбуке). На уже
> инициализированной БД realm не переимпортируется автоматически; чтобы переимпортировать,
> оператор вручную выполняет `docker compose -f docker-compose.yml -f docker-compose.prod.yml down -v`.
