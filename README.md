<p align="center">
  <img src="assets/sirius-argus-logo.png" alt="Sirius Argus — MLSecOps Platform" width="300">
</p>

# Sirius Argus — безопасная MLOps-платформа

*Sirius Argus* встраивает безопасность прямо в ML-пайплайн: проверки запускаются автоматически на переходах от приёма данных до вывода модели из эксплуатации. Для каждого актива видно, какие угрозы закрыты и каким контролем.

> Argus — стоокий страж из мифа: имя про суть платформы, которая видит весь ML-пайплайн и оберегает от угроз. Sirius — звезда-сторож, α Большого Пса; девиз — *the all-seeing watchdog star*.



> Статус: в разработке, итерации [И0–И6](docs/roadmap.md). Сделано: **И0** + **И1** (реестр, zero-trust RBAC, lineage/blast-radius, MON-02-гейт, реальный OIDC через Keycloak, Redis-шина, маскирование логов, реестр на обёрнутом MLflow) + **И2** (ingestion-гейт: вредоносный pickle блокируется + Finding + триаж; политика форматов по критичности; gate на закачку датасета — карантин; расхождение вердиктов сканеров + триаж фолза; PII-маскирование по допуску; ML-aware SAST на код/ноутбуки) + **И3** (policy-матрица промоушена критичных моделей: модель-карта + подпись + HITL-аппрув; скан зависимостей на CVE + секретов; separation of duties; запрет отката) + **И4** (3 НЕ-генеративные модели задеплоены за рантайм-защитами; extraction-detect RT-01 → троттлинг + сработка) + **И5** (карта покрытия угроз + CEO-вью на live-данных) + **И6** (сквозной конвейер ЖЦ одной командой — `make pipeline`; decommission, детект эксфильтрации, tamper-evidence аудита) + **инфра-доводка** (observability Prometheus/Loki/Grafana; реальные сканеры picklescan/detect-secrets; единая точка входа Gitea-CI; веб-UI: live-дашборд сработок и аудита на HTMX + матрица прав RBAC) + **добор residual** (дрейф данных, output-reduction, сетевая сегментация рантайма, typosquat/dependency-confusion, hardcoded-логика, качество данных: label-flip/UGC-триггер/skew/петля дообучения) — **56 pytest-функций green** (48 уникальных сценариев каталога из 50; остаток — 2 честных: ShadowLogic и стоимостные квоты, см. [risk-register](docs/threat-model/risk-register.md)). Документация идёт впереди кода намеренно — модель угроз и поведения (BDD) задают, что строим.

## Документация

| Документ | О чём |
|---|---|
| [docs/roadmap.md](docs/roadmap.md) | Итеративный план реализации (И0–И6), привязка к приоритетам куратора и сценариям |
| [docs/architecture.md](docs/architecture.md) | Архитектура: компоненты, ER-модель, жизненный цикл, потоки, карта покрытия (схемы Mermaid) |
| [docs/threat-model/personas.md](docs/threat-model/personas.md) | Персоны атакующих (A1–A22) и защитников (D1–D10), с кодовыми именами |
| [docs/threat-model/bdd-catalog.md](docs/threat-model/bdd-catalog.md) | 50 BDD-сценариев: разом модель угроз, acceptance-тест, шаг демо и строка карты покрытия |
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
| Скан моделей | picklescan + собств. opcode-скан (`SUP-01`) |
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

Живое демо money-shot'ов (вредоносная модель → блок, гейты, HITL, рантайм-атака, карта покрытия). Для локального демо со скриптовыми ролями поднимай с `DEV_AUTH=1` (иначе authN — только через Keycloak, dev-токены отклоняются):

```bash
DEV_AUTH=1 make up      # локальное демо с dev-токенами ролей
make demo               # все 5 money-shot'ов по живому стеку
make pipeline           # сквозной ЖЦ одной модели: приём→скан→gate→HITL→деплой→атака→decommission
```

Профили `core`/`full` — см. [docs/roadmap.md](docs/roadmap.md). AuthN — через Keycloak; для локали без Keycloak можно `DEV_AUTH=1` и токены `Bearer dev:<user>:<role>`.
