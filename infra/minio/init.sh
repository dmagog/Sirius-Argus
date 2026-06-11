#!/bin/sh
# MinIO: отдельный сервис-юзер для MLflow с политикой ТОЛЬКО на s3://mlflow (least privilege —
# MLflow больше не ходит под root-кредами MinIO). Идемпотентно, one-shot после старта MinIO.
set -e
ALIAS=local

# ждём MinIO и логинимся root'ом (root — только для bootstrap юзера/политики, не для MLflow)
i=0
until mc alias set "$ALIAS" http://minio:9000 "$MINIO_ROOT_USER" "$MINIO_ROOT_PASSWORD" >/dev/null 2>&1; do
  i=$((i + 1)); [ "$i" -ge 60 ] && { echo "minio-init: MinIO не поднялся за разумное время"; exit 1; }
  sleep 2
done
echo "minio-init: подключились к MinIO"

# бакет артефактов MLflow
mc mb --ignore-existing "$ALIAS/mlflow" >/dev/null 2>&1 || true

# политика наименьших привилегий: только s3://mlflow
cat > /tmp/mlflow-policy.json <<'EOF'
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": ["s3:*"], "Resource": ["arn:aws:s3:::mlflow", "arn:aws:s3:::mlflow/*"] }
  ]
}
EOF
mc admin policy create "$ALIAS" mlflow-only /tmp/mlflow-policy.json >/dev/null 2>&1 \
  || mc admin policy add "$ALIAS" mlflow-only /tmp/mlflow-policy.json >/dev/null 2>&1 \
  || echo "minio-init: политика mlflow-only уже есть"

# сервис-юзер MLflow
mc admin user add "$ALIAS" "$MLFLOW_S3_USER" "$MLFLOW_S3_PASSWORD" >/dev/null 2>&1 \
  || echo "minio-init: юзер $MLFLOW_S3_USER уже есть"

# привязка политики к юзеру (синтаксис attach в новых mc, set — в старых)
mc admin policy attach "$ALIAS" mlflow-only --user "$MLFLOW_S3_USER" >/dev/null 2>&1 \
  || mc admin policy set "$ALIAS" mlflow-only "user=$MLFLOW_S3_USER" >/dev/null 2>&1 \
  || echo "minio-init: политика уже привязана к $MLFLOW_S3_USER"

echo "minio-init: MLflow-юзер $MLFLOW_S3_USER с политикой mlflow-only (только s3://mlflow) готов"
