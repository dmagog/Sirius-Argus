Feature: AuthN через Keycloak (OIDC)
  CRED-01: реальный токен Keycloak принимается, подделанный — отвергается.
  Сценарий пропускается, если Keycloak не поднят (нужен full/core стек).

  Scenario: CRED-01 — валидный OIDC-токен принимается, подделанный отвергается
    Given получен OIDC-токен Keycloak для роли DS
    When я зову whoami с этим токеном
    Then ответ 200 и роль DS
    When я порчу токен и зову whoami
    Then ответ 401 на подделанный токен
