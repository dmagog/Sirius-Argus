#!/usr/bin/env bash
# Vault prod init — DRAFT. ОПЕРАТОРСКИЙ шаг, выполняется ВРУЧНУЮ после `vault operator init`
# и unseal. Создаёт KV-движок, политику для control-plane и AppRole — вместо dev-сида под root.
# VAULT_TOKEN (операторский, с правами) задаётся в окружении и НЕ хранится в репозитории.
set -euo pipefail

export VAULT_ADDR="${VAULT_ADDR:-https://127.0.0.1:8200}"
: "${VAULT_TOKEN:?нужен операторский VAULT_TOKEN в окружении}"

# 1) KV v2 под секреты Sirius
vault secrets enable -path=sirius kv-v2 2>/dev/null || echo "sirius/ уже включён"

# 2) Узкая политика: control-plane только читает свои секреты
vault policy write sirius-control-plane - <<'POLICY'
path "sirius/data/*"     { capabilities = ["read"] }
path "sirius/metadata/*" { capabilities = ["read", "list"] }
POLICY

# 3) AppRole для control-plane (короткоживущие токены, без root)
vault auth enable approle 2>/dev/null || echo "approle уже включён"
vault write auth/approle/role/control-plane \
  token_policies="sirius-control-plane" \
  token_ttl=1h token_max_ttl=4h \
  secret_id_ttl=24h

echo "=== выдать в .env.production (НЕ в репозиторий) ==="
echo -n "VAULT_ROLE_ID=";   vault read   -field=role_id   auth/approle/role/control-plane/role-id
echo -n "VAULT_SECRET_ID="; vault write  -field=secret_id -f auth/approle/role/control-plane/secret-id

# TODO (code-change): control-plane/app/vault.py — логин по AppRole (role_id/secret_id →
# short-lived token), а не VAULT_TOKEN=root. Сейчас приложение ходит по статичному токену.
