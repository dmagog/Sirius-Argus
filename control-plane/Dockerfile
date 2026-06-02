FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

# modelaudit — в ИЗОЛИРОВАННОМ venv: его protobuf>=5 несовместим с semgrep otel<5 в одном
# окружении. Вызываем CLI через subprocess (как semgrep) → оба реальных тула сосуществуют.
RUN python -m venv /opt/modelaudit-venv \
 && /opt/modelaudit-venv/bin/pip install --no-cache-dir modelaudit==0.2.45

COPY app ./app

# непривилегированный пользователь (least privilege)
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --retries=10 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
