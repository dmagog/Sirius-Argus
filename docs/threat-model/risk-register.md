# Sirius Argus — Реестр рисков (по узлам, с приоритизацией)

> Проходим по **каждому узлу** архитектуры ([architecture.md](../architecture.md) §5) и перечисляем риски, затем **приоритизируем по «вероятность × опасность»** и фиксируем **обработку и владельца**. Персоны — [personas.md](personas.md); поведения-митигации — [bdd-catalog.md](bdd-catalog.md).

## Методология оценки

- **Likelihood (L)** и **Impact (I)** — по шкале 1–5. **Score = L × I** (1–25).
- Уровень: **Критический ≥ 15** · **Высокий 9–14** · **Средний 4–8** · **Низкий ≤ 3**.
- **Обработка** (risk treatment): `Mitigate` (есть контроль) · `Accept` (осознанно принимаем остаточный) · `Transfer` · `Avoid`.
- **Владелец** — РОЛЬ (D1 MLSecOps · D3 DE · D8 Data Steward · D9 Platform/SRE · D7 IR), не личность.
- Префикс ID = узел (CP/ML/MO/GT/PG/SC/SV/NET/SECR/ID/DATA/HOST).
- ID рисков — **одна цифра** (`SC-1`); ID BDD-сценариев в [bdd-catalog.md](bdd-catalog.md) — **две цифры** (`SC-01`). Совпадающие префиксы (`DATA`/`SC`/`RB`) различаются числом цифр.

## Узлы и почему они — мишени

| Узел | Активы | Экспозиция | Почему интересен |
|---|---|---|---|
| **Control Plane** | токены, authZ, оркестрация гейтов | единственное наружу | компрометация = обход всех гейтов; «корона» |
| **MLflow** | реестр, версии, артефакты | внутр. сеть, **нет RBAC** | подмена статуса/артефакта → протащить модель |
| **MinIO** | артефакты, датасеты | внутр. сеть | эксфильтрация/подмена, TOCTOU |
| **Gitea + CI** | код, пайплайн, единая точка в прод | внутр. сеть | обход branch protection, отравление пайплайна |
| **PostgreSQL** | метаданные, аудит, findings | внутр. сеть | подмена истории и статусов сработок |
| **security/ (гейты)** | сами проверки | вызывается CP/CI | fail-open/evasion = тихий пропуск зла |
| **Serving** | модели в проде, прод-периметр | наружу (gateway) | extraction/evasion/lateral, загрузка неодобренного |
| **Сеть / секреты / хост** | связность, креды, рантайм | сквозное | боковое движение, утечка кред, граница доверия |
| **Keycloak** | identity, токены, роли | внутр. сеть (логин через proxy) | компрометация = захват всех identity; SPOF authN |
| **Брокер / Observability** | события, очередь сканов, логи, метрики | внутр. сеть | инъекция/подмена событий; утечка секретов в логи |

## Реестр рисков — отсортирован по Score

### 🔴 Критический (15)

| ID | Узел | Риск | L | I | Score | Обработка · Владелец | Митигация (сценарий) |
|---|---|---|:--:|:--:|:--:|---|---|
| CP-1 | Control Plane | Компрометация CP → полный обход гейтов | 3 | 5 | **15** | Mitigate · D9/D1 | минимизация поверхности, object-authz, скан своих зависимостей (CI-01, ESC-01, SC-01) |
| ML-1 | MLflow | Прямой тамперинг метаданных реестра (нет RBAC) | 3 | 5 | **15** | Mitigate · D9 | писать может только CP + netpolicy + integrity (REG-01, RT-06) |
| GT-2 | Gitea/CI | Компрометация пайплайна/раннера/образа | 3 | 5 | **15** | Mitigate · D9 | пины образов, least-priv раннер, подписанный пайплайн (CI-01) |
| SC-1 | security/ | Fail-open при ошибке/обходе сканера | 3 | 5 | **15** | Mitigate · D1 | **fail-closed по умолчанию**, нельзя skip без authz+audit (VIS-04) |

### 🟠 Высокий (9–14)

| ID | Узел | Риск | L | I | Score | Обработка · Владелец | Митигация (сценарий) |
|---|---|---|:--:|:--:|:--:|---|---|
| CP-2 | Control Plane | SSRF / confused deputy к внутренним сервисам | 3 | 4 | 12 | Mitigate · D1 | egress allow-list, нет user-controlled URL |
| CP-3 | Control Plane | IDOR / привилегированная эскалация | 3 | 4 | 12 | Mitigate · D1 | object-level authz (ESC-01) |
| ML-2 | MLflow | Эксплуатация известных CVE MLflow | 3 | 4 | 12 | Mitigate · D9 | пины, не наружу, скан (SC-01) |
| MO-1 | MinIO | Утёкшие S3-ключи → эксфильтрация/подмена | 3 | 4 | 12 | Mitigate · D9 | scoped keys, ротация, netpolicy (CRED-01) |
| SC-2 | security/ | Evasion сканера (ShadowLogic/обфускация) | 3 | 4 | 12 | Mitigate + Accept(residual) · D1 | мульти-тулзы + валидация (SUP-06) |
| SC-3 | security/ | Гейт отключён/пропущен («шум → выключили») | 3 | 4 | 12 | Mitigate · D1 | нельзя skip без authz+audit (VIS-04) |
| NET-1 | Сеть | Плоская внутр. сеть без auth → lateral | 3 | 4 | 12 | Mitigate · D9 | сегментация, per-service creds (RT-06) |
| SECR-1 | Секреты | Секреты в .env / коммитах | 3 | 4 | 12 | Mitigate · D9 | gitleaks, .gitignore, secret store (ACC-06) |
| ID-1 | Identity | Кража / replay токена | 3 | 4 | 12 | Mitigate · D9 | short-lived scoped токены, ротация (CRED-01) |
| DATA-3 | Данные | Утечка PII (логи/датасеты) | 3 | 4 | 12 | Mitigate · D3 | маскирование (DATA-04) |
| ML-3 | MLflow | Перезапись артефакта → pickle RCE | 2 | 5 | 10 | Mitigate · D9 | integrity/подпись + admission (SUP-05, TOCTOU-01) |
| MO-2 | MinIO | TOCTOU-подмена артефакта после скана | 2 | 5 | 10 | Mitigate · D1 | подпись/хеш при загрузке (TOCTOU-01) |
| GT-1 | Gitea/CI | Обход branch protection / force-push в main | 2 | 5 | 10 | Mitigate · D9 | protection + required checks (SUP-03) |
| PG-4 | Postgres | Утечка DB-кред | 2 | 5 | 10 | Mitigate · D9 | secrets, netpolicy (CRED-01) |
| SC-4 | security/ | Компрометация зависимости самих сканеров | 2 | 5 | 10 | Mitigate · D1 | пин + скан собственных зависимостей (SC-01) |
| SV-1 | Serving | Загрузка неподписанной/неодобренной модели | 2 | 5 | 10 | Mitigate · D1 | admission control (SUP-04, TOCTOU-01) |
| KC-1 | Keycloak | Компрометация Keycloak → захват identity/токенов (SPOF authN) | 2 | 5 | 10 | Mitigate · D9 | внутр. сеть, realm-as-code, не наружу, ротация ключей (ADR-0007) |
| SV-3 | Serving | Model extraction | 3 | 3 | 9 | Mitigate · D1 | rate-limit + detect (RT-01) |
| SV-4 | Serving | Adversarial evasion | 3 | 3 | 9 | Mitigate · D1 | детектор (RT-02) |
| SV-6 | Serving | Denial-of-wallet / истощение ресурсов | 3 | 3 | 9 | Mitigate · D9 | rate-limit + квоты (DOW-01) |
| SV-7 | Serving | Распределённый DDoS на gateway → недоступность инференса | 3 | 3 | 9 | Mitigate + Accept(volumetric) · D9 | reverse-proxy, global/per-IP rate-limit, load-shedding (DOS-01) |
| ID-2 | Identity | Неотозванный доступ (orphaned) | 3 | 3 | 9 | Mitigate · D9 | lifecycle revoke (ACC-03) |

### 🟡 Средний (4–8)

| ID | Узел | Риск | L | I | Score | Обработка · Владелец | Митигация (сценарий) |
|---|---|---|:--:|:--:|:--:|---|---|
| CP-4 | Control Plane | Утечка секретов из CP (логи/env) | 2 | 4 | 8 | Mitigate · D9 | secret mgmt, не логировать секреты |
| CP-5 | Control Plane | DDoS на единую точку входа → недоступность управления | 2 | 4 | 8 | Mitigate + Accept(volumetric) · D9 | reverse-proxy, rate-limit, load-shedding (DOS-01) |
| MO-3 | MinIO | Мисконфиг бакета (анонимный доступ) | 2 | 4 | 8 | Mitigate · D9 | private by default |
| GT-3 | Gitea/CI | Подделка вебхука (fake → PR passed) | 2 | 4 | 8 | Mitigate · D9 | HMAC-секрет вебхука (CI-01) |
| PG-1 | Postgres | Подмена/удаление аудита | 2 | 4 | 8 | Mitigate · D1 | hash-chain (MON-04) |
| PG-2 | Postgres | Манипуляция статусом finding (TP→FP) | 2 | 4 | 8 | Mitigate · D1 | authz + audit (VIS-04) |
| PG-3 | Postgres | SQLi через CP | 2 | 4 | 8 | Mitigate · D9 | параметризация/ORM |
| SV-2 | Serving | Боковое движение из serving к MLflow/MinIO | 2 | 4 | 8 | Mitigate · D9 | per-service creds, netpolicy (RT-06) |
| DATA-1 | Данные | Отравление/label-flip на приёме | 2 | 4 | 8 | Mitigate · D3/D8 | trusted source + качество (DATA-01/02) |
| DATA-2 | Данные | Отравление петли дообучения | 2 | 4 | 8 | Mitigate · D3 | provenance retrain (FB-01) |
| RB-1 | Реестр | Rollback на уязвимую версию | 2 | 4 | 8 | Mitigate · D1 | version policy (RB-01) |
| SV-5 | Serving | Membership/attribute inference | 2 | 3 | 6 | Accept(partial) · D1 | output reduction (RT-03/04); остаток принят |
| HOST-1 | Хост | Компрометация хоста / docker-демона | 1 | 5 | 5 | **Accept** · D9 | граница доверия — допущение (вне скоупа) |
| GT-4 | Gitea/CI | Вредоносный Gitea-плагин/action | 1 | 4 | 4 | Mitigate · D9 | allow-list плагинов |
| BUS-1 | Брокер | Инъекция/подмена событий → ложные Finding или обход | 2 | 4 | 8 | Mitigate · D9 | ACL топиков, аутентификация клиентов, дубль критичных событий в tamper-evident аудит (ADR-0008) |
| OBS-1 | Observability | Утечка секретов/PII в операционные логи | 2 | 4 | 8 | Mitigate · D9/D3 | маскирование в логах, доступ к лог-стору по ролям (ADR-0009) |

> Низкий уровень (≤3) пуст осознанно: для платформы безопасности «тривиальных» рисков почти нет.

## Принятые остаточные риски (Accept)

Зафиксированы явно, а не замолчаны (зрелость МУ):

| Риск | Почему принимаем | Владелец |
|---|---|---|
| HOST-1 — компрометация хоста/докер-демона | граница доверия: ноутбук/хост считаем доверенным; защита хоста вне скоупа MLSecOps-контура | D9 |
| SC-2 (остаток) — ShadowLogic-класс граф-бэкдоров | автосканеры pickle их не ловят; смягчаем валидацией/red-team, остаток принимаем и роутим в HITL (SUP-06) | D1 |
| SV-5 (остаток) — membership/attribute inference | полностью не устраняется без DP; снижаем output-reduction, остаток принят | D1 |
| Объёмный L3/L4 DDoS (SV-7/CP-5 остаток) | сетевой scrubbing / anti-DDoS-провайдер вне ноутбука; держим app-layer (DOS-01), сетевую защиту принимаем как допущение | D9 |
| Side-channel / weight-stego (edge) | research-grade, вне скоупа окна; см. personas.md §6 | D1 |

## Что это значит для порядка работ

Критический и верх высокого кластеризуются **не вокруг атак на модель, а вокруг контура контроля**: CP-1, ML-1, GT-2, SC-1, NET-1, CP-2/3. Вывод для итераций (см. [ADR-0005](../adr/0005-fail-closed-protect-enforcer.md)):

1. **И0/И1 — самозащита контура с самого начала**: сетевая изоляция (наружу только CP и serving-gateway), per-service креды, object-level authz, **fail-closed** гейты, short-lived токены, hash-chain аудита, скан собственных зависимостей.
2. **И2/И3 — supply-chain и единая точка входа** (SUP-01/03, CI-01, REG-01).
3. **И4 — runtime** (extraction/evasion/DoW/DDoS) — важно для демо, но не «корона».
4. **Остаточные** — приняты явно (таблица выше), а не замолчаны.

Главный тезис для защиты проекта: **мы защищаем в первую очередь то, что само защищает** — компрометация энфорсера обнуляет все остальные контроли.
