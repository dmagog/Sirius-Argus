# Sirius Argus — аудит безопасности самой платформы и план доработок

> Дата: 2026-06-10. Область: безопасность **самой системы** (периметр, развёртывание, аутентификация, авторизация, секреты, контейнеры, цепочка поставок, целостность), а не моделируемые ML-угрозы — те уже разобраны в [threat-model](threat-model/) и закрыты контролями. Этот документ дополняет [improvements.md](improvements.md) и [risk-register.md](threat-model/risk-register.md): здесь — то, что нашёл прицельный аудит защищённости контура.
>
> Метод: разносторонний разбор по семи направлениям (секреты, аутентификация, авторизация, веб/инъекции, инфраструктура, цепочка поставок, ML/данные/аудит) с независимой адверсариальной перепроверкой каждой находки и ручной сверкой по коду. Серьёзности ниже — **после** перепроверки (часть исходных оценок понижена там, где сработала уже существующая защита).
>
> Роли везде — системные RBAC-акторы (DS, DE, MLSecOps, Product, CEO, Service), не люди.

## Главный вывод

**Прикладной слой защиты — сильный и продуманный.** Подтверждено по коду: zero-trust RBAC с object-level проверками, fail-closed OIDC (подпись RS256, alg запинен — `alg:none` не пройдёт), tamper-evident аудит на hash-chain, скан артефактов без десериализации (`pickletools.genops`, не `pickle.load`), подпись через OpenSSF model-signing, separation of duties на промоушене с привязкой решения к хэшу артефакта (anti-TOCTOU), атомарный промоушен под row-lock, экранирование всего пользовательского ввода в server-rendered UI через `html.escape`, параметризованный SQL (ORM, без строковой склейки), non-root контейнеры, запиненные зависимости. Классических веб-дыр (SQLi, инъекция команд, XSS, небезопасная десериализация) аудит **не нашёл**.

**Дыры — не в коде приложения, а в слое развёртывания публичного стенда.** Жёсткая конфигурация, которую команда уже спроектировала (черновой путь `docker-compose.production.yml` + `Caddyfile.production` + `vault.prod.hcl` + oauth2-proxy), **не подключена к пути, которым реально деплоит `scripts/deploy_netangels.sh`** (`docker-compose.yml` + `docker-compose.prod.yml` + `Caddyfile.prod`). В результате на боевом стенде:

- периметр открыт в интернет без аутентификации (Basic Auth заявлен в скрипте и compose, но **в `Caddyfile.prod` его нет**);
- импортируется демо-realm Keycloak, где у пользователей **пароль равен логину** (включая `mlsecops`), а клиент `sirius` — публичный с включённым ROPC;
- Keycloak и Vault работают в dev-режиме.

Связка даёт **полный обход** заявленной защиты «`/api` заперт через `DEV_AUTH=0`»: токен с ролью MLSecOps выпускается по известным из репозитория учёткам. Это главный приоритет.

Практически весь план Фазы 0–1 — это **подключить уже готовую жёсткую конфигурацию к реальному пути деплоя** и убрать демо-артефакты из боевого контура, а не писать защиту с нуля.

## Статус реализации (2026-06-10)

Правки внесены так, чтобы **не менять дев-поведение и не ломать зелёный pytest-bdd** (тесты
логинятся ROPC по дев-realm и завязаны на дев-дефолты): жёсткие настройки идут отдельным
прод-путём и через env-гейты, по умолчанию выключенные в dev.

**Проверено на живом стеке (Docker 29.4, `docker compose` v5.1.1):**
- `docker compose config -q` — все 6 конфигов валидны (база + test/prod/production/seed/dev).
- Стек поднят целиком (`make up-test`): postgres×3, keycloak (+импорт realm), vault (+init), minio, mlflow, redis, control-plane, serving, reverse-proxy.
- **pytest-bdd: 71 passed, 2 skipped** (skip — `test_sso`, требует профиль `full`; 71+2 = все 73 функции). DOS-02, OIDC/brute-force (ROPC), offboard, CI-вебхук, append-only аудит — зелёные.
- **AUD-20 проверен напрямую:** на стеке с лимитом 2 ГиБ загрузка 30 МиБ (>25 МиБ) → HTTP 422 (дошла до сканера формата), НЕ 413 — реальные модели не блокируются по размеру; на тест-стеке (25 МиБ) 26 МиБ → 413 (DOS-02).

| ID | Статус | Что сделано |
|---|:--:|---|
| AUD-01 | ✅ | `infra/keycloak-prod/realm-sirius-prod.json` без демо-персон и с выключенным ROPC; монтируется в `prod.yml` и `production.yml` |
| AUD-02 | ✅ | `basic_auth` в `Caddyfile.prod` (использует уже пробрасываемые `DEMO_USER`/`DEMO_PASS_HASH`) |
| AUD-03 | 🟡 | UI-аппрув берёт личность из forward_auth (`X-Auth-Request-User`), не из формы (код); смягчено Basic Auth; полный энфорс роли — oauth2-proxy путь ([рунбук](runbooks/security-hardening-ops.md)) |
| AUD-04 | 🟡 | `/versions` больше не доверяет клиентскому ярлыку `signature` (код); политика «гейт и для internal-моделей» — решение + [рунбук](runbooks/security-hardening-ops.md) |
| AUD-05 | ✅ | `auth.py`: проверка `aud`/`iss` при заданных `OIDC_AUDIENCE`/`OIDC_ISSUER` (в проде — opt-in) |
| AUD-06 | ✅ | `main.py`: в лог идёт только тип схемы, не значение токена |
| AUD-07 | 🟡 | Смягчено Basic Auth (нет анонимного доступа); по-ролевое маскирование в UI — остаток |
| AUD-08 | 📝 | Триггер append-only на месте (тест зелёный); non-owner роль БД — операционный остаток |
| AUD-09 | ⏳ | Прод-оверлей Vault существует; unseal — ручной операционный шаг; внешний доступ закрыт Basic Auth |
| AUD-10 | ✅ | `signing.py`: fail-fast в проде (нет ключа/seed → отказ); dev-фолбэк сохранён |
| AUD-11 | ✅ | `storage.py`: версионирование бакета карантина (перезапись не уничтожает одобренные байты); WORM — операционно |
| AUD-12 | ✅ | `auth.py`+`bus.py`: durable-отзыв доступа через Redis (in-memory как кэш/фолбэк) |
| AUD-13 | ✅ | `ci_scans_api.py`: вебхук без секрета → 503 (fail-closed) |
| AUD-14 | 🟡 | Окно засева теперь за Basic Auth; перенос публикации портов после засева — рекоменд. в остатках |
| AUD-15 | ✅ | Security-заголовки (HSTS/CSP-набор) в `Caddyfile.prod` |
| AUD-16 | 🟡 | `no-new-privileges:true` на control-plane/serving (проверено — стек зелёный); лимиты ресурсов — [рунбук](runbooks/security-hardening-ops.md) |
| AUD-17 | ✅ | Консоль MinIO в base — только `127.0.0.1:9001` |
| AUD-18 | ⏳ | promtail (profile full) — операционный фикс (docker-socket-proxy/journald), описан в остатках |
| AUD-19 | 🟡 | Прод требует секреты через `:?`/примеры; dev-дефолты оставлены намеренно (нужны тестам) |
| AUD-20 | ✅ | Дефолт `MAX_UPLOAD_BYTES` — 2 ГиБ (не 0/безлимит; реальные модели проходят); потолки Caddy подняты выше app-лимита; малый лимит 25 МиБ для DOS-02 — в `docker-compose.test.yml` (`make up-test`) |
| AUD-21 | ✅ | `.github/workflows/security.yml` (bandit/pip-audit/semgrep/gitleaks/compose-config); branch protection — операционно |
| AUD-22 | 📝 | Зафиксировать как осознанный остаточный риск (сервинг не из реестра) |
| AUD-23 | ✅ | `ci_scans_api.py`: валидация `repo`/`path` из вебхука (anti-SSRF/traversal) |
| AUD-24 | ✅ | `production.yml`: Grafana/Gitea не публикуются, пароль Grafana обязателен, регистрация Gitea закрыта |
| AUD-25 | 🟡 | `infra/mlflow/Dockerfile`: psycopg2-binary запинен; boto3 беспиновый (жёсткий пин ломает резолв botocore в образе mlflow — нужен constraints-файл/pip-tools); digest-пины образов — рекоменд. |
| AUD-26 | ✅/⏳ | `production.yml` — Keycloak `start`; `prod.yml` оставлен `start-dev` (смена режима требует живой проверки hostname) |
| AUD-27 | ✅ | `.dockerignore` для control-plane и serving |
| AUD-28 | ✅ | `demo.py`: dev-root-токен Vault из env, не хардкод |
| AUD-29 | 🟡 | Смягчено Basic Auth периметра (нет анонимного доступа к `/api/map/status`) |

Легенда: ✅ исправлено в коде/конфиге · 🟡 смягчено (полный фикс требует SSO-пути или прогона на стеке) · ⏳ операционный шаг · 📝 документированный остаток.

### Остатки, требующие живого стека или операционных решений

- **AUD-04** (промоушен-гейт): предложенный патч — для **любой** модели в `promote` верифицировать артефакт по сохранённым в карантине байтам (как ingest-путь) и запретить понижение `criticality`. Не применял вслепую: затрагивает `test_promote_atomic`/`test_approval_gate`/`test_integrity` (создают версии через `/versions` без сохранённых байтов). Применить после `make up && make test`.
- **AUD-03/07** (идентичность и по-ролевое маскирование в UI): полностью закрываются переходом боевого стенда на `Caddyfile.production` + oauth2-proxy (forward_auth даёт `X-Auth-Request-User`); до этого Basic Auth убирает анонимный доступ.
- **AUD-08** (non-owner роль БД), **AUD-09** (Vault unseal), **AUD-18** (docker-socket-proxy), **AUD-21** (branch protection), **AUD-16** (лимиты ресурсов) — конкретные шаги в [рунбуке хардненинга](runbooks/security-hardening-ops.md).

> Перед публичным показом: на машине с Docker — `make config`; боевой/демо-режим и реальные модели (лимит 2 ГиБ) — `make up` (+ `make demo`); полный pytest-набор (с DOS-02, лимит 25 МиБ) — `make up-test`, затем `cd tests && python -m pytest -q`; для боевого стенда — `deploy_netangels.sh` (теперь Basic Auth реально включается, импортируется прод-realm).

## Второй заход — исследование «что упустили» (2026-06-10)

Повторный широкий разбор (7 зон недоохвата + адверсариальная верификация) и **реальные прогоны сканеров** на живом стеке. Нашлось 45 подтверждённых пробелов, в т.ч. два неполных/регрессивных места в фиксах первого захода.

**Прогоны сканеров (живьём):**
- **bandit** — реальных проблем нет: `B105 'var(--sa-alert)'` — ложняк на CSS-переменную; `subprocess` в `scanners.py` легитимны (list-args, `shutil.which`); `B310` в demo.py — мелочь.
- **pip-audit** — **их собственные зависимости имеют CVE**: `requests==2.32.3` (CVE-2024-47081), `starlette==0.41.3` (CVE-2025-54121/62727, PYSEC-2026-161), `pytest==8.3.4` (CVE-2025-71176). Офлайн-база их же SUP-03-сканера эти CVE не знает (DEPS_AUDIT_ONLINE=0).
- **gitleaks** (286 коммитов) — 5 «находок», **все ложняки/дев-дефолты**: `cripto/app/ca.py:27` это `_root_key: Ed25519PrivateKey | None = None` (тип-аннотация, не ключ; каталога нет в HEAD), остальные 4 — дев-пароли БД в старых compose-коммитах. **Реального секрета в истории нет** — исходный вывод «история чистая» подтверждён.

### Исправлено в этом заходе (проверено: pytest 71/2)
| Что | Где |
|---|---|
| **AUD-03 регресс**: UI-аппрув доверял спуфабельному `X-Auth-Request-User` → стрип входящих identity-заголовков на периметре | `Caddyfile`, `Caddyfile.prod`, `Caddyfile.production` |
| **AUD-12 dev-путь**: durable-отзыв теперь и для dev-токена (`is_revoked(parts[1])`) | `auth.py:95` |
| **AUD-07**: PII-сэмплы в карточке датасета маскируются по умолчанию (ложный note стал правдой) | `cards.py:194` |
| Grafana фолбэк-роль Editor → **Viewer** (любой realm-юзер получал Editor) | `docker-compose.yml` |
| serving: `PredictIn.features` ≤ 64 (memory-DoS одним запросом до rate-limit) | `serving/app/main.py` |
| bus.py: payload не перетирает служебный `type`, лимит длины значений | `bus.py:35` |
| `requests` 2.32.3 → **2.32.4** (CVE-2024-47081) | `control-plane/requirements.txt`, `serving/requirements.txt` |
| CI gitleaks: `fetch-depth: 0` (полная история); CODEOWNERS → `@dmagog` (была несуществующая GitLab-группа) | `.github/workflows/security.yml`, `CODEOWNERS` |

### Вынесено в [рунбук](runbooks/security-hardening-ops.md) (операционное/развёртывание)
AUD-01 повторный деплой (realm импортируется только на пустой kc-БД → форсить чистый старт `keycloak-db`); AUD-05 задать `OIDC_ISSUER` из `PUBLIC_HOST` на пути prod.yml; AUD-08 проверка активности триггера + non-owner роль; AUD-11 Object-Lock (не только versioning) + scoped MinIO-политика; `prod.yml` не гейтит секреты `:?` (+ убрать публичный seed из `init.sh`); хардненинг Grafana/observability продублировать в `prod.yml` (или перейти на `production.yml`); Loki без ретеншна/тома; promtail маскирует только логи control-plane (добавить redact-stage для всех потоков); Grafana на `edge` + `0.0.0.0:3000` в base → loopback; **MLflow без аутентификации** (теги реестра подделываемы изнутри сети) → basic-auth + scoped MinIO-юзер; Vault audit в stdout→Loki; `infra/gitea-data` (живые секреты Gitea) в дереве репо → в named volume; согласованный бамп `starlette`/`fastapi` и `pytest` (CVE); branch protection + Code Owners review.

### В risk-register (осознанные остатки)
- **serving rate-limit RT-01/EXF-01/DOW-01** висят на спуфабельных `X-Client-Id`/`X-Tenant-Id` без inbound-auth → это best-effort телеметрия против дружелюбного клиента, **не контроль против адверсария** (ротация заголовка обходит).
- **serving не из реестра** (AUD-22): promote/sign/admission и MON-05 верифицируют контур реестра, а не то, что реально обслуживается — не заявлять end-to-end admission.
- disclosure постуры: `/health` (внутр. топология), `/users/{actor}` (профиль активности + внутр. коды), `/metrics` — закрывается периметром, но зафиксировать.
- **AUD-04** (гейтить ли internal-модели как критичные) — политическое решение.

## Сводка находок (после перепроверки)

| ID | Серьёзность | Область | Где | Среда | Суть |
|---|:--:|---|---|:--:|---|
| AUD-01 | 🔴 critical | authn / периметр | realm-sirius.json + Caddyfile.prod + docker-compose.prod.yml | prod | Известные демо-учётки + публичный ROPC-клиент + открытый периметр → выпуск MLSecOps-токена в обход `DEV_AUTH=0` |
| AUD-02 | 🟠 high | периметр | infra/reverse-proxy/Caddyfile.prod | prod | Нет Basic Auth/forward_auth — весь UI и login-less аппрув-гейт открыты в интернет |
| AUD-03 | 🟠 high | authz | routers/pages.py:247 | both | UI-аппрув без аутентификации: аппрувер — самозаявленное поле формы; подделка решений и записей аудита |
| AUD-04 | 🟠 high | authz / integrity | registry_api.py:117,135 | both | Самоназначаемая критичность + непроверяемый клиентский hash → критичная модель уходит в прод без подписи и аппрува |
| AUD-05 | 🟡 medium | authn | auth.py:91 | both | OIDC-токен не проверяется на audience/issuer → токен любого клиента realm принимается control-plane |
| AUD-06 | 🟡 medium | logging | main.py:58 | both | Заголовок Authorization (вкл. сервис-токен) пишется в лог открытым текстом |
| AUD-07 | 🟡 medium | authz | pages.py + cards.py | both | UI-страницы в обход API-RBAC: немаскированный PII и все findings/аудит/решения видны любому, кто дотянулся |
| AUD-08 | 🟡 medium | audit | db.py:33 + audit.py | both | Append-only триггер отключается ролью-владельцем БД, под которой ходит приложение; внешнее якорение — best-effort |
| AUD-09 | 🟡 medium | secrets | docker-compose.prod.yml:55 | prod | На боевом пути Vault в dev-режиме: секреты в памяти (теряются при рестарте), без TLS, root-токен в env |
| AUD-10 | 🟡 medium | secrets | signing.py:28 | both | Приватный ключ подписи выводится из публично закоммиченного дефолтного `SIGNING_SEED` |
| AUD-11 | 🟡 medium | integrity | storage.py + compose | both | Карантин-стор без версионирования/WORM и на общих root-кредах MinIO — одобренный артефакт перезаписывается на месте |
| AUD-12 | 🟡 medium | authn | auth.py:21 | both | Отзыв доступа (offboarding) — в памяти процесса: теряется при рестарте, не виден другим воркерам |
| AUD-13 | 🟡 medium | supply / CI | ci_scans_api.py:115 | both | CI-вебхук fail-open при пустом `CI_WEBHOOK_SECRET`; слабый закоммиченный дефолт |
| AUD-14 | 🟡 medium | deploy | deploy_netangels.sh:74 | prod | Окно засева: 80/443 открыты в интернет при `DEV_AUTH=1` до файрвола и до переключения на `0` |
| AUD-15 | 🟡 medium | периметр | Caddyfile.prod | prod | Нет security-заголовков (HSTS/CSP/X-Frame-Options/X-Content-Type-Options) на боевом периметре |
| AUD-16 | 🟡 medium | контейнеры | все compose-файлы | both | Нигде нет лимитов ресурсов и hardening (`no-new-privileges`, `read_only`, `cap_drop`) |
| AUD-17 | 🟡 medium | инфра | docker-compose.yml:155 | dev | Веб-консоль MinIO на `0.0.0.0:9001` с root-кредами в базовом compose |
| AUD-18 | 🟡 medium | инфра | docker-compose.yml:256 | both | promtail монтирует host docker.sock (полный Docker API) без hardening |
| AUD-19 | 🟡 medium | secrets | compose + clients-init.sh | both | Общие статические OIDC-секреты как дефолты и как буквальные значения в примерах |
| AUD-20 | 🟡 medium | DoS | main.py:44 + ingest | both | Лимит тела по умолчанию выключен (`MAX_UPLOAD_BYTES=0`), проверка только по `Content-Length` (обходится) |
| AUD-21 | 🟡 medium | CI/CD | ci/gitlab-ci.reference.yml | both | Нет активного CI-гейта безопасности; «только зелёное в прод» держится на opt-in pre-commit |
| AUD-22 | 🔵 low | архитектура | serving/app/main.py | both | Сервинг крутит модели в памяти, не из реестра — промоушен/подпись/admission не управляют тем, что реально обслуживается |
| AUD-23 | 🔵 low | SSRF | ci_scans_api.py:88 | both | `repo`/`path` из вебхука без валидации в URL Gitea (под валидным HMAC + заданным `GITEA_TOKEN`) |
| AUD-24 | 🔵 low | инфра | docker-compose.production.yml | prod | В full-профиле Grafana (admin/admin) и Gitea (открытая регистрация) публикуются в интернет |
| AUD-25 | 🔵 low | supply | Dockerfile-ы + requirements | both | Образы по тегу, не по digest; зависимости без hash-pin; MLflow-образ ставит часть пакетов без пина |
| AUD-26 | 🔵 low | authn | docker-compose.yml:93 | prod | Keycloak в `start-dev`, `sslRequired` фактически отключён в боевом стеке |
| AUD-27 | 🔵 low | supply | build-контексты | both | Нет `.dockerignore` — `.env`/`.git` могут попасть в слои образа |
| AUD-28 | ⚪ info | secrets | scripts/demo.py | dev | Dev-root-токен Vault зашит в сид-скрипт |
| AUD-29 | ⚪ info | disclosure | pages.py:226 | both | `/api/map/status` без аутентификации отдаёт здоровье узлов/счётчики сработок |

---

## План доработок по фазам

Усилие: **S** — до часа, **M** — полдня, **L** — несколько дней.

### Фаза 0 — до любого публичного показа (блокеры)

#### AUD-01 · Известные учётки + публичный ROPC → захват API в обход `DEV_AUTH=0` 🔴
**Что не так.** Боевой путь (`deploy_netangels.sh` → `docker-compose.yml` + `docker-compose.prod.yml`) импортирует `infra/keycloak/realm-sirius.json`, где включённые пользователи имеют пароль = логину (`ds/ds`, `de/de`, `mlsecops/mlsecops`, `product/product`, `ceo/ceo`, `bruteme/brutepass`), а клиент `sirius` — `publicClient: true` + `directAccessGrantsEnabled: true` + `redirectUris: ["*"]`. Репозиторий публичный, пароли известны.
**Риск.** Любой из интернета шлёт `POST /auth/realms/sirius/protocol/openid-connect/token` с `grant_type=password&client_id=sirius&username=mlsecops&password=mlsecops` (секрет клиента не нужен — публичный клиент + direct grants) и получает валидный access-токен с ролью MLSecOps. `auth.py` его принимает (подпись валидна), и весь `/api/*` открыт — несмотря на `DEV_AUTH=0`. `bruteForceProtected` не помогает: учётки не угадывают, их знают. Перепроверка: подтверждено, серьёзность поднята до critical.
**Как чинить.**
1. Завести отдельный боевой realm **без демо-персон** и импортировать **его** (а не `realm-sirius.json`) — поправить монтирование realm в `docker-compose.prod.yml`/`production.yml` и `deploy_netangels.sh`. Либо удалять демо-юзеров сразу после импорта.
2. На клиенте `sirius`: `directAccessGrantsEnabled: false`, `redirectUris`/`webOrigins` — точные URL вместо `*`.
3. Перевести Keycloak в `start` (см. AUD-26).
**Усилие.** M.
**Проверка.** Префлайт в `deploy_netangels.sh`: ROPC с `mlsecops/mlsecops` к боевому realm обязан вернуть `invalid_grant`/`unauthorized_client`. Новый BDD-сценарий `PERIM-CRED`: «учётка demo-realm не выпускает токен на боевом контуре».

#### AUD-02 · Открытый периметр: в `Caddyfile.prod` нет аутентификации 🟠
**Что не так.** `deploy_netangels.sh` генерирует bcrypt-хэш demo-пароля и кладёт `DEMO_USER`/`DEMO_PASS_HASH`, `docker-compose.prod.yml` пробрасывает их в reverse-proxy — но **в `Caddyfile.prod` нет ни `basic_auth`, ни `forward_auth`**. `grep -ri basic infra/reverse-proxy/` пуст. Заявленный «периметр за HTTP Basic Auth» по факту отсутствует.
**Риск.** Весь server-rendered UI control-plane (`/map`, `/registry`, `/data`, `/decisions`, `/users`, `/findings`, карточки) и login-less пишущий аппрув-гейт (`POST /ui/map/run/...`, см. AUD-03) открыты в интернет. Плюс это и есть условие достижимости AUD-01 (открыт `/auth/*`).
**Как чинить.** Либо добавить `basic_auth` в `Caddyfile.prod` (consume уже пробрасываемые `DEMO_USER`/`DEMO_PASS_HASH`) — минимум для демо-стенда; либо перейти на путь `Caddyfile.production` + oauth2-proxy (`forward_auth`), где это уже спроектировано. Если стенд только для жюри — Basic Auth + ограничение `/auth/*` достаточно.
**Усилие.** S (basic_auth) / M (oauth2-proxy).
**Проверка.** Префлайт: `GET /` и `GET /map` без credentials → `401`. BDD `PERIM-01`: «UI боевого стенда требует аутентификацию».

> AUD-01 и AUD-02 чинятся вместе — это один кластер «боевой путь деплоя не получил спроектированной защиты». Самый быстрый цельный фикс: переключить `deploy_netangels.sh` на оверлей `docker-compose.production.yml` + `Caddyfile.production` и довести его три TODO (Vault prod, oauth2-proxy, AppRole-логин в `vault.py`).

### Фаза 1 — высокий приоритет

#### AUD-03 · UI-аппрув без идентичности аппрувера 🟠
**Что не так.** `POST /ui/map/run/{run}/{decision}` ([pages.py:247](../control-plane/app/routers/pages.py#L247)) не имеет ни `get_principal`, ни `require(...)`. Аппрувер берётся из поля формы `approver` и лишь сверяется со списком `decisions.UI_APPROVERS = ("mlsecops", "reviewer")`. На открытом периметре любой шлёт форму с `approver=mlsecops` и пишет решение аппрув-гейта в `Approval` + аудит.
**Риск.** Подделка governance-записей и записей аудита, замусоривание журнала решений, давление на промоушен-гейт. Смягчает то, что сам промоушен в прод идёт через `/api` (под RBAC и separation of duties с привязкой к хэшу), поэтому одной UI-подделки для деплоя мало — отсюда high, не critical.
**Как чинить.** Закрыть эндпоинт реальной идентичностью: либо `forward_auth` на периметре (заголовок `X-Auth-Request-User` от oauth2-proxy → принципал), либо `Depends(require("model.approve"))` как у API-аппрува. Убрать самозаявленный `approver`.
**Усилие.** M (зависит от выбранной модели аутентификации UI).
**Проверка.** BDD: «UI-аппрув без аутентифицированного MLSecOps → 401/403, запись в аудит не создаётся».

#### AUD-04 · Обход промоушен-гейта через самоназначаемую критичность 🟠
**Что не так.** При регистрации модели `criticality` приходит из тела клиента ([registry_api.py:117](../control-plane/app/routers/registry_api.py#L117)); жёсткий гейт (подпись SUP-04 + ручной аппрув VIS-03/ACC-02) включается только при `requires_validation`, то есть лишь для `regulatory`/`financial`. Версия через `POST /versions` принимает `artifact_hash` и `signature` **из тела клиента без проверки** ([registry_api.py:135](../control-plane/app/routers/registry_api.py#L135)); для не-критичных моделей `promote` подпись и целостность не проверяет вовсе.
**Риск.** DS регистрирует реально критичную модель как `internal`, создаёт версию с произвольным `artifact_hash`, проходит только проверку «нет открытых critical» и промоутит в прод — без подписи, без аппрува, без верификации артефакта. End-to-end обход admission-control.
**Как чинить.** (1) Критичность не должна быть полностью самоназначаемой: выводить её из источника/датасета или требовать подтверждения ролью MLSecOps; как минимум — нельзя понижать критичность уже заведённой модели. (2) Для **любой** модели в `promote` верифицировать артефакт по сохранённым в карантине байтам (как уже делает ingest-путь), а не доверять клиентскому `artifact_hash`. (3) Рассмотреть обязательность подписи для всех прод-промоушенов, не только `requires_validation`.
**Усилие.** M.
**Проверка.** BDD: «версия с клиентским hash без сохранённого артефакта не промоутится»; «понижение criticality запрещено».

### Фаза 2 — defense-in-depth (medium)

#### AUD-05 · OIDC-токен без проверки audience/issuer 🟡
`jwt.decode(..., options={"verify_aud": False})` ([auth.py:91](../control-plane/app/auth.py#L91)), issuer не проверяется. Токен, выпущенный для **любого** клиента того же realm (`grafana`, `gitea`, `minio`), несёт `realm_access.roles` и принимается control-plane. Усиливает AUD-01. **Чинить:** проверять `aud` (ожидаемый клиент control-plane) и `iss` (URL realm); завести для control-plane отдельный confidential-клиент/audience. **Усилие S.** **Проверка:** тест «токен для клиента minio отвергается control-plane».

#### AUD-06 · Bearer-токен в логах открытым текстом 🟡
[main.py:58](../control-plane/app/main.py#L58): `logger.info("req ... auth=%s", ... headers.get("authorization"))` — на каждый не-health запрос пишет полный заголовок Authorization (включая долгоживущий `SERVICE_TOKEN`) в stdout → Loki/Promtail. Прямо противоречит контролю LOG-01 «без значений секретов». **Чинить:** не логировать значение; писать только факт наличия/тип схемы (`bearer`/`none`) или хэш-префикс. **Усилие S.** **Проверка:** тест «в логах нет подстроки токена».

#### AUD-07 · UI-страницы в обход object-level авторизации 🟡
Маскирование PII и допуск по чувствительности (`can_read_sensitivity`) живут только в `/api/*`. Server-rendered страницы (`/data`, карточки датасета через `cards.py`) и фрагменты findings/аудита/решений рендерятся без проверки роли и допуска ([pages.py:106](../control-plane/app/routers/pages.py#L106)). На достижимом периметре — немаскированные PII-сэмплы и весь оперативный контекст любому зрителю. **Чинить:** провести UI через ту же аутентификацию (см. AUD-02/03) и применять `can_read_sensitivity`/маскирование в `cards.py`/UI так же, как в API. **Усилие M.** **Проверка:** BDD «роль без допуска к pii видит `***` и в UI, не только в API».

#### AUD-08 · Append-only аудита отключается ролью-владельцем БД 🟡
Триггер `sirius_audit_no_mutate` ([db.py:33](../control-plane/app/db.py#L33)) defeat-абелен: приложение ходит под `POSTGRES_USER=sirius` — владельцем схемы, которому доступен `DROP TRIGGER`. Установка триггера к тому же fail-soft. Внешнее якорение головы цепочки в Redis/Loki — best-effort и нигде не сверяется. **Чинить:** (1) в проде control-plane должен ходить под non-owner ролью без DDL на `audit_events` (комментарий в коде это и предполагает — осталось выдать роль через Vault и применить); (2) сделать сверку отгруженной наружу головы с БД регулярной (а не «оно где-то есть»). **Усилие M.** **Проверка:** тест «под рабочей ролью `DROP TRIGGER`/`DELETE` по `audit_events` запрещён».

#### AUD-09 · Vault в dev-режиме на боевом пути 🟡
`docker-compose.prod.yml` не переопределяет vault — остаётся базовый `server -dev`: хранилище в памяти (рестарт стирает все KV, а `restart: unless-stopped` поднимает пустой), без TLS, root-токен в `.env.prod` и пробрасывается как `VAULT_TOKEN` в vault-init (виден через `docker inspect`). Жёсткие `vault.prod.hcl`/`vault-init-prod.sh`/`production.yml` существуют, но этим путём не используются. **Чинить:** применить prod-оверлей Vault (raft + unseal + TLS), сидировать секреты под scoped-оператором после unseal, перестать передавать root-токен в env. **Усилие L.** **Проверка:** `vault status` → не dev, sealed→unsealed оператором; health control-plane → `secrets_source=vault`.

#### AUD-10 · Ключ подписи из публичного дефолтного seed 🟡
Без `SIGNING_KEY_PEM`/`SIGNING_SEED` ключ детерминированно выводится из зашитого `"5e1f17a0"` ([signing.py:28](../control-plane/app/signing.py#L28)); compose-дефолт и `init.sh` используют тот же публичный seed. Кто угодно воспроизводит приватный ключ и подделывает валидные подписи — обнуляя SUP-04. `deploy_netangels.sh` и `production.yml` задают стойкий seed, но fallback в коде гарантирует выводимый ключ вместо явного отказа. **Чинить:** убрать hardcoded fallback — при отсутствии ключа и seed падать (`raise`); убрать демо-дефолты seed из compose и `init.sh`. **Усилие S.** **Проверка:** старт без seed → ошибка, не «тихо подписываем известным ключом».

#### AUD-11 · Перезапись одобренного артефакта в карантин-сторе 🟡
`storage.put` пишет по ключу с перезаписью ([storage.py:46](../control-plane/app/storage.py#L46)), бакет без версионирования/Object-Lock, креды — root MinIO. Кто получил креды MinIO (а консоль ещё и наружу, AUD-17), молча подменяет уже отсканированный/подписанный артефакт на месте. Ловится только постфактум `verify_prod_signatures` (MON-05, детект), без prevent. **Чинить:** включить версионирование + Object-Lock (WORM) на бакете карантина; выдать control-plane узкую S3-политику (put/get своих ключей), не root. **Усилие M.** **Проверка:** тест «перезапись существующего ключа артефакта отклоняется/версионируется».

#### AUD-12 · Отзыв доступа не переживает рестарт 🟡
`_REVOKED` — `set()` в памяти процесса ([auth.py:21](../control-plane/app/auth.py#L21)). Offboarding (ACC-03) теряется при рестарте и не виден другим uvicorn-воркерам. В одно-воркерном демо работает, в проде молча регрессирует. **Чинить:** хранить отзыв в общем сторе (Redis/БД), проверять оттуда; в идеале — короткие токены + проверка против списка отзыва централизованно. **Усилие M.** **Проверка:** BDD «после offboarding и рестарта control-plane субъект всё ещё получает 401».

#### AUD-13 · CI-вебхук fail-open без секрета 🟡
В `ci_webhook` проверка HMAC выполняется только если `CI_WEBHOOK_SECRET` задан ([ci_scans_api.py:115](../control-plane/app/routers/ci_scans_api.py#L115)); дефолт в base compose — `change-me-ci-webhook`. Пустой/дефолтный секрет → поддельный вебхук принимается, гейт CI-01 обходится. **Чинить:** при пустом секрете — отклонять вебхук (fail-closed), убрать слабый дефолт (требовать через `:?`, как в `production.yml`). **Усилие S.** **Проверка:** тест «вебхук без валидной подписи → 401 даже при незаданном секрете».

#### AUD-14 · Окно засева: публичные 80/443 при `DEV_AUTH=1` 🟡
Фаза 1 `deploy_netangels.sh` поднимает стек с сид-оверрайдом (`DEV_AUTH=1`), а `docker-compose.prod.yml` публикует Caddy на 80/443 с первого старта; файрвол — опциональный последний шаг, префлайт «dev-токен → 401» только после фазы 2. Есть окно, когда публичный бокс принимает `Bearer dev:mlsecops:MLSecOps` из интернета. **Чинить:** на время засева не публиковать 80/443 (только loopback) либо поднять файрвол до экспозиции; сначала засев на 127.0.0.1, потом переключение и открытие порта. **Усилие M.** **Проверка:** во время фазы 1 внешний `:80` недоступен.

#### AUD-15 · Нет security-заголовков на боевом периметре 🟡
`Caddyfile.prod` не отдаёт HSTS/CSP/X-Frame-Options/X-Content-Type-Options/Referrer-Policy — они есть только в неиспользуемом `Caddyfile.production`. **Чинить:** перенести блок `header { ... }` из `Caddyfile.production` в `Caddyfile.prod` (или перейти на `production`). **Усилие S.** **Проверка:** `curl -I` показывает HSTS и nosniff.

#### AUD-16 · Нет лимитов ресурсов и hardening контейнеров 🟡
Ни в одном compose нет `mem_limit`/`cpus`, `security_opt: no-new-privileges`, `read_only`, `cap_drop`. Любой сервис может выесть память/CPU хоста; привилегии не урезаны. **Чинить:** задать ресурсные лимиты ключевым сервисам (control-plane, serving, keycloak, postgres), добавить `no-new-privileges:true` и `cap_drop: [ALL]` где возможно, `read_only` для stateless. **Усилие M.** **Проверка:** `docker inspect` показывает лимиты и опции.

#### AUD-17 · Консоль MinIO наружу с root-кредами (dev) 🟡
Базовый `docker-compose.yml:155` публикует `9001` на `0.0.0.0` с входом под root (`MINIO_ROOT_USER/PASSWORD`, дефолт `sirius`/`sirius-minio`). `prod.yml` биндит на `127.0.0.1`, `production.yml` убирает — но базовый профиль так и торчит. **Чинить:** в базовом compose биндить консоль на `127.0.0.1` (как уже сделано в prod-оверлеях). **Усилие S.** **Проверка:** `9001` не слушается на внешнем интерфейсе.

#### AUD-18 · promtail монтирует host docker.sock 🟡
`docker-compose.yml:256` монтирует `/var/run/docker.sock` в promtail. Сокет (даже `:ro`-монтирование) — это полный Docker API: контроль над сокетом = контроль над хостом. **Чинить:** перейти на чтение логов через файловый драйвер/journald вместо docker.sock; если сокет нужен — проксировать через `docker-socket-proxy` с whitelist. **Усилие M.** **Проверка:** promtail не имеет прямого доступа к сокету.

#### AUD-19 · Общие статические OIDC-секреты как дефолты 🟡
`GRAFANA_OIDC_SECRET`/`GITEA_OIDC_SECRET`/`MINIO_OIDC_SECRET` имеют дефолты (`*-oidc-dev`) в compose и буквальные значения в `.env.prod.example`/`clients-init.sh`. **Чинить:** убрать дефолты (требовать через `:?`), генерировать в `deploy_netangels.sh` (уже частично делается), не держать в примерах. **Усилие S.** **Проверка:** старт full-профиля без заданных секретов падает.

#### AUD-20 · Лимит тела запроса по умолчанию выключен 🟡
`MAX_UPLOAD_BYTES=0` ([main.py:44](../control-plane/app/main.py#L44)) = лимита нет; middleware проверяет только `Content-Length`, который подделывается/опускается (chunked). Эндпоинты ingest/scan читают тело в память целиком (`await request.body()`). Caddy режет на 2 ГБ — всё равно много. **Чинить (сделано).** Дефолт `MAX_UPLOAD_BYTES` = 2 ГиБ (реальные модели проходят, но не безлимит); потолки Caddy (`Caddyfile`/`.prod`/`.production`) подняты до 3 ГБ (выше app-лимита, чтобы связывающим guard'ом был app-уровень с Finding/аудитом). Сценарий DOS-02 требует малого лимита (26 МиБ → 413), поэтому он вынесен в `docker-compose.test.yml` (25 МиБ, `make up-test`) — тест зелёный, прод не ограничен. Остаток (не сделано): чтение тела потоково с обрывом по факту, а не только по `Content-Length` (обход chunked'ом — известный фолбэк на потолок Caddy). **Усилие M.** **Проверка:** `make up` — модель ~1 ГБ проходит ingest; `make up-test` — 26 МиБ → 413 + Finding(oversized-upload).

#### AUD-21 · Нет активного CI-гейта безопасности 🟡
`ci/gitlab-ci.reference.yml` — референс/parked, `.github/workflows` в репозитории нет. Заявленное «только зелёное в прод» фактически держится на opt-in `.pre-commit-config.yaml`, который разработчик может пропустить (`--no-verify`). **Чинить:** включить реальный CI-пайплайн (GitHub Actions, раз канон — github.com/dmagog/Sirius-Argus) с обязательными джобами: semgrep, pip-audit/Trivy, gitleaks, pytest, и branch protection с required checks. **Усилие M.** **Проверка:** PR с уязвимой зависимостью не мёржится.

### Фаза 3 — гигиена (low / info)

- **AUD-22 · Сервинг не из реестра (low).** `serving/app/main.py` обучает iris-модели в памяти на старте; промоушен/подпись/admission в control-plane не управляют тем, что реально обслуживается. Для капстона это ок (честная демо-петля), но стоит зафиксировать как осознанный остаточный риск в risk-register: «контур контроля и контур инференса не связаны загрузкой артефакта». При желании — загрузка подписанного артефакта из карантина в serving с verify-on-load.
- **AUD-23 · SSRF в `_fetch_changed_files` (low).** `repo`/`path` из payload вебхука подставляются в URL Gitea без валидации ([ci_scans_api.py:88](../control-plane/app/routers/ci_scans_api.py#L88)). Гейтится валидным HMAC + заданным `GITEA_TOKEN` (по умолчанию пуст), поэтому low. **Чинить:** валидировать `repo` по шаблону `owner/name`, запрещать `..`/абсолютные пути.
- **AUD-24 · Grafana/Gitea наружу в full-профиле (low).** `docker-compose.production.yml --profile full` публикует Grafana (дефолт admin/admin) и Gitea (`ENABLE_AUTO_REGISTRATION`, открытая регистрация) в интернет. **Чинить:** не публиковать ops-консоли наружу (доступ через SSO/VPN), задать `GRAFANA_PASSWORD`, выключить открытую регистрацию Gitea.
- **AUD-25 · Пины образов/зависимостей (low).** Базовые образы по тегу, не по digest; `pip install` без `--require-hashes`; `infra/mlflow/Dockerfile` ставит psycopg2-binary/boto3 без пина. **Чинить:** пин по digest для боевых образов, hash-pin requirements, пин в MLflow-образе.
- **AUD-26 · Keycloak в dev-режиме (low).** `start-dev`, `sslRequired` фактически off. **Чинить:** `start` (+ `--optimized` после `kc.sh build`), `sslRequired=external`. Связано с AUD-01.
- **AUD-27 · Нет `.dockerignore` (low).** Build-контексты control-plane/serving без `.dockerignore` — риск утащить `.env`/`.git` в слои. **Чинить:** добавить `.dockerignore`.
- **AUD-28 · Dev-root-токен Vault в `scripts/demo.py` (info).** Только dev-сид; убрать/вынести в env.
- **AUD-29 · `/api/map/status` без аутентификации (info).** Отдаёт здоровье узлов и счётчики сработок ([pages.py:226](../control-plane/app/routers/pages.py#L226)) — раскрытие постуры. **Чинить:** закрыть аутентификацией периметра вместе с остальным UI (AUD-02).

---

## Что уже сделано хорошо (не ломать при правках)

- **AuthN fail-closed.** Нет токена / невалиден / бэкенд недоступен → 401, никогда open-by-default. Алгоритм подписи запинен (`RS256`) — атака `alg:none` не проходит. Сервис-токен сравнивается constant-time (`hmac.compare_digest`).
- **Zero-trust RBAC + object-level.** Матрица «действие→роли» + допуск по чувствительности на уровне объекта; каждый отказ — в аудит.
- **Промоушен-гейт.** Атомарность под `with_for_update` (anti-TOCTOU), separation of duties (аппрувер ≠ владелец ≠ промоутер), решение привязано к `artifact_hash`, reject имеет «зубы», блок отката на retired-версию, open-critical-гейт с явным risk-acceptance.
- **Скан артефактов без исполнения.** `pickletools.genops` вместо `pickle.load`; архивы и (для критичных) pickle отклоняются; AST-SAST не исполняет код.
- **Tamper-evident аудит.** hash-chain + сериализация записи под локом; внешнее якорение головы (идея верная, доделать сверку — AUD-08).
- **Веб-гигиена.** Весь пользовательский ввод в server-rendered UI экранируется через `html.escape` (`_e()`); SQL только через ORM с биндами; контейнеры под non-root; зависимости запинены `==`; `.env` в `.gitignore`, история git чистая.

## Регрессионная защита (в духе BDD-методологии)

Чтобы находки не вернулись, добавить их как поведенческие проверки — поверх существующего стиля (pytest-bdd против живой системы + префлайт в деплое):

- **Префлайт деплоя** (расширить `deploy_netangels.sh`): ROPC демо-учётки → отказ (AUD-01); `GET /` без credentials → 401 (AUD-02); внешний `:80`/`:9001` закрыт; security-заголовки присутствуют (AUD-15).
- **Новые BDD-сценарии:** `PERIM-01` (UI требует аутентификацию), `PERIM-CRED` (демо-realm не выпускает токен), `AUD-LOG-01` (токен не попадает в логи), `AUTHZ-UI-01` (object-level маскирование и в UI), `OFFB-DURABLE` (offboarding переживает рестарт).
- **CI-гейт** (AUD-21): semgrep + pip-audit/Trivy + gitleaks + pytest как required checks на ветке `main`.

## Порядок действий (рекомендация)

1. **Сегодня, перед показом:** AUD-01 + AUD-02 (один кластер — переключить деплой на жёсткий путь или закрыть периметр и вычистить демо-realm). Без этого публичный стенд захватывается известными учётками.
2. **Эта неделя:** AUD-03, AUD-04 (governance-целостность), AUD-05, AUD-06 (быстрые S-фиксы с высоким эффектом).
3. **Доводка прод-готовности:** AUD-08–AUD-12, AUD-15, AUD-20, AUD-21.
4. **Гигиена:** остальное по мере появления времени; AUD-22 — зафиксировать как осознанный остаточный риск в [risk-register](threat-model/risk-register.md).
