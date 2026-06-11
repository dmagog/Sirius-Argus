# Рунбук: операционные шаги хардненинга (остатки аудита)

> Дополняет [security-audit-remediation.md](../security-audit-remediation.md). Здесь — пункты,
> которые закрываются не правкой кода, а операционным действием при развёртывании. Код/конфиг
> для них уже подготовлены; ниже — что сделать руками на боевом контуре.

## AUD-03/07 · Идентичность и по-ролевое маскирование в UI (oauth2-proxy)

Перевести боевой стенд на путь с SSO в UI вместо login-less + Basic Auth:

1. Развернуть оверлеем `docker-compose.production.yml` + `Caddyfile.production` (там уже есть
   `oauth2-proxy` и `forward_auth`), а не `docker-compose.prod.yml`.
2. Завести в Keycloak confidential-клиент `sirius-ui` (redirect `/oauth2/callback`), задать
   `UI_OIDC_CLIENT_SECRET` и `OAUTH2_PROXY_COOKIE_SECRET` (`openssl rand -base64 32`).
3. Включить проверку токена control-plane: задать `OIDC_AUDIENCE` (= client_id control-plane) и
   `OIDC_ISSUER` (`https://<PUBLIC_HOST>/auth/realms/sirius`) в `.env.production` — **после** сверки,
   что токены реально несут эти aud/iss (иначе все токены отвергнутся).
4. Для полного энфорса роли на UI-аппруве (AUD-03): прокинуть роль/группу через oauth2-proxy
   (`--scope "openid email roles"` + claim → заголовок) и проверять MLSecOps в
   `ui_map_run_decision` (сейчас эндпоинт уже берёт личность из `X-Auth-Request-User`).
5. По-ролевое маскирование PII в UI (AUD-07): применить `can_read_sensitivity` в `cards.py`/UI так
   же, как в `/api/.../schema`, используя роль из forward_auth.

После этого закрываются AUD-03, AUD-07, AUD-29 (UI больше не анонимен и не самозаявлен).

## AUD-08 · control-plane под non-owner ролью БД

Append-only-триггер на `audit_events` уже стоит, но владелец схемы (`sirius`) может его отключить.
В проде приложение должно ходить под ролью без DDL:

```sql
CREATE ROLE sirius_app LOGIN PASSWORD '<из Vault>';
GRANT CONNECT ON DATABASE sirius TO sirius_app;
GRANT USAGE ON SCHEMA public TO sirius_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO sirius_app;
-- но на audit_events — только SELECT/INSERT:
REVOKE UPDATE, DELETE, TRUNCATE ON audit_events FROM sirius_app;
-- владелец таблицы остаётся sirius (миграции/DDL), приложение — sirius_app
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO sirius_app;
```

`DATABASE_URL` control-plane перевести на `sirius_app` (выдаётся через Vault). Тогда даже
скомпрометированный control-plane не сделает `DROP TRIGGER` / `ALTER TABLE ... DISABLE TRIGGER`.
Плюс наладить регулярную сверку отгруженной в Redis/Loki головы hash-chain с БД.

## AUD-09 · Vault в prod-режиме

`docker-compose.prod.yml` не переопределяет Vault → остаётся `server -dev` (память, без TLS, root в env).
Перейти на `docker-compose.production.yml` (там `server -config=/vault/config/vault.prod.hcl`, raft-том)
и выполнить операторский init после unseal:

```
docker compose ... up -d vault
docker compose exec vault vault operator init     # сохранить unseal-ключи offline (KMS/HSM/сейф)
docker compose exec vault vault operator unseal   # x3 порогом
bash infra/vault/vault-init-prod.sh               # политики + AppRole (под scoped-токеном, не root)
```

control-plane логинится в Vault по AppRole (`VAULT_ROLE_ID`/`VAULT_SECRET_ID` из тома `vault_creds`).
Root-токен не передавать в env контейнеров.

## AUD-16 · Лимиты ресурсов контейнеров

`no-new-privileges` уже добавлен control-plane/serving. Для DoS-устойчивости задать лимиты памяти
(пример; подобрать под бокс), напр. в прод-оверлее:

```yaml
control-plane: { mem_limit: 1g, cpus: "1.0" }
serving:       { mem_limit: 1g, cpus: "1.0" }
keycloak:      { mem_limit: 1g }
postgres:      { mem_limit: 512m }
minio:         { mem_limit: 512m }
```

Не ставить в base без проверки под нагрузкой (brute-force/DoS-сценарии не должны ловить OOM-kill).
Дополнительно рассмотреть `read_only: true` + `tmpfs` для stateless-сервисов.

## AUD-18 · promtail без host docker.sock

promtail (profile full) монтирует `/var/run/docker.sock` (= полный Docker API = контроль над хостом).
Заменить на чтение через journald/файловый драйвер, либо проксировать сокет через
`tecnativa/docker-socket-proxy` с whitelist только нужных read-эндпоинтов (CONTAINERS=1, остальное 0).

## AUD-21 · Branch protection

CI-гейт (`.github/workflows/security.yml`) добавлен; включить на GitHub
(`dmagog/Sirius-Argus`, ветка `main`): Settings → Branches → Protection rule → Require status checks
to pass → выбрать `static-security` и `compose-validate`; Require PR before merge.

## Второй заход (исследование «что упустили»)

- **AUD-01 повторный деплой.** `--import-realm` импортирует realm только в ПУСТУЮ БД Keycloak. При
  повторном `deploy_netangels.sh` на существующем томе `kc_pg_data` (где уже dev-realm) прод-realm НЕ
  переимпортируется → тихий регресс. Лечение: на первом прод-запуске форсить чистый старт
  (`docker compose ... rm -sf keycloak keycloak-db && docker volume rm <proj>_kc_pg_data`) или сделать
  импорт идемпотентным (kc admin import при старте). До этого — проверять realm после деплоя.
- **AUD-05 issuer.** `OIDC_ISSUER` известен из `PUBLIC_HOST` — задавать его в `deploy_netangels.sh`
  (`OIDC_ISSUER=https://$PUBLIC_HOST/auth/realms/sirius`) и пробрасывать в control-plane: безопасно
  включает проверку issuer (свои токены не отвергаются). `OIDC_AUDIENCE` — только после сверки `aud`.
- **AUD-11 Object-Lock.** Версионирование (уже включено) спасает от перезаписи, но НЕ от удаления.
  Для неизменяемости — создавать бакет карантина с Object-Lock (COMPLIANCE retention) при первом
  создании; control-plane выдать узкую S3-политику (PutObject/GetObject на префикс), не root MinIO.
- **prod.yml secret-gating.** `docker-compose.prod.yml` не форсит `:?` на секретах → молчаливый фолбэк
  на публичные дефолты (signing-seed `5e1f17a0…`, Vault root, service-token). Перенести `:?`-гейты в
  `prod.yml` (как в `production.yml`) и убрать публичный seed-дефолт из `infra/vault/init.sh`. Либо
  перевести деплой на `production.yml`. Также `REDIS_PASSWORD`/OIDC-секреты — генерировать, не дефолтить.
- **Observability в prod.yml.** Хардненинг Grafana/Gitea (AUD-24) лежит в `production.yml`, а реальный
  деплой идёт через `prod.yml` БЕЗ observability-оверрайдов. Продублировать (ports `!override []`,
  `ALLOW_SIGN_UP=false`, `GRAFANA_PASSWORD:?`, `DISABLE_REGISTRATION`) в `prod.yml`, либо перейти на
  `production.yml`. В base: Grafana биндить на `127.0.0.1:3000` и убрать из сети `edge`.
- **Loki/Promtail.** ✅ Сделано: `infra/observability/loki-config.yml` (filesystem-storage +
  retention 7д) + named volume `loki_data` (раньше логи терялись на рестарте); в promtail добавлены
  `pipeline_stages` redact (Bearer / hvs.* / root-token+unseal / key=value-секреты) — секреты из stdout
  ВСЕХ контейнеров маскируются ДО отправки в Loki (раньше app-фильтр покрывал только control-plane).
  Проверено end-to-end: инъецированный секрет приходит в Loki как `[REDACTED]`.
  Остаток: для критичного аудита Vault лучше отдельный файловый sink, а не stdout→Loki (ниже).
- **MLflow без auth.** ✅ Сделано: `mlflow server --app-name basic-auth --workers 1` (entrypoint
  `infra/mlflow/entrypoint.sh`, креды админа из env `MLFLOW_AUTH_USER/PASSWORD` → в проде из Vault);
  control-plane ходит под Basic Auth (`registry.py`, `MLFLOW_TRACKING_USERNAME/PASSWORD`). Проверено:
  модель пишется (`backend_synced=true`) и читается (`/backend present=true`) с auth, без auth → 401.
  ✅ MLflow-артефакты — отдельный MinIO-юзер `mlflow-svc` с политикой только на `s3://mlflow`
  (`infra/minio/init.sh` + сервис `minio-init`), не root; проверено: юзер имеет доступ к `s3://mlflow`,
  но `s3://sirius-quarantine` запрещён. Остатки: control-plane не доверять MLflow как источнику истины
  о стадии (авторитетен Postgres+аудит); в проде сменить пароль админа MLflow; аналогично дать
  control-plane узкого MinIO-юзера на `sirius-quarantine` вместо root (AUD-11).
- **Vault audit.** `init.sh` шлёт audit в stdout → Loki (каждый read секрета логируется в общий стек).
  В проде — отдельный файловый sink с ограниченным доступом, либо исключить vault из promtail.
- **gitea-data.** `infra/gitea-data/` (SSH host-ключи, JWT/INTERNAL_TOKEN, `gitea.db`) лежит в дереве
  репо (gitignored, но одна `git add -f`/архив от утечки). Вынести в named volume (как `caddy_data`).
- **Зависимости с CVE.** ✅ Закрыто (11.06.2026): согласованный бамп `fastapi 0.115.6 → 0.136.3`
  + явный пин `starlette 1.2.1` (≥1.0.1 закрывает PYSEC-2026-161, GHSA-2c2j-9gv5-cj73, GHSA-7f5h-v6xp-fcq8)
  в control-plane и serving; `pytest 8.3.4 → 9.0.3` (GHSA-6w46-j5rx-g56g / CVE-2025-71176, совместим
  с `pytest-bdd 8.1.0`); pyjwt 2.13.0 (PYSEC-2025-183 ушёл из БД). Все `--ignore-vuln` убраны из
  `.github/workflows/security.yml` — `pip-audit` теперь «No known vulnerabilities found» по всем трём
  requirements, любой новый CVE валит гейт. Проверено `make up-test && make test` (контракт не сломан).

## AUD-04 · Промоушен не-критичных моделей (решение по политике)

Сейчас `internal`-модели промоутятся без подписи/аппрува (by design — light-touch), а критичность
самоназначается при регистрации. Полностью закрыть AUD-04 = политическое решение:
- либо выводить критичность из источника/датасета (не самоназначение),
- либо требовать подпись + verify-on-consume по сохранённым байтам для **любого** прод-промоушена.

Второе ломает текущий контракт тестов (`internal` версии создаются без артефакта). Внедрять с
осознанным обновлением `test_promote_atomic`/`test_approval_gate` и прогоном `make up-test && make test`.
Уже сделано безопасно: `/versions` не принимает клиентский ярлык `signature` (только `/sign`).
