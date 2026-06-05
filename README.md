# Sirius Argus — безопасная MLOps-платформа

<img align="right" width="280" src="assets/sirius-argus-logo.png" alt="Sirius Argus — MLSecOps Platform">

[![last commit](https://img.shields.io/github/last-commit/dmagog/Sirius-Argus?style=flat-square)](https://github.com/dmagog/Sirius-Argus/commits/main)
![BDD](https://img.shields.io/badge/BDD-53%2F54_green-2ea44f?style=flat-square)
![tests](https://img.shields.io/badge/pytest-73_green-2ea44f?style=flat-square)
![run](https://img.shields.io/badge/run-make_up-2496ED?style=flat-square&logo=docker&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![SSO](https://img.shields.io/badge/SSO-Keycloak_OIDC-FF6C37?style=flat-square&logo=keycloak&logoColor=white)

**Sirius Argus — открытая self-hosted платформа MLSecOps: безопасность и управляемость на всём жизненном цикле ML-модели, в едином контуре.** Один control-plane объединяет точечные сканеры и governance-инструменты; модель попадает в прод только через него — со сканами, подписью, policy-гейтами, ручным аппрувом для критичных версий и неизменяемым аудитом. По каждому активу видно, какие угрозы закрыты и каким контролем. Работает в своём периметре: данные, артефакты и секреты наружу не уходят.

> Argus — стоокий страж из мифа: имя про суть платформы, которая видит весь ML-пайплайн и оберегает от угроз. Sirius — звезда-сторож, α Большого Пса; девиз — *the all-seeing watchdog star*.

## Что внутри

- **Zero-trust + единая точка входа.** Право на каждое действие проверяется на control-plane; в прод не попасть в обход — только через него.
- **Гейты на каждом переходе ЖЦ.** Приём артефактов (вредоносный pickle блокируется до десериализации), скан кода/данных/зависимостей, политика форматов по критичности, подпись и воспроизводимость.
- **Ручной аппрув-гейт.** Критичную версию в прод пускает другой MLSecOps — доказательный чеклист и separation of duties; аппрув привязан к hash артефакта (anti-TOCTOU).
- **Finding — сквозная сущность.** Все сканы пишут единую «сработку» с привязкой к активу и причастному; расхождения вердиктов триажатся вручную.
- **Реестры и карточки.** Модели, данные, решения, акторы — со сквозной связью **актив ⇄ актор ⇄ находка** и «историей актива» в один клик.
- **Карта покрытия угроз.** Угроза → контроль → live-статус (CEO-вью) на реальных данных, аудит-цепочка tamper-evident.
- **Неизменяемый аудит.** Append-only на БД-триггере + hash-chain; подмена записи видна.
- **Реальные тулзы.** modelaudit, OpenSSF model-signing, Semgrep, detect-secrets, pip-audit — поверх собственных сканеров; секреты в HashiCorp Vault.

Модели в демо — три НЕ-генеративные (sklearn на наборе iris): бустинг, линейная, anomaly-detection. Домен абстрактный, без привязки к отрасли.

## Интерфейс

Тёмная и светлая темы (SOC-консоль). Слева — тёмная, справа — светлая; клик по картинке открывает оригинал в полном размере.

**Ручной аппрув-гейт** — критичная версия уходит в прод только после решения MLSecOps: доказательный чеклист (модель-карта, воспроизводимость, подпись, нет открытых critical) и кнопки Аппрув/Отклонить с separation of duties.

<table>
<tr>
<td><img src="docs/_assets/img/02-approval-gate.png" alt="Ручной аппрув-гейт — тёмная тема"></td>
<td><img src="docs/_assets/img/light/02-approval-gate.png" alt="Ручной аппрув-гейт — светлая тема"></td>
</tr>
</table>

<details>
<summary><b>Ещё экраны</b> — карта пайплайна, покрытие, реестры, карточки, дашборд</summary>

<br>

**Карта пайплайна** — пространственный жизненный цикл модели, здоровье узлов, единая точка входа.

<table><tr>
<td><img src="docs/_assets/img/01-map.png" alt="Карта пайплайна — тёмная"></td>
<td><img src="docs/_assets/img/light/01-map.png" alt="Карта пайплайна — светлая"></td>
</tr></table>

**Карта покрытия (CEO-вью)** — угроза → контроль → live-статус.

<table><tr>
<td><img src="docs/_assets/img/03-coverage.png" alt="Карта покрытия — тёмная"></td>
<td><img src="docs/_assets/img/light/03-coverage.png" alt="Карта покрытия — светлая"></td>
</tr></table>

**Реестр моделей** — поиск, сортировка, KPI «с проблемами», владелец.

<table><tr>
<td><img src="docs/_assets/img/04-registry.png" alt="Реестр моделей — тёмная"></td>
<td><img src="docs/_assets/img/light/04-registry.png" alt="Реестр моделей — светлая"></td>
</tr></table>

**Карточка модели** — алерт-бар, проблемы, версии (lineage), решения гейта, таймлайн.

<table><tr>
<td><img src="docs/_assets/img/05-model-card.png" alt="Карточка модели — тёмная"></td>
<td><img src="docs/_assets/img/light/05-model-card.png" alt="Карточка модели — светлая"></td>
</tr></table>

**Карточка датасета** — богатая PII-схема с маскированием для ролей без допуска (DATA-04).

<table><tr>
<td><img src="docs/_assets/img/12-dataset-schema.png" alt="Карточка датасета — тёмная"></td>
<td><img src="docs/_assets/img/light/12-dataset-schema.png" alt="Карточка датасета — светлая"></td>
</tr></table>

**Реестр решений** — журнал аппрув-гейта (VIS-03) и принятий остаточного риска (GOV-02).

<table><tr>
<td><img src="docs/_assets/img/08-decisions.png" alt="Реестр решений — тёмная"></td>
<td><img src="docs/_assets/img/light/08-decisions.png" alt="Реестр решений — светлая"></td>
</tr></table>

**Карточка актора** — «кто что делал»: активность, инциденты причастности, решения, владение.

<table><tr>
<td><img src="docs/_assets/img/09-user-card.png" alt="Карточка актора — тёмная"></td>
<td><img src="docs/_assets/img/light/09-user-card.png" alt="Карточка актора — светлая"></td>
</tr></table>

**Live-дашборд** — поток сработок и таймлайн аудита в реальном времени.

<table><tr>
<td><img src="docs/_assets/img/14-dashboard.png" alt="Дашборд — тёмная"></td>
<td><img src="docs/_assets/img/light/14-dashboard.png" alt="Дашборд — светлая"></td>
</tr></table>

**Реестр данных** — чувствительность, карантин (DATA-01), PII, панель scoped-сканов (DATA-02/03/05).

<table><tr>
<td><img src="docs/_assets/img/06-data.png" alt="Реестр данных — тёмная"></td>
<td><img src="docs/_assets/img/light/06-data.png" alt="Реестр данных — светлая"></td>
</tr></table>

**Карточка датасета (карантин)** — недоверенный источник → карантин (DATA-01) + потребители (lineage).

<table><tr>
<td><img src="docs/_assets/img/07-dataset-card.png" alt="Карточка датасета — тёмная"></td>
<td><img src="docs/_assets/img/light/07-dataset-card.png" alt="Карточка датасета — светлая"></td>
</tr></table>

**Реестр пользователей** — люди и сервис-аккаунты с ролью, активностью, инцидентами.

<table><tr>
<td><img src="docs/_assets/img/10-users.png" alt="Реестр пользователей — тёмная"></td>
<td><img src="docs/_assets/img/light/10-users.png" alt="Реестр пользователей — светлая"></td>
</tr></table>

**Сработки** — единый список Finding с кликабельными активом и причастным.

<table><tr>
<td><img src="docs/_assets/img/13-findings.png" alt="Сработки — тёмная"></td>
<td><img src="docs/_assets/img/light/13-findings.png" alt="Сработки — светлая"></td>
</tr></table>

**Матрица ролей (RBAC)** — роль → действие из единого источника (zero-trust).

<table><tr>
<td><img src="docs/_assets/img/15-roles.png" alt="Матрица ролей — тёмная"></td>
<td><img src="docs/_assets/img/light/15-roles.png" alt="Матрица ролей — светлая"></td>
</tr></table>

**Инспектор прогона** — lineage (MON-02), сработки прогона и терминальный лог.

<table><tr>
<td><img src="docs/_assets/img/11-inspector.png" alt="Инспектор прогона — тёмная"></td>
<td><img src="docs/_assets/img/light/11-inspector.png" alt="Инспектор прогона — светлая"></td>
</tr></table>

**Сплэш-заставка** — экран загрузки с бутлогом этапов.

<table><tr>
<td><img src="docs/_assets/img/00-splash.png" alt="Заставка — тёмная"></td>
<td><img src="docs/_assets/img/light/00-splash.png" alt="Заставка — светлая"></td>
</tr></table>

</details>

## Запуск

```bash
cp .env.example .env      # поправь секреты
make up                   # core: control-plane + Postgres + Keycloak + Redis + MinIO + MLflow + reverse-proxy
# или: make up-full       # + observability (Loki/Grafana/Prometheus) + Gitea
```

Открыть: дашборд — http://localhost:8080 · карта пайплайна — `/map` · карта покрытия (CEO) — `/coverage` · Keycloak — `/auth/` · сервинг моделей — http://localhost:8001/models · Grafana (full) — http://localhost:3000.

Демо и тесты:

```bash
DEV_AUTH=1 make up      # локальное демо с dev-токенами ролей
make demo               # money-shot'ы по живому стеку
make pipeline           # сквозной ЖЦ одной модели: приём→скан→gate→аппрув-гейт→деплой→атака→decommission
cd tests && pip install -r requirements.txt && pytest -q   # BDD против живого стека
```

AuthN — через Keycloak; для локали без Keycloak можно `DEV_AUTH=1` и токены `Bearer dev:<user>:<role>` (иначе dev-токены отклоняются — fail-closed). Профили `core`/`full` — см. [roadmap](docs/roadmap.md).

> **Проверяющему:** пошаговый гайд «запуск и что потыкать» (UI, прогон сценариев, что попробовать «сломать») — [docs/evaluation.md](docs/evaluation.md).

## Статус

В разработке, итерации [И0–И6](docs/roadmap.md) — всё обязательное к сдаче готово, money-shot'ы гоняются одной командой (`make demo` / `make pipeline`). **73 pytest-функции green** (53 из 54 сценариев каталога; остаётся 1 — ShadowLogic, предел статического анализа, см. [risk-register](docs/threat-model/risk-register.md)). Документация идёт впереди кода намеренно: модель угроз и поведения (BDD) задают, что строим.

## Как датасеты и модели попадают в систему

Единственный путь — через control-plane по фиксированному контракту (handshake), а не прямым пушем в реестр:

1. **Датасет** регистрируется с источником и схемой; недоверенный источник → карантин (`DATA-01`). Тренеру отдаётся только admitted-версия (не карантинная), с PII-маскированием по допуску (`DATA-04`), и `dataset_version_id` как handle происхождения.
2. **Обучение** идёт снаружи (CI / Kubeflow / SageMaker), но обязано зафиксировать lineage: `code_commit`, `env_lock`, `dataset_version_id`.
3. **Артефакт модели** заводится через ingest-гейт: скан байтов в карантине без десериализации (`SUP-01`); вредоносный → блок, в реестр не попадает.
4. **Версия + lineage** регистрируется (критичные → `requires_validation`), затем подпись (`SUP-04`) и промоушен через policy-гейт с ручным аппрувом для критичных.

Запуск моделей (serving) идёт за рантайм-защитами и отчитывается о детектах обратно в control-plane (петля runtime → control-plane). Тренер и serving работают под сервис-аккаунтами без права `promote` — миновать гейт нельзя.

Пошаговый контракт с эндпоинтами и правами — в [docs/integration.md](docs/integration.md#контракт-интеграции-обучения-handshake); потоки жизненного цикла со схемами — в [architecture §8](docs/architecture.md#8-ключевые-потоки).

## Интеграция в контур заказчика

Sirius Argus — контур контроля, а не замена вашему стеку. Он встаёт в заданные точки и делает control-plane единственным путём в прод:

- **IdP (OIDC)** даёт роли из токена; **Git / CI** интегрируется вебхуком с HMAC; **тренер** (CI / Kubeflow / SageMaker / Vertex) ходит через REST-handshake под сервис-аккаунтом без права `promote`.
- **Реестр (MLflow), S3-хранилище, Postgres-аудит, Redis, Vault** — за единой точкой входа; компонент можно подменить на ваш (brownfield).
- Обязательно: единая точка входа, сетевая сегментация (serving не достаёт хранилище), OIDC с ролями, append-only аудит, ключ подписи офлайн.

Полный контракт интеграции, параметры (env) и чек-лист онбординга — в [docs/integration.md](docs/integration.md).

## Документация

| Документ | О чём |
|---|---|
| [docs/overview.md](docs/overview.md) | Пакет к сдаче: обзор всех узлов и защит на одной странице — читать первым |
| [docs/integration.md](docs/integration.md) | Встраивание в контур заказчика: что с чем, обязательные условия, параметры, чек-лист онбординга |
| [docs/evaluation.md](docs/evaluation.md) | Проверяющему: запуск, что потыкать в UI, прогон сценариев, попробовать «сломать» |
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
