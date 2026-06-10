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

## AUD-04 · Промоушен не-критичных моделей (решение по политике)

Сейчас `internal`-модели промоутятся без подписи/аппрува (by design — light-touch), а критичность
самоназначается при регистрации. Полностью закрыть AUD-04 = политическое решение:
- либо выводить критичность из источника/датасета (не самоназначение),
- либо требовать подпись + verify-on-consume по сохранённым байтам для **любого** прод-промоушена.

Второе ломает текущий контракт тестов (`internal` версии создаются без артефакта). Внедрять с
осознанным обновлением `test_promote_atomic`/`test_approval_gate` и прогоном `make up-test && make test`.
Уже сделано безопасно: `/versions` не принимает клиентский ярлык `signature` (только `/sign`).
