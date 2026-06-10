# MLflow с предустановленными драйверами: psycopg2 (backend-store Postgres) и
# boto3 (артефакты в MinIO/S3). Рантайм идёт в сети internal:true без egress,
# поэтому зависимости ставим на сборке — у хоста сеть есть, у контейнера нет.
FROM ghcr.io/mlflow/mlflow:v2.18.0
# AUD-25: psycopg2-binary пинуем; boto3 оставляем беспиновым — жёсткий пин boto3 ломает
# резолв botocore в окружении образа mlflow (boto3==1.35.99 → botocore «from versions: none»).
# Для воспроизводимого пина boto3/botocore — отдельный constraints-файл (pip-tools), не inline.
RUN pip install --no-cache-dir --retries 5 --timeout 120 psycopg2-binary==2.9.10 boto3

# basic-auth: реестр под аутентификацией (mlflow server --app-name basic-auth), креды из env
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
