Feature: Реестр и zero-trust RBAC
  ACC-01, ACC-04, ESC-01, MON-02 против живого control-plane (роли через dev-токены).

  Scenario: ACC-01 — DS не может промоутить в прод
    Given поднятый control-plane
    And зарегистрирована модель с воспроизводимой версией
    When DS пытается промоутить версию
    Then ответ 403

  Scenario: MON-02 — невоспроизводимая версия не уходит в прод
    Given поднятый control-plane
    And зарегистрирована модель с невоспроизводимой версией
    When MLSecOps пытается промоутить версию
    Then ответ 422

  Scenario: Happy — MLSecOps промоутит воспроизводимую версию, видно в blast-radius
    Given поднятый control-plane
    And зарегистрирована модель с воспроизводимой версией
    When MLSecOps пытается промоутить версию
    Then ответ 200
    And blast-radius по датасету показывает модель

  Scenario: ACC-04 — DS не читает секретный датасет
    Given поднятый control-plane
    And DE создал секретный датасет
    When DS читает секретный датасет
    Then ответ 403

  Scenario: ESC-01 — Product не читает секретный датасет (object-level)
    Given поднятый control-plane
    And DE создал секретный датасет
    When Product читает секретный датасет
    Then ответ 403

  Scenario: REG-01 — версия модели реально лежит в обёрнутом MLflow
    Given поднятый control-plane
    And реестр на MLflow доступен
    And зарегистрирована модель с воспроизводимой версией
    Then версия видна в MLflow-реестре через control-plane
    And прямой доступ к MLflow снаружи закрыт
