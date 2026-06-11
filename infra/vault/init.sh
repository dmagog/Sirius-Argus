#!/bin/sh
# Одноразовый seed Vault для Sirius Argus: аудит + AppRole + политика + KV-секреты.
# Демонстрирует паттерн «выдача секретов по политике, с аудитом и быстрым revoke/rotate».
# Vault в dev-режиме (auto-unseal, фикс. root-токен) — воспроизводимо для демо; в проде —
# file/raft backend + auto-unseal (KMS/HSM), здесь честно scoped.
set -e
export VAULT_ADDR="${VAULT_ADDR:-http://vault:8200}"

# ждём готовности Vault
for i in $(seq 1 30); do
  vault status >/dev/null 2>&1 && break
  sleep 1
done

# аудит доступа к секретам → stdout (виден в логах vault); каждый read секрета логируется
vault audit list 2>/dev/null | grep -q '^file/' || vault audit enable file file_path=stdout

# KV v2: секреты платформы
vault secrets list 2>/dev/null | grep -q '^secret/' || vault secrets enable -path=secret kv-v2
vault kv put secret/sirius/signing seed="${SIGNING_SEED:-}"
vault kv put secret/sirius/service-token token="${SIRIUS_SERVICE_TOKEN:-}"

# политика наименьших привилегий: control-plane читает ТОЛЬКО свои секреты
cat > /tmp/cp.hcl <<'EOF'
path "secret/data/sirius/*"        { capabilities = ["read"] }
path "database/creds/sirius-cp"    { capabilities = ["read"] }
EOF
vault policy write control-plane /tmp/cp.hcl

# AppRole для control-plane (вместо «секрета-зеро» в env): role_id + secret_id в общий том
vault auth list 2>/dev/null | grep -q '^approle/' || vault auth enable approle
vault write auth/approle/role/control-plane token_policies=control-plane token_ttl=1h token_max_ttl=4h secret_id_ttl=24h
vault read -field=role_id  auth/approle/role/control-plane/role-id        > /vault-creds/role_id
vault write -f -field=secret_id auth/approle/role/control-plane/secret-id > /vault-creds/secret_id
chmod 0444 /vault-creds/role_id /vault-creds/secret_id

echo "vault-init: seeded KV (signing, service-token) + approle(control-plane) + policy + audit"
