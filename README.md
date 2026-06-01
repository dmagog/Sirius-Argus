# Sirius Argus — безопасная MLOps-платформа

> **Argus** — стоокий всевидящий страж из мифа. Имя — про суть платформы: видеть весь ML-пайплайн и сторожить угрозы. Девиз: *the all-seeing watchdog star* (Sirius — звезда-сторож, α Большого Пса).

Платформа, которая делает безопасность **встроенной автоматической фичей** ML-пайплайна, а не патчем поверх. Видит весь жизненный цикл ML-решения, ловит угрозы на естественных переходах (приём данных → обучение → упаковка → деплой → рантайм → вывод) и даёт **полную видимость статуса защищённости**.

> Статус: в разработке, итеративно (И0 → И6). Документация опережает код — это сознательно: модель угроз и поведения (BDD) задают, что строим.

## Документация

| Документ | О чём |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Архитектура: компоненты, ER-модель, ЖЦ, потоки, карта покрытия (Mermaid-схемы) |
| [docs/threat-model/personas.md](docs/threat-model/personas.md) | Персоны атакующих (A1–A21) и защитников (D1–D10) |
| [docs/threat-model/bdd-catalog.md](docs/threat-model/bdd-catalog.md) | 41 BDD-сценарий = модель угроз + acceptance-тесты + демо + карта покрытия |
| [docs/threat-model/risk-register.md](docs/threat-model/risk-register.md) | Пер-узловой реестр рисков, приоритет L×I, обработка/владелец |
| [docs/threat-model/security-kpis.md](docs/threat-model/security-kpis.md) | Измеримая безопасность: KPI/SLO |
| [docs/adr/](docs/adr/) | Журнал архитектурных решений |
| [docs/runbooks/incident-response.md](docs/runbooks/incident-response.md) | Реакция на инциденты + доступность/DR |
| [SECURITY.md](SECURITY.md) | Безопасность самого репозитория (догфудинг) |

## Безопасность этого репозитория

Репозиторий управляется теми же практиками, что платформа применяет к ML: **fail-closed CI-гейты** (gitleaks, Trivy), **pre-commit**-хуки, обязательное ревью (CODEOWNERS). Подробно — [SECURITY.md](SECURITY.md).

## Запуск

> Появится на итерации И0: вся система поднимается одной командой.

```bash
docker compose up
```
