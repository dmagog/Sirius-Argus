# Безопасность репозитория Sirius

Этот проект — платформа безопасного MLOps, поэтому **сам репозиторий управляется теми же практиками**, которые платформа применяет к ML-активам (догфудинг). Безопасность — встроенная фича, а не патч.

## Применённые контроли (self-governance)

| Контроль | Где | Закрывает риск |
|---|---|---|
| Скан секретов (gitleaks) | CI-гейт + pre-commit | SECR-1 |
| Скан уязвимостей/секретов (Trivy fs) | CI-гейт | SC-1 |
| SAST (Semgrep) | CI-гейт (при наличии кода) | качество/инъекции |
| Локальные хуки (pre-commit) | dev-машина | shift-left |
| Fail-closed гейты | `.gitlab-ci.yml` | SC-1 (fail-open) |
| Обязательное ревью | CODEOWNERS + MR-аппрув | ACC-02 (разделение полномочий) |

## Рекомендуемые настройки проекта (GitLab → Settings)

Применяются к защищаемым веткам (`main`) — это настройки уровня проекта, не файлы:

- **Protected branch `main`:** запрет force-push, запрет прямого push (только через MR).
- **Require approvals:** ≥1 аппрув, **запрет аппрува автором MR** (separation of duties, ACC-02).
- **Require pipeline to succeed** перед merge (fail-closed на уровне ветки, закрывает GT-1).
- **Require Code Owner approval** на изменения `.gitlab-ci.yml`, `/docs/threat-model/`, `SECURITY.md`.
- **Signed commits** (рекомендуется) — целостность авторства.

> Эти настройки правятся в shared-проекте и затрагивают всех — применять с согласованием, не автоматически.

## Сообщить об уязвимости

Внутренний процесс: завести issue с меткой `security` (confidential) либо эскалировать роли **MLSecOps**. Реакция и классификация — см. [docs/runbooks/incident-response.md](docs/runbooks/incident-response.md).

## Контекст безопасности

- Модель угроз: [docs/threat-model/](docs/threat-model/)
- Реестр рисков и приоритеты: [docs/threat-model/risk-register.md](docs/threat-model/risk-register.md)
- Архитектурные решения: [docs/adr/](docs/adr/)
