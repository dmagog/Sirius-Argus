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

  Scenario: SC-01 — собственные зависимости платформы сканируются и чисты
    Given поднятый control-plane
    When сканируются собственные requirements платформы
    Then скан помечает зависимости чистыми

  Scenario: SUP-02/08 — тайпсквоттинг и dependency confusion флагаются
    Given поднятый control-plane
    When DS отправляет на скан requirements с тайпсквоттингом и неприпиненным внутренним пакетом
    Then скан помечает зависимости небезопасными
    And создаётся сработка typosquat-dependency
    And создаётся сработка dependency-confusion
