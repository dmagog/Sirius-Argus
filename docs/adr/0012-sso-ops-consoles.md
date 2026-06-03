# ADR-0012: Единый вход (SSO) в ops-консоли через Keycloak OIDC

- Статус: Accepted (расширяет [ADR-0007](0007-keycloak-authn.md), согласуется с [ADR-0005](0005-fail-closed-protect-enforcer.md))
- Дата: 2026-06-03

## Контекст
Authn пользователей платформы уже идёт через Keycloak ([ADR-0007](0007-keycloak-authn.md)), но **ops-консоли** (Grafana, Gitea, MinIO) логинились отдельно (локальные пароли / визард), а внутренние панели (MLflow, Vault, MinIO) вообще не были доступны наружу — следствие zero-trust и единой точки входа ([ADR-0005](0005-fail-closed-protect-enforcer.md)). Нужно: одна идентичность и роли (DS/DE/MLSecOps/Product/CEO) для операторских инструментов и контролируемый доступ через тот же IdP, **не размывая** zero-trust для секрет-хранилища и сырого tracking.

## Решение
- **Нативный OIDC для Grafana и Gitea** — полноценный вход через Keycloak (realm `sirius`). MinIO-консоль выставлена для ops, но вход root (см. ниже).
- **Клиенты как код, но не в realm-файле.** OIDC-клиентов (`grafana`/`gitea`/`minio`) + мапперы ролей заводит сервис `keycloak-init` через Admin API (`kcadm`, `infra/keycloak/clients-init.sh`) **идемпотентно**. Realm уже импортирован в БД Keycloak, и правка `realm-sirius.json` на него не влияет без вайпа — Admin-API-подход применяет клиентов к живому realm и не конфликтует с владельцем realm-файла.
- **Keycloak за единым входом (Caddy).** `KC_HTTP_RELATIVE_PATH=/auth` + `KC_HOSTNAME=http://localhost:8080/auth` + `KC_HOSTNAME_BACKCHANNEL_DYNAMIC=true` дают split-horizon discovery: браузер идёт на `localhost:8080/auth` (через Caddy), сервисы-контейнеры обращаются к `keycloak:8080/auth` за token/jwks. Обязательно для discovery-клиентов (Gitea/MinIO).
- **MLflow и Vault — НЕ выставляем.** Остаются zero-trust: доступ только через control-plane. Секрет-хранилище и сырой artifact/tracking наружу не торчат сознательно — это часть тезиса, а не недоработка. Сеть `internal` — Docker-`internal` (без хоста); чтобы выставить сервис, его добавляют в сеть `edge`.

## Последствия
- (+) Одна идентичность и роли для ops-инструментов; админ-доступ через единый IdP с аудитом Keycloak; zero-trust для секретов сохранён; клиенты идемпотентны и переживают ре-импорт realm.
- (−) Тоньше конфиг Keycloak (split-horizon, `KC_HOSTNAME` указывать **с** `/auth`, иначе frontend-URL теряет префикс). Issuer теперь `http://localhost:8080/auth/realms/sirius` — учитывать валидаторам (в control-plane issuer не проверяется, JWKS берётся напрямую).
- (−) **MinIO console-SSO недоступен**: community-образ `RELEASE.2025-09` вырезал OIDC-вход в консоль (`/api/v1/login/oauth2/auth` → 404). OIDC-клиент остаётся валидным для S3-API (STS `AssumeRoleWithWebIdentity`); вход в саму консоль — root. Ограничение апстрима, не конфигурации.

## Альтернативы
- **SSO-gateway** (oauth2-proxy / Caddy `forward_auth`) — один прокси перед всем, покрыл бы и MLflow/Vault/MinIO-консоль, включая сервисы без нативного OIDC. Отклонён сейчас: больше движущихся частей; выбран нативный OIDC как MVP. **Зона роста**, если потребуется единый вход и во внутренние панели.
- Выставить консоли с локальными паролями — отклонено: нет единой авторизации, размывает zero-trust.
- Пин старого образа MinIO ради console-SSO — отклонено: риск совместимости данных и безопасности устаревшего образа; демо-доступ root приемлем.
