#!/bin/sh
# MLflow с basic-auth: реестр перестаёт быть «дверью только по сетевой изоляции» —
# к /api/2.0/mlflow нужен логин. Админ-юзер заводится из env (креды — из секрет-стора/Vault,
# не в репозитории). control-plane ходит под этими же кредами (MLFLOW_TRACKING_USERNAME/PASSWORD).
set -e
: "${MLFLOW_AUTH_ADMIN_USERNAME:?нужен MLFLOW_AUTH_ADMIN_USERNAME}"
: "${MLFLOW_AUTH_ADMIN_PASSWORD:?нужен MLFLOW_AUTH_ADMIN_PASSWORD}"
: "${MLFLOW_BACKEND_STORE_URI:?нужен MLFLOW_BACKEND_STORE_URI}"

CFG=/tmp/basic_auth.ini
cat > "$CFG" <<EOF
[mlflow]
default_permission = READ
database_uri = sqlite:////tmp/mlflow_basic_auth.db
admin_username = ${MLFLOW_AUTH_ADMIN_USERNAME}
admin_password = ${MLFLOW_AUTH_ADMIN_PASSWORD}
authorization_function = mlflow.server.auth:authenticate_request_basic_auth
EOF
export MLFLOW_AUTH_CONFIG_PATH="$CFG"

# --workers 1: basic-auth-приложение нестабильно с несколькими gunicorn-воркерами
# (Worker failed to boot); для реестра низкого трафика одного воркера достаточно.
exec mlflow server --host 0.0.0.0 --port 5000 \
  --backend-store-uri "$MLFLOW_BACKEND_STORE_URI" \
  --artifacts-destination s3://mlflow \
  --app-name basic-auth \
  --workers 1
