# Sirius Argus — безопасная MLOps-платформа

Argus — стоокий страж из мифа: имя про суть платформы, которая видит весь ML-пайплайн и оберегает от угроз. Sirius — звезда-сторож, α Большого Пса; девиз — *the all-seeing watchdog star*.

Sirius Argus встраивает безопасность прямо в ML-пайплайн: проверки запускаются сами на переходах от приёма данных до вывода модели из эксплуатации. Для каждого актива видно, какие угрозы закрыты и каким контролем.

> Статус: в разработке, итерации И0–И6. Документация идёт впереди кода намеренно — модель угроз и поведения (BDD) задают, что строим.

## Документация

| Документ | О чём |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Архитектура: компоненты, ER-модель, жизненный цикл, потоки, карта покрытия (схемы Mermaid) |
| [docs/threat-model/personas.md](docs/threat-model/personas.md) | Персоны атакующих (A1–A22) и защитников (D1–D10), с кодовыми именами |
| [docs/threat-model/bdd-catalog.md](docs/threat-model/bdd-catalog.md) | 42 BDD-сценария: разом модель угроз, acceptance-тест, шаг демо и строка карты покрытия |
| [docs/threat-model/risk-register.md](docs/threat-model/risk-register.md) | Пер-узловой реестр рисков: приоритет L×I, обработка, владелец |
| [docs/threat-model/security-kpis.md](docs/threat-model/security-kpis.md) | Измеримая безопасность: KPI и SLO |
| [docs/adr/](docs/adr/) | Журнал архитектурных решений |
| [docs/runbooks/incident-response.md](docs/runbooks/incident-response.md) | Реакция на инциденты, доступность и восстановление |
| [SECURITY.md](SECURITY.md) | Безопасность самого репозитория |

## Безопасность этого репозитория

Репозиторий живёт по тем же правилам, что платформа применяет к ML: стоят pre-commit-хуки (gitleaks), чувствительные изменения проходят ревью через CODEOWNERS, конфиг fail-closed гейтов (gitleaks, Trivy, Semgrep) хранится как reference в `ci/`. Серверный гейт по плану — локальный control-plane как CI (ADR-0002); GitLab CI запаркован, потому что gitlab.com не запускает пайплайны на аккаунте владельца. Подробности — в [SECURITY.md](SECURITY.md).

## Запуск

Появится на итерации И0: вся система поднимается одной командой.

```bash
docker compose up
```
