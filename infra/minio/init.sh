#!/bin/sh
# MinIO least privilege: отдельные сервис-юзеры с политикой на ОДИН бакет —
#   mlflow-svc → s3://mlflow (артефакты MLflow)
#   cp-svc     → s3://sirius-quarantine (карантин-стор control-plane, AUD-11)
# Ни тот, ни другой не ходят под root MinIO. Идемпотентно, one-shot после старта MinIO.
set -e
ALIAS=local

# ждём MinIO и логинимся root'ом (root — только для bootstrap юзеров/политик)
i=0
until mc alias set "$ALIAS" http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -ge 60 ] && { echo "minio-init: MinIO не поднялся за разумное время"; exit 1; }
  sleep 2
done
echo "minio-init: подключились к MinIO"

# ensure_scoped_user <policy> <bucket> <user> <password>: бакет + политика только на него + юзер
ensure_scoped_user() {
  pol="$1"; bucket="$2"; usr="$3"; pwd="$4"
  mc mb --ignore-existing "$ALIAS/$bucket" >/dev/null 2>&1 || true
  cat > "/tmp/$pol.json" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:*"], "Resource": ["arn:aws:s3:::${bucket}", "arn:aws:s3:::${bucket}/*"] }
  ]
}
EOF
  mc admin policy create "$ALIAS" "$pol" "/tmp/$pol.json" >/dev/null 2>&1 \
    || mc admin policy add "$ALIAS" "$pol" "/tmp/$pol.json" >/dev/null 2>&1 \
    || echo "minio-init: политика $pol уже есть"
  mc admin user add "$ALIAS" "$usr" "$pwd" >/dev/null 2>&1 \
    || echo "minio-init: юзер $usr уже есть"
  mc admin policy attach "$ALIAS" "$pol" --user "$usr" >/dev/null 2>&1 \
    || mc admin policy set "$ALIAS" "$pol" "user=$usr" >/dev/null 2>&1 \
    || echo "minio-init: политика $pol уже привязана к $usr"
  echo "minio-init: юзер $usr → политика $pol (только s3://$bucket)"
}

ensure_scoped_user mlflow-only mlflow "$MLFLOW_S3_USER" "$MLFLOW_S3_PASSWORD"
ensure_scoped_user cp-only "${ARTIFACT_BUCKET:-sirius-quarantine}" "$CP_S3_USER" "$CP_S3_PASSWORD"

echo "minio-init: scoped-юзера готовы (mlflow-svc, cp-svc)"
