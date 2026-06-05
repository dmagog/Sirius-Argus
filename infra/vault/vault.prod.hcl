# Vault production config — DRAFT. Raft-storage + TLS-листенер + auto-unseal.
# Заменяет dev-режим (`server -dev`). После старта нужен `vault operator init` + unseal.

storage "raft" {
  path    = "/vault/data"
  node_id = "sirius-vault-1"
}

listener "tcp" {
  address       = "0.0.0.0:8200"
  tls_cert_file = "/vault/tls/tls.crt"   # TODO: смонтировать серт/ключ (том infra/vault/tls)
  tls_key_file  = "/vault/tls/tls.key"
}

# Auto-unseal через облачный KMS — раскомментировать и заполнить под провайдера,
# иначе unseal вручную ключами Шамира после `vault operator init`.
# seal "awskms" {
#   region     = "..."
#   kms_key_id = "..."
# }

api_addr     = "https://127.0.0.1:8200"
cluster_addr = "https://127.0.0.1:8201"
ui           = false
