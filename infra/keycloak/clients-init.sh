#!/bin/sh
# keycloak-init — идемпотентно заводит OIDC-клиентов ops-консолей (Grafana/Gitea/MinIO)
# в realm sirius через Admin API. НЕ трогает realm-sirius.json: клиенты создаются в уже
# импортированном realm (Postgres), поэтому файл realm и этот скрипт не конфликтуют.
set -eu

KCADM=/opt/keycloak/bin/kcadm.sh
SERVER=http://keycloak:8080/auth
REALM=sirius

# ждём, пока Keycloak поднимется и админ-логин пройдёт (без healthcheck — просто ретраим).
# Бюджет щедрый: на холодном/нагруженном старте Keycloak с импортом realm поднимается
# несколько минут (наблюдали ~270с), а не десятки секунд — иначе SSO не встанет с первого up.
i=0
until $KCADM config credentials --server "$SERVER" --realm master \
        --user "$KEYCLOAK_ADMIN" --password "$KEYCLOAK_ADMIN_PASSWORD" >/dev/null 2>&1; do
  i=$((i + 1))
  [ "$i" -ge 150 ] && { echo "keycloak-init: admin-логин не прошёл (Keycloak не поднялся за разумное время)"; exit 1; }
  sleep 2
done
echo "keycloak-init: подключились к Keycloak"

_client_id() {
  $KCADM get clients -r "$REALM" -q clientId="$1" --fields id --format csv --noquotes 2>/dev/null | tr -d '\r'
}

# confidential-клиент с фикс. секретом и redirect (идемпотентно: create или update)
ensure_client() {
  cid="$1"; secret="$2"; redirect="$3"; origin="$4"
  id=$(_client_id "$cid")
  if [ -z "$id" ]; then
    $KCADM create clients -r "$REALM" \
      -s clientId="$cid" -s enabled=true -s protocol=openid-connect \
      -s publicClient=false -s standardFlowEnabled=true -s directAccessGrantsEnabled=false \
      -s secret="$secret" \
      -s "redirectUris=[\"$redirect\"]" -s "webOrigins=[\"$origin\"]" >/dev/null
    echo "keycloak-init: клиент $cid создан"
  else
    $KCADM update "clients/$id" -r "$REALM" \
      -s secret="$secret" -s "redirectUris=[\"$redirect\"]" -s "webOrigins=[\"$origin\"]" >/dev/null
    echo "keycloak-init: клиент $cid обновлён"
  fi
}

_has_mapper() {
  id=$(_client_id "$1")
  $KCADM get "clients/$id/protocol-mappers/models" -r "$REALM" --fields name --format csv --noquotes 2>/dev/null \
    | tr -d '\r' | grep -qx "$2"
}

# realm-роли → claim "roles" (для role-mapping в Grafana/Gitea)
ensure_roles_mapper() {
  cid="$1"; id=$(_client_id "$cid")
  _has_mapper "$cid" "realm roles" && return 0
  $KCADM create "clients/$id/protocol-mappers/models" -r "$REALM" \
    -s name="realm roles" -s protocol=openid-connect \
    -s protocolMapper=oidc-usermodel-realm-role-mapper \
    -s 'config."claim.name"=roles' \
    -s 'config."jsonType.label"=String' \
    -s 'config."multivalued"=true' \
    -s 'config."id.token.claim"=true' \
    -s 'config."access.token.claim"=true' \
    -s 'config."userinfo.token.claim"=true' >/dev/null
  echo "keycloak-init: $cid — добавлен маппер ролей"
}

# MinIO требует claim "policy" = имя политики MinIO. Хардкодим consoleAdmin (демо-доступ оператора).
ensure_minio_policy_mapper() {
  cid="$1"; id=$(_client_id "$cid")
  _has_mapper "$cid" "minio policy" && return 0
  $KCADM create "clients/$id/protocol-mappers/models" -r "$REALM" \
    -s name="minio policy" -s protocol=openid-connect \
    -s protocolMapper=oidc-hardcoded-claim-mapper \
    -s 'config."claim.name"=policy' \
    -s 'config."claim.value"=consoleAdmin' \
    -s 'config."jsonType.label"=String' \
    -s 'config."id.token.claim"=true' \
    -s 'config."access.token.claim"=true' \
    -s 'config."userinfo.token.claim"=true' >/dev/null
  echo "keycloak-init: $cid — добавлен policy-claim (consoleAdmin)"
}

ensure_client grafana "$GRAFANA_OIDC_SECRET" "http://localhost:3000/login/generic_oauth" "http://localhost:3000"
ensure_roles_mapper grafana

ensure_client gitea "$GITEA_OIDC_SECRET" "http://localhost:3001/user/oauth2/keycloak/callback" "http://localhost:3001"
ensure_roles_mapper gitea

ensure_client minio "$MINIO_OIDC_SECRET" "http://localhost:9001/oauth_callback" "http://localhost:9001"
ensure_minio_policy_mapper minio

echo "keycloak-init: OIDC-клиенты готовы (grafana, gitea, minio)"
