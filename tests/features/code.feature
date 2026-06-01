Feature: SAST на код (ML-aware)
  CODE-01: статический скан кода/ноутбуков ловит опасные паттерны (eval/exec/os.system/...).
  Код не исполняется — только разбирается в AST. Pattern-based MVP; полный Semgrep-гейт на PR — в И3.

  Scenario: CODE-01 — небезопасный паттерн в коде ловится
    Given поднятый control-plane
    When DS отправляет на скан код с os.system
    Then скан помечает код небезопасным
    And создаётся сработка insecure-code

  Scenario: CODE-01 — чистый код проходит
    Given поднятый control-plane
    When DS отправляет на скан безопасный код
    Then скан помечает код чистым

  Scenario: ACC-06 — захардкоженный секрет в коде флагается
    Given поднятый control-plane
    When DS отправляет на скан код с захардкоженным секретом
    Then скан помечает код небезопасным
    And создаётся сработка secret-exposed
