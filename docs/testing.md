# Sirius Argus — Стратегия тестирования

> Принцип: **test-first в BDD-стиле** (outside-in). Поведение — угроза и ответ системы — описывается сценарием **до кода**; код итерации делает сценарий зелёным. Сценарий = спека + приёмочный тест + шаг демо + строка карты покрытия ([ADR-0004](adr/0004-bdd-methodology.md)).

## Что значит «test-first» у нас
- 44 BDD-сценария ([bdd-catalog](threat-model/bdd-catalog.md)) написаны раньше кода, статус `spec`.
- Код каждой итерации переводит свой набор `spec` → `green`.
- «Зелёный» = проходящий `pytest-bdd` против **живой системы** (`docker compose up`), не моки.
- Зелёная колонка в [roadmap](roadmap.md) — это Definition of Done итерации.

Почему поведенческий test-first, а не «unit-TDD везде»: угроза — это поведение, и мы проверяем, что система **отрабатывает** его (блок / `Finding` / запись в аудит), а не что функция вернула ожидаемое значение.

## Пирамида тестов

| Уровень | Что покрывает | Инструмент | Test-first |
|---|---|---|---|
| Приёмка (BDD) | 44 поведения против живого стека | pytest-bdd + httpx + проверки БД | да — сценарии раньше кода |
| Unit | security-критичная чистая логика: policy-движок (матрица гейтов по критичности), hash-chain аудита, RBAC/object-authz, политика форматов, extraction-детектор | pytest | да — TDD там, где окупается |
| Smoke | UI / шаблоны / glue | pytest, минимально | нет — без фанатизма |

Принцип: test-first для поведений и критичной логики; на тривиальный клей тесты не пишем.

## Как сценарий становится тестом
1. `.feature` (Gherkin) — спека (готово).
2. step-definitions на pytest-bdd: `Given/When/Then` дёргают API живой системы (control-plane, serving), не моки.
3. `pytest` против `compose up` → green = поведение доказано. Тот же прогон виден в таймлайне UI — это демо. Куратор может запустить тесты сам.

Пример (`SUP-01`):

```gherkin
Scenario: SUP-01 — Вредоносный артефакт блокируется до загрузки
  Given актор DS затягивает модель из недоверенного источника
  And  артефакт содержит pickle с исполняемым payload
  When артефакт проходит ingestion-гейт
  Then создаётся Finding(severity=critical, tool=modelscan)
  And  в аудит пишется "ingestion.blocked"
  And  модель не появляется в реестре
```

```python
@when("артефакт проходит ingestion-гейт")
def submit(ctx, client):
    ctx.resp = client.post("/api/ingest", files={"f": MALICIOUS_PKL}, token=ctx.ds)

@then('создаётся Finding(severity=critical, tool=modelscan)')
def finding(db):
    assert db.findings(severity="critical", tool="modelscan")      # реальная запись

@then("модель не появляется в реестре")
def not_registered(ctx, registry):
    assert ctx.resp.status_code == 422 and not registry.has(MALICIOUS_PKL.hash)
```

## Цикл итерации (outside-in red → green)
`spec` → пишем step-defs (красные, фичи ещё нет) → строим **минимум**, пока не позеленели → DoD итерации.

## Что проверяем в безопасности (негативные тесты)
Главное — утверждать, что **плохое предотвращено и записано** (fail-closed): блок + `Finding` + `AuditEvent` + объект не попал в реестр/прод. Happy-path вторичен. Это отличает security-тесты от обычных: мы тестируем отказ, а не успех.

## Тест-харнес
- Гоняется против поднятого `docker compose` (тестовый профиль).
- Фикстуры: сид-юзеры под каждую роль, sample-артефакты — в т.ч. **безвредный «вредоносный» pickle** (payload только ставит маркер-файл; тест проверяет блок **до** загрузки, маркер не появляется).
- Курица-яйцо: харнес + первый зелёный сценарий (`ACC-05`) закладываются в **И0**.
- HITL и ручные шаги: автоматизируем **принуждение** (промоушен заблокирован до аппрува), сам approve симулируем через API.
- Связь с видимостью: статус сценария (`green`/`spec`/`fail`) питает [карту покрытия](architecture.md) и [KPI](threat-model/security-kpis.md) — «статус защищённости» берётся из проходящих тестов.

## Запуск
`pytest` после `docker compose up`. В перспективе — шаг в control-plane как CI ([ADR-0002](adr/0002-gitea-control-plane-ci.md)), тот же набор гейтов.
