# Журнал архитектурных решений (ADR)

Зачем: проект сам лечит боль «специалист ушёл — никто не помнит, почему так сделано». Применяем это к себе — фиксируем ключевые решения, чтобы система была передаваемой и воспроизводимой.

Формат: MADR-lite (Статус · Контекст · Решение · Последствия · Альтернативы). Роли — системные, без привязки к личностям.

| № | Решение | Статус |
|---|---|---|
| [0001](0001-mlflow-wrapped.md) | MLflow обёрнут, доступен только через control-plane | Accepted |
| [0002](0002-gitea-control-plane-ci.md) | Gitea + control-plane как CI = единая точка входа в прод | Accepted |
| [0003](0003-no-keycloak-inapp-rbac.md) | Без Keycloak — zero-trust RBAC в control-plane | Accepted |
| [0004](0004-bdd-methodology.md) | BDD: угроза = поведение; сценарий = МУ + тест + демо + карта | Accepted |
| [0005](0005-fail-closed-protect-enforcer.md) | Fail-closed гейты; защищаем контур контроля в первую очередь | Accepted |
| [0006](0006-model-signing-provenance.md) | Подпись моделей и провенанс; verify-on-consume; подпись ≠ безопасность | Accepted |
