Feature: AuthN и доступ
  Поведения ACC-05 и AUTH-01 против живого control-plane.

  Scenario: ACC-05 — запрос без токена отклоняется и пишется в аудит
    Given поднятый control-plane
    When я обращаюсь к "/api/whoami" без токена
    Then ответ 401
    And в аудит-таймлайне есть access.denied

  Scenario: AUTH-01 — невалидный токен отклоняется (fail-closed)
    Given поднятый control-plane
    When я обращаюсь к "/api/whoami" с токеном "garbage"
    Then ответ 401
