# Безопасность репозитория Sirius Argus

Этот проект — платформа безопасного MLOps, поэтому **сам репозиторий управляется теми же практиками**, которые платформа применяет к ML-активам (догфудинг). Безопасность — встроенная фича, а не патч.

## Применённые контроли (self-governance)

| Контроль | Где | Закрывает риск |
|---|---|---|
| Скан секретов (gitleaks) | pre-commit (локально) + обязательный гейт GitHub Actions (`.github/workflows/security.yml`, джоб `static-security`) | SECR-1 |
| Скан зависимостей (pip-audit) | обязательный гейт GitHub Actions (джоб `static-security`, без `--ignore-vuln`); Trivy fs — reference-only в запаркованном `ci/gitlab-ci.reference.yml` | SC-1 |
| SAST (bandit + semgrep) | обязательный гейт GitHub Actions (джоб `static-security`) | качество/инъекции |
| Локальные хуки (pre-commit) | dev-машина | shift-left |
| Fail-closed гейты | GitHub Actions: required status checks `static-security` + `compose-validate` (strict) на `main` | SC-1 (fail-open) |
| Владелец изменений (CODEOWNERS) | задаёт владельца чувствительных путей; обязательное ревью ≥1 / запрет self-approve — план при росте команды (сейчас solo-merge) | ACC-02 (разделение полномочий) |

> **Реальный гейт — GitHub Actions** (`.github/workflows/security.yml`): джобы `static-security` (bandit + pip-audit + gitleaks + semgrep) и `compose-validate`. Канон репозитория — GitHub (`github.com/dmagog/Sirius-Argus`); GitLab — legacy-remote. Старый `ci/gitlab-ci.reference.yml` запаркован как reference-only (Trivy fs там не активен) и в гейте не участвует.

## Настройки репозитория (GitHub → Settings → Branches)

Применяются к защищаемой ветке (`main`) — это настройки уровня репозитория, не файлы:

- **Branch protection `main` (включена 11.06.2026):** запрет force-push, запрет прямого push (только через PR).
- **Required status checks (strict):** `static-security` + `compose-validate` обязаны пройти перед merge (fail-closed на уровне ветки, закрывает GT-1).
- **Обязательное ревью:** сейчас **не включено** — solo-merge сохранён, `enforce_admins=false`. Required approval ≥1 и запрет self-approve — план при росте команды.
- **CODEOWNERS** задаёт владельца изменений `ci/`, `/docs/threat-model/`, `SECURITY.md`.
- **Signed commits** (рекомендуется) — целостность авторства.

> Эти настройки правятся на уровне репозитория и затрагивают всех с доступом — менять с согласованием, не автоматически.

## Сообщить об уязвимости

Внутренний процесс: завести приватный GitHub issue с меткой `security` либо эскалировать роли **MLSecOps**. Реакция и классификация — см. [docs/runbooks/incident-response.md](docs/runbooks/incident-response.md).

## Контекст безопасности

- Модель угроз: [docs/threat-model/](docs/threat-model/)
- Реестр рисков и приоритеты: [docs/threat-model/risk-register.md](docs/threat-model/risk-register.md)
- Архитектурные решения: [docs/adr/](docs/adr/)
