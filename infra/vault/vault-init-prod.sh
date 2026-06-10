#!/usr/bin/env bash
# Vault prod init — DRAFT. ОПЕРАТОРСКИЙ шаг, выполняется ВРУЧНУЮ после `vault operator init`
# и unseal. Создаёт KV-движок, политику для control-plane и AppRole — вместо dev-сида под root.
# VAULT_TOKEN (операторский, с правами) задаётся в окружении и НЕ хранится в репозитории.
set -euo pipefail

export VAULT_ADDR="${VAULT_ADDR:-https://127.0.0.1:8200}"
: "${VAULT_TOKEN:?нужен операторский VAULT_TOKEN в окружении}"
# секреты приходят из секрет-стора оператора (НЕ из репозитория):
: "${SIGNING_SEED:?задай SIGNING_SEED (постоянный, из KMS/секрет-стора)}"
: "${SIRIUS_SERVICE_TOKEN:?задай SIRIUS_SERVICE_TOKEN (стойкий)}"

# 1) KV v2 под секреты Sirius — mount `secret` (как ждёт control-plane/app/vault.py: VAULT_KV_MOUNT)
vault secrets enable -path=secret kv-v2 2>/dev/null || echo "secret/ уже включён"

# 2) посев секретов (vault.py читает sirius/signing.seed и sirius/service-token.token под mount secret)
vault kv put secret/sirius/signing seed="$SIGNING_SEED"
vault kv put secret/sirius/service-token token="$SIRIUS_SERVICE_TOKEN"

# 3) Узкая политика: control-plane только читает свои секреты
vault policy write sirius-control-plane - <<'POLICY'
path "secret/data/sirius/*"     { capabilities = ["read"] }
path "secret/metadata/sirius/*" { capabilities = ["read", "list"] }
POLICY

# 4) AppRole для control-plane (короткоживущие токены, без root)
vault auth enable approle 2>/dev/null || echo "approle уже включён"
vault write auth/approle/role/control-plane \
  token_policies="sirius-control-plane" \
  token_ttl=1h token_max_ttl=4h \
  secret_id_ttl=24h

echo "=== выдать в .env.production (НЕ в репозиторий) ==="
echo -n "VAULT_ROLE_ID=";   vault read   -field=role_id   auth/approle/role/control-plane/role-id
echo -n "VAULT_SECRET_ID="; vault write  -field=secret_id -f auth/approle/role/control-plane/secret-id

# control-plane/app/vault.py теперь умеет AppRole-логин из env (VAULT_ROLE_ID/VAULT_SECRET_ID) —
# впишите выданные значения в .env.production. Фолбаком остаётся файловый том (dev).
