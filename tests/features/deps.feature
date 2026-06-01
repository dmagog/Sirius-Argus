Feature: Скан зависимостей (gate перед продом)
  SUP-03: зависимость с известной CVE флагается и не проходит гейт; чистые — проходят.

  Scenario: SUP-03 — уязвимая зависимость флагается
    Given поднятый control-plane
    When DS отправляет на скан requirements с уязвимой зависимостью
    Then скан помечает зависимости небезопасными
    And создаётся сработка vulnerable-dependency

  Scenario: SUP-03 — чистые зависимости проходят
    Given поднятый control-plane
    When DS отправляет на скан чистые requirements
    Then скан помечает зависимости чистыми
