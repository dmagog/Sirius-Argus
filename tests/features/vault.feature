Feature: Секреты в HashiCorp Vault (AppRole, политика, аудит, revoke)
  CRED-02: секреты (signing-ключ, service-token) выдаются по политике least-privilege, доступ —
  в аудите Vault, и их можно мгновенно отозвать. control-plane аутентифицируется по AppRole и
  тянет секреты из Vault (фолбэк на env, если Vault недоступен).

  Scenario: CRED-02 — control-plane получает секреты из Vault
    Given поднятый control-plane
    Then control-plane подключён к Vault и источник секретов — vault

  Scenario: CRED-02 — политика ограничивает доступ, secret-id отзывается мгновенно
    Given поднятый control-plane
    When прогоняем в Vault выдачу по политике и отзыв secret-id
    Then секрет выдан по политике, путь вне политики запрещён, после revoke логин отклонён
