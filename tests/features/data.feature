Feature: Контроль источников данных (gate на закачку датасета)
  DATA-01: датасет из недоверенного источника попадает в карантин + сработка;
  из доверенного — активен.

  Scenario: DATA-01 — недоверенный источник в карантине
    Given поднятый control-plane
    When DE создаёт датасет из недоверенного источника
    Then датасет в статусе quarantined
    And появляется сработка untrusted-source по датасету

  Scenario: DATA-01 — доверенный источник активен
    Given поднятый control-plane
    When DE создаёт датасет из доверенного источника
    Then датасет в статусе active

  Scenario: DATA-04 — PII-колонка маскируется без допуска
    Given поднятый control-plane
    And DE создал датасет с PII-колонкой
    When DS читает схему датасета
    Then PII-значение замаскировано
    And не-PII значение видно

  Scenario: DATA-04 — с допуском PII видно
    Given поднятый control-plane
    And DE создал датасет с PII-колонкой
    When MLSecOps читает схему датасета
    Then PII-значение видно

  Scenario: AUD-07 — UI-карточка маскирует PII без допуска
    Given поднятый control-plane
    And DE создал датасет с PII-колонкой
    When DS открывает UI-карточку датасета
    Then в UI PII-значение замаскировано

  Scenario: AUD-07 — UI-карточка показывает PII с допуском
    Given поднятый control-plane
    And DE создал датасет с PII-колонкой
    When MLSecOps открывает UI-карточку датасета
    Then в UI PII-значение видно
