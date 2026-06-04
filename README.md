# Sirius Argus — безопасная MLOps-платформа

<img align="right" width="280" src="assets/sirius-argus-logo.png" alt="Sirius Argus — MLSecOps Platform">

[![last commit](https://img.shields.io/github/last-commit/dmagog/Sirius-Argus?style=flat-square)](https://github.com/dmagog/Sirius-Argus/commits/main)
![BDD](https://img.shields.io/badge/BDD-53%2F54_green-2ea44f?style=flat-square)
![run](https://img.shields.io/badge/run-make_up-2496ED?style=flat-square&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![SSO](https://img.shields.io/badge/SSO-Keycloak_OIDC-FF6C37?style=flat-square&logo=keycloak&logoColor=white)

*Sirius Argus* встраивает безопасность прямо в ML-пайплайн: проверки запускаются автоматически на переходах от приёма данных до вывода модели из эксплуатации. Для каждого актива видно, какие угрозы закрыты и каким контролем.

> Argus — стоокий страж из мифа: имя про суть платформы, которая видит весь ML-пайплайн и оберегает от угроз. Sirius — звезда-сторож, α Большого Пса; девиз — *the all-seeing watchdog star*.



> Статус: в разработке, итерации [И0–И6](docs/roadmap.md). Сделано: **И0** + **И1** (реестр, zero-trust RBAC, lineage/blast-radius, MON-02-гейт, реальный OIDC через Keycloak, Redis-шина, маскирование логов, реестр на обёрнутом MLflow) + **И2** (ingestion-гейт: вредоносный pickle блокируется + Finding + триаж; политика форматов по критичности; gate на закачку датасета — карантин; расхождение вердиктов сканеров + триаж фолза; PII-маскирование по допуску; ML-aware SAST на код/ноутбуки) + **И3** (policy-матрица промоушена критичных моделей: модель-карта + подпись + ручной аппрув; скан зависимостей на CVE + секретов; separation of duties; запрет отката) + **И4** (3 НЕ-генеративные модели задеплоены за рантайм-защитами; extraction-detect RT-01 → троттлинг + сработка) + **И5** (карта покрытия угроз + CEO-вью на live-данных) + **И6** (сквозной конвейер ЖЦ одной командой — `make pipeline`; decommission, детект эксфильтрации, tamper-evidence аудита) + **инфра-доводка** (observability Prometheus/Loki/Grafana; реальные сканеры modelaudit/detect-secrets; единая точка входа Gitea-CI; веб-UI: live-дашборд сработок и аудита на HTMX + матрица прав RBAC) + **добор residual** (дрейф данных, output-reduction, сетевая сегментация рантайма, typosquat/dependency-confusion, hardcoded-логика, качество данных: label-flip/UGC-триггер/skew/петля дообучения, стоимостная квота DOW-01, сервис-аккаунт сервинга без DEV_AUTH) + **supply-chain/GRC-доводка** (карантин-стор артефактов + reject архивов; подпись OpenSSF model-signing офлайн-ключом; артефакт-скан modelaudit; evidence-based ручной аппрув + привязан к hash; risk-acceptance под условиями; лимит больших загрузок; секреты в HashiCorp Vault — AppRole + политика + аудит + revoke) + **защита энфорсера** (по итогам security-review: append-only аудит на БД-триггере LOG-02, атомарный промоушен под row-lock GOV-03, непрерывная ре-верификация прода MON-05, EXF-01-счётчик в общем Redis, anti-replay HMAC-вебхука, Keycloak brute-force CRED-03, лимит чтения артефакта, догфудинг bandit по своему коду) — **73 pytest-функции green** (53 уникальных сценариев каталога из 54; остаток — 1 честный: ShadowLogic как предел статического анализа, см. [risk-register](docs/threat-model/risk-register.md)). Документация идёт впереди кода намеренно — модель угроз и поведения (BDD) задают, что строим.

## Документация

| Документ | О чём |
|---|---|
| [docs/overview.md](docs/overview.md) | Пакет к сдаче: обзор всех узлов и защит на одной странице — читать первым |
| [docs/roadmap.md](docs/roadmap.md) | Итеративный план реализации (И0–И6), привязка к приоритетам куратора и сценариям |
| [docs/architecture.md](docs/architecture.md) | Архитектура: компоненты, ER-модель, жизненный цикл, потоки, карта покрытия (схемы Mermaid) |
| [docs/threat-model/personas.md](docs/threat-model/personas.md) | Персоны атакующих (A1–A22) и защитников (D1–D10), с кодовыми именами |
| [docs/threat-model/bdd-catalog.md](docs/threat-model/bdd-catalog.md) | 53 BDD-сценария: разом модель угроз, acceptance-тест, шаг демо и строка карты покрытия |
| [docs/testing.md](docs/testing.md) | Стратегия тестирования: test-first BDD, пирамида, pytest-bdd против compose |
| [docs/threat-model/risk-register.md](docs/threat-model/risk-register.md) | Пер-узловой реестр рисков: приоритет L×I, обработка, владелец |
| [docs/threat-model/security-kpis.md](docs/threat-model/security-kpis.md) | Измеримая безопасность: KPI и SLO |
| [docs/adr/](docs/adr/) | Журнал архитектурных решений |
| [docs/runbooks/incident-response.md](docs/runbooks/incident-response.md) | Реакция на инциденты, доступность и восстановление |
| [SECURITY.md](SECURITY.md) | Безопасность самого репозитория |

## Приоритеты кейса (рекомендации куратора) → где закрыто

| Приоритет | Контроль / сценарий |
|---|---|
| Скан кода | Semgrep + AST-SAST (`CODE-01`) + detect-secrets |
| Реестр моделей | control-plane + MLflow (§6) |
| Security gate перед продом | gated PR (`SUP-03`, `CI-01`) |
| Скан моделей | modelaudit (изолир. venv) + собств. opcode-скан (`SUP-01`) |
| Секреты | HashiCorp Vault: AppRole + политика + аудит + revoke (`CRED-02`) |
| Версионирование · история · lineage | MLflow + хеш-версии · `AuditEvent` + hash-chain (`MON-04`) · `Run` lineage (`MON-02`) |
| Ролёвка (zero-trust) | RBAC (`ACC-01/02/05`, `ESC-01`) |
| Подписи | `SUP-04`, `TOCTOU-01` (ADR-0006) |
| Сканы данных · gate на закачку | `DATA-01..04` · ingestion-блок (`SUP-01`), карантин (`DATA-01`) |
| Автоконвертация / запрет небезопасных форматов | `SUP-07` (convert-or-reject) |
| Рантайм | `RT-01/02/05/06`, `DOS-01` |

Порядок сборки И0–И6 следует этому приоритету; рантайм — поздний, как и в риск-реестре (см. [ADR-0005](docs/adr/0005-fail-closed-protect-enforcer.md)).

## Безопасность этого репозитория

Репозиторий живёт по тем же правилам, что платформа применяет к ML: стоят pre-commit-хуки (gitleaks), чувствительные изменения проходят ревью через CODEOWNERS, конфиг fail-closed гейтов (gitleaks, Trivy, Semgrep) хранится как reference в `ci/`. Серверный гейт по плану — локальный control-plane как CI (ADR-0002); GitLab CI запаркован, потому что gitlab.com не запускает пайплайны на аккаунте владельца. Подробности — в [SECURITY.md](SECURITY.md).

## Запуск

```bash
cp .env.example .env      # поправь секреты
make up                   # core: control-plane + Postgres + Keycloak + Redis + MinIO + MLflow + reverse-proxy
# или: make up-full       # + observability (Loki/Grafana/Prometheus) + Gitea
```

Открыть: дашборд — http://localhost:8080 · карта покрытия (CEO) — http://localhost:8080/coverage · Keycloak — http://localhost:8080/auth/ · Сервинг моделей — http://localhost:8001/models · Grafana (full) — http://localhost:3000.

Тесты (BDD против живого стека):

```bash
cd tests && pip install -r requirements.txt && pytest -q
```

Живое демо money-shot'ов (вредоносная модель → блок, гейты, ручной аппрув-гейт, рантайм-атака, карта покрытия). Для локального демо со скриптовыми ролями поднимай с `DEV_AUTH=1` (иначе authN — только через Keycloak, dev-токены отклоняются):

```bash
DEV_AUTH=1 make up      # локальное демо с dev-токенами ролей
make demo               # все 5 money-shot'ов по живому стеку
make pipeline           # сквозной ЖЦ одной модели: приём→скан→gate→аппрув-гейт→деплой→атака→decommission
```

Профили `core`/`full` — см. [docs/roadmap.md](docs/roadmap.md). AuthN — через Keycloak; для локали без Keycloak можно `DEV_AUTH=1` и токены `Bearer dev:<user>:<role>`.
