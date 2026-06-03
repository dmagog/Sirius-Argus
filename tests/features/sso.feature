Feature: Единый вход (SSO) в ops-консоли через Keycloak
  ADR-0012: оператор логинится в ops-консоли единым аккаунтом Keycloak (realm sirius),
  без локального пароля сервиса. Сценарии пропускаются, если Grafana/Gitea/Keycloak или
  OIDC-клиенты не подняты (нужен профиль full + keycloak-init).

  Scenario: SSO-01 — оператор входит в Grafana аккаунтом Keycloak
    Given Grafana с включённым OIDC-входом через Keycloak
    When оператор ds проходит OIDC-вход в Grafana
    Then Grafana-сессия принадлежит ds

  Scenario: SSO-02 — оператор входит в Gitea аккаунтом Keycloak
    Given Gitea с включённым OIDC-источником Keycloak
    When оператор ds проходит OIDC-вход в Gitea
    Then Gitea-сессия аутентифицирована
