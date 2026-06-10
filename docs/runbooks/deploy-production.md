# Рунбук: боевой деплой Sirius Argus (production)

Основная инструкция по выносу платформы в боевой контур. В отличие от
[демо-стенда](deploy-netangels.md), здесь нет сознательных упрощений: реальная аутентификация,
Vault и Keycloak в production-режиме, управляемые секреты, бэкапы, наблюдаемость, единый путь в
прод через CI.

> **Статус готовности.** Базовый `docker-compose.yml` — это dev/local-baseline: Keycloak и Vault в
> нём идут в dev-режиме, часть секретов имеет небезопасные дефолты. Для боевого контура нужен
> отдельный production-overlay и несколько доработок (перечислены в конце, раздел «Что ещё собрать
> в репозитории»). Этот рунбук описывает целевую боевую конфигурацию и шаги до неё, а не
> «`make up` = прод».

---

## Боевой режим против демо: что меняется

| Аспект | Демо-стенд | Боевой контур |
|---|---|---|
| Вход в UI control-plane | Basic Auth или открыто (login-less by design) | Реальный OIDC-вход через auth-proxy (oauth2-proxy + Keycloak) **или** приватная сеть/VPN |
| `/api` | `DEV_AUTH=0`, но засев через временный `DEV_AUTH=1` | `DEV_AUTH=0` всегда; dev-токены недоступны; никакого сид-режима |
| Keycloak | `start-dev`, демо-персоны (логин=пароль) | `start --optimized`, HTTPS, реальные пользователи/федерация, brute-force detection |
| Vault | `server -dev`, фикс. root-токен | `server` с raft/file-storage + TLS + auto-unseal; AppRole; без root-токена в control-plane |
| Секреты | дефолты `change-me-*` / `*-dev` | из секрет-стора/KMS, ротация, **ноль** дефолтных значений |
| Данные | `scripts/demo.py` (синтетика) | реальный ЖЦ моделей через gated-пайплайн; сид не запускается |
| Бэкапы | выключены | Postgres PITR + бэкап объектного стора + снапшоты ВМ; проверка восстановления |
| Сеть | `ufw` 22/80/443, ops на `127.0.0.1` | публично только 443; ops-консоли за SSO + VPN/allowlist; управление через VPN |
| Наблюдаемость | профиль `core` | профиль `full` (Prometheus/Grafana/Loki), алерты, экспорт аудита во внешний WORM/SIEM |
| Доставка | `rsync` + скрипт вручную | единый вход в прод: Gitea + CI (мердж в `main` → деплой), подписанные коммиты, пины образов |

---

## 1. Предпосылки

- **Инфраструктура.** Под профиль `full` заложить ≥16 ГБ RAM / 4–8 vCPU и место под образы и
  данные; Postgres (app/keycloak/mlflow) — либо managed-СУБД, либо отдельные тома с бэкапом.
  Объектный стор — MinIO с durability/versioning или внешний S3-совместимый.
- **Домены и TLS.** Боевой домен с A/AAAA на балансировщик/входной узел. Сертификат — Let's Encrypt
  или корпоративный CA. Отдельные хосты (или пути) для ops-консолей.
- **Секрет-стор / KMS.** Источник секретов и ключ для auto-unseal Vault (облачный KMS или
  Transit). Ни один секрет не хранится в репозитории или в открытом `.env`.
- **Управляющий доступ.** VPN или bastion для SSH/ops; прямой публичный доступ к управлению закрыт.
- **Бэкап-таргет.** Хранилище для дампов БД, версий объектов и снапшотов ВМ (вне боевого узла).

## 2. Архитектура и точки входа

- **Единственная публичная точка** — обратный прокси (Caddy) на 443. Всё остальное — во внутренних
  Docker-сетях. `/metrics` наружу не публикуется.
- **Единый путь в прод** — Gitea + CI (тезис платформы): изменения попадают в боевой контур только
  через мердж в `main` и CI-пайплайн. Прямого `docker compose up` на боевом узле руками — нет.
- **ops-консоли** (Grafana, Gitea, MinIO) — за Keycloak-SSO и недоступны из интернета напрямую
  (VPN/allowlist). MinIO: console-SSO в community-сборках 2025 урезан — доступ к объектам через
  S3/STS, а не веб-консоль под OIDC.

## 3. Идентичность и доступ

- **Keycloak — production.** Перевести с `start-dev --import-realm` на сборку + `start --optimized`;
  `KC_HOSTNAME=https://<домен>/auth`, `KC_PROXY_HEADERS=xforwarded`,
  `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` (за Caddy). Сменить bootstrap-админа
  (`KEYCLOAK_ADMIN_PASSWORD`), **удалить демо-персоны** из realm (`ds/de/mlsecops/product/ceo/bruteme`
  с тривиальными паролями) и завести реальные учётки через федерацию (LDAP/AD/IdP) или admin.
  Включить brute-force detection, разумные TTL токенов, политики паролей.
- **UI control-plane login-less by design.** Сам UI не имеет логина (SSO — у ops-консолей), а
  login-less остаётся пишущий аппрув-гейт `/ui/map/run/...`. В боевом контуре закрыть одним из:
  - **auth-proxy** (oauth2-proxy / Keycloak gatekeeper) перед control-plane: до UI доходят только
    аутентифицированные операторы организации; гейт перестаёт быть публично кликабельным;
  - либо **приватная сеть/VPN** — UI вообще не торчит в интернет.
  Строгий ролевой контроль (`require(...)`, object-level, fail-closed) остаётся на `/api` и работает
  по Keycloak-JWT; `DEV_AUTH=0` гарантирует, что `dev:*`-токены не принимаются.
- **Сервис-аккаунт serving→control-plane.** `SIRIUS_SERVICE_TOKEN` — стойкое значение из
  секрет-стора (не дефолт `svc-serving-local-dev-7f3a9c`); узкая роль `Service` (только
  `runtime.event` / `prod.verify`).
- **Offboarding (ACC-03).** Отзыв субъекта закрывает доступ немедленно — встроить в процесс
  ухода/смены ролей.

## 4. Секреты (Vault в production)

- **Режим Vault.** `server -dev` → `server` с конфигом: storage `raft` (или `file`) на
  персистентном томе, TLS-листенер, **auto-unseal** через облачный KMS/Transit (или manual-unseal с
  раздачей ключей хранителям). Убрать фиксированный root-токен.
- **Доступ control-plane к Vault.** Сейчас control-plane ходит по `VAULT_TOKEN` (= root в dev). В
  проде — **AppRole**: control-plane логинится по role-id/secret-id и получает короткоживущий токен
  с узкой политикой. `vault-init` переписать под создание политик/AppRole вместо dev-сида.
- **Ротация и нулевые дефолты.** Перед go-live проверить, что **ни одна** переменная не осталась
  дефолтной. Ротировать: `KEYCLOAK_ADMIN_PASSWORD`, `MINIO_USER/MINIO_PASSWORD`,
  `CI_WEBHOOK_SECRET`, `SIRIUS_SERVICE_TOKEN`, OIDC-секреты ops-консолей
  (`GRAFANA_OIDC_SECRET`/`GITEA_OIDC_SECRET`/`MINIO_OIDC_SECRET`), `GITEA_ADMIN_PASSWORD`, пароли
  Postgres.
- **`SIGNING_SEED`.** Задать постоянным из секрет-стора: от него зависит подпись моделей, смена
  сломает верификацию уже подписанных версий. Не оставлять пустым/дефолтным.

## 5. Данные и устойчивость

- **Postgres** (app / keycloak / mlflow): managed-СУБД или собственные инстансы с регулярным
  `pg_dump` и WAL/PITR; не на эфемерных томах. Бэкапы — вне боевого узла, с проверкой восстановления.
- **Объектный стор**: versioning + durability (MinIO в режиме с репликацией/erasure или внешний S3);
  бэкап критичных бакетов (артефакты/датасеты/подписи).
- **Без демо-сида.** `scripts/demo.py` в боевом контуре не запускается. Данные появляются только
  через реальный жизненный цикл: приём → скан/gate → ручной аппрув → промоушен → рантайм.

## 6. Сеть и периметр

- **Firewall:** публично только 443. Управление (SSH/ops) — через VPN/bastion. Прямые host-порты
  serving/MinIO/Grafana/Gitea наружу не публикуются.
- **TLS + заголовки.** Реальный сертификат, HSTS и security-заголовки на входном Caddy
  (`Strict-Transport-Security`, `X-Frame-Options`, `X-Content-Type-Options`, `Referrer-Policy`,
  `Content-Security-Policy`, `Permissions-Policy`), потолок тела запроса. `/metrics` — только во
  внутренней сети.
- **Сегментация.** Внутренние сети Docker (`internal`/`runtime`) без egress; наружу смотрит только
  прокси.

## 7. Наблюдаемость и целостность

- **Профиль `full`.** Включить Loki/Promtail/Prometheus/Grafana (`docker compose --profile full`),
  завести алерты (доступность, ошибки авторизации, рост critical-сработок, целостность аудита).
- **Аудит.** Журнал append-only + hash-chain (`audit_chain_ok`) — мониторить целостность цепочки;
  экспортировать аудит во внешний WORM/SIEM, чтобы записи нельзя было затереть на узле.
- **MON-05.** Непрерывная ре-верификация подписи прод-моделей (`/api/prod/verify-signatures`) по
  расписанию от сервис-аккаунта — ловит подмену уже-прод артефакта.

## 8. Доставка и жизненный цикл

- **Единый вход — Gitea + CI.** Боевой контур обновляется только через CI: мердж в `main` →
  пайплайн → деплой на узел. Подписанные коммиты, HMAC-вебхук с реальным `CI_WEBHOOK_SECRET`,
  CODEOWNERS-ревью на защищённой ветке.
- **Образы.** Пины версий и дайджестов (не `latest`), скан образов, подпись; собственные образы
  (control-plane/serving/mlflow) — из доверенного реестра.
- **Миграции и откат.** Миграции БД в пайплайне; снапшот/дамп перед апдейтом; задокументированная
  процедура отката.

## 9. Чек-лист перед go-live

- [ ] `DEV_AUTH=0` (и нигде в проде не включается `1`).
- [ ] Ни одного дефолтного секрета (`change-me-*`, `*-dev`, `*-local`) — все ротированы из стора.
- [ ] Keycloak: `start` (не `start-dev`), демо-персоны удалены, brute-force on, HTTPS-hostname.
- [ ] Vault: production-режим, sealed/auto-unseal, control-plane ходит по AppRole, не по root.
- [ ] UI control-plane закрыт (auth-proxy или приватная сеть); login-less гейт не публичен.
- [ ] TLS с HSTS и security-заголовками; `/metrics` не наружу.
- [ ] Firewall: публично только 443; ops-консоли за SSO + VPN/allowlist.
- [ ] Бэкапы Postgres/объектов настроены и **проверены восстановлением**.
- [ ] Демо-сид не запускался; данные — из реального ЖЦ.
- [ ] Аудит-цепочка цела (`audit_chain_ok`), экспорт в SIEM включён.
- [ ] MON-05 (ре-верификация подписи прода) — по расписанию.

## Что собрано и что осталось (боевой режим)

**Черновой каркас (DRAFT — в репозитории, требует ревью и теста перед go-live):**
- `docker-compose.production.yml` — overlay: Keycloak `start`, Vault `server` с конфигом, oauth2-proxy
  перед UI, без host-портов наружу, restart-политики.
- `infra/vault/vault.prod.hcl` + `infra/vault/vault-init-prod.sh` — Vault raft/TLS/unseal + AppRole-init.
- `infra/reverse-proxy/Caddyfile.production` — HSTS + security-заголовки + `forward_auth` для UI.
- `.env.production.example` — шаблон секретов без дефолтов.

**Сделано в коде/конфиге (статически провалидировано, требует прогона на стейджинге):**
- ✅ **code-change** `control-plane/app/vault.py` — AppRole-логин из env (`VAULT_ROLE_ID`/`VAULT_SECRET_ID`, приоритет над файл-томом) + настраиваемый TLS (`VAULT_SKIP_VERIFY`/`VAULT_CACERT`).
- ✅ `infra/keycloak-prod/realm-sirius-prod.json` — prod-realm без демо-персон и без ROPC (монтируется в `production.yml`).
- ✅ `clients-init.sh` — заводит клиент `sirius-ui` (oauth2-proxy) с redirect по `PUBLIC_HOST` + маппер ролей.
- ✅ `vault-init-prod.sh` — посев секретов (`secret/sirius/*`), политика, AppRole — согласовано с `vault.py`.
- ✅ `production.yml` — oauth2-proxy запрашивает claim `roles` → `X-Auth-Request-Groups`; Caddyfile.production его прокидывает; UI-аппрув (`pages.ui_map_run_decision`) пускает только роль MLSecOps; control-plane ходит в Vault по HTTPS+AppRole; `OIDC_ISSUER` авто из `PUBLIC_HOST`.
- ✅ `make up-prod` — подъём боевого пути (`production.yml --profile full`).

**Осталось операторски (на боевом узле, не из репозитория):**
- TLS-серт prod-Vault (`infra/vault/tls/tls.{crt,key}` — генерация в [tls/README](../../infra/vault/tls/README.md)) и выбранный auto-unseal (KMS) либо ручной unseal с раздачей ключей хранителям.
- Keycloak: образ с `kc.sh build` для `--optimized` (сейчас `start --import-realm` без оптимизации); реальные учётки через федерацию (LDAP/AD/IdP).
- Реальный домен + Let's Encrypt (Caddy выпустит при открытых 80/443 и A-записи); браузерный прогон OIDC-входа через oauth2-proxy.
- `.env.production`: заполнить все `:?`-секреты (вкл. `UI_OIDC_CLIENT_SECRET`, `OAUTH2_PROXY_COOKIE_SECRET=$(openssl rand -base64 32)`, `VAULT_ROLE_ID`/`VAULT_SECRET_ID` из `vault-init-prod.sh`).
- CI-пайплайн деплоя как единый вход в прод; прогон всего каркаса на стейджинге + чек-лист go-live.

## Запуск боевого пути (последовательность)

```sh
# 0. .env.production (из .env.production.example), все секреты из стора; TLS-серт Vault:
openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes \
  -keyout infra/vault/tls/tls.key -out infra/vault/tls/tls.crt -days 825 \
  -subj "/CN=vault" -addext "subjectAltName=DNS:vault,DNS:localhost,IP:127.0.0.1"

# 1. Поднять стек (Vault стартует ЗАпечатанным):
set -a; . ./.env.production; set +a
make up-prod

# 2. Операторский init+unseal Vault (ключи — хранителям, не на узле):
docker compose -f docker-compose.yml -f docker-compose.production.yml exec vault vault operator init   # сохранить unseal-ключи + root offline
docker compose ... exec vault vault operator unseal   # ×3 порогом

# 3. Завести политику/AppRole/секреты (под операторским VAULT_TOKEN):
docker compose ... exec -e VAULT_TOKEN=<operator> -e SIGNING_SEED=<...> -e SIRIUS_SERVICE_TOKEN=<...> \
  vault sh -c 'sh /vault/init/vault-init-prod.sh'   # выдаст VAULT_ROLE_ID / VAULT_SECRET_ID
# впиши role_id/secret_id в .env.production → пересоздай control-plane:
make up-prod

# 4. Префлайт: /api с dev-токеном → 401; UI требует OIDC; health.vault.secrets_source=vault.
```

> Vault во внутренней сети, наружу не публикуется; `VAULT_SKIP_VERIFY=1` допустим для self-signed,
> но предпочтительно положить CA и задать `VAULT_CACERT`. `vault-init-prod.sh` смонтировать в
> контейнер vault (или запускать с хоста с `VAULT_ADDR` на узел).

---

См. также: [демо-стенд на NetAngels](deploy-netangels.md) — одноразовый публичный показ (не прод).
