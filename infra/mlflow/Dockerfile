# MLflow с предустановленными драйверами: psycopg2 (backend-store Postgres) и
# boto3 (артефакты в MinIO/S3). Рантайм идёт в сети internal:true без egress,
# поэтому зависимости ставим на сборке — у хоста сеть есть, у контейнера нет.
FROM ghcr.io/mlflow/mlflow:v2.18.0
RUN pip install --no-cache-dir psycopg2-binary boto3
