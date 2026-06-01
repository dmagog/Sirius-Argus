# Сервинг трио НЕ-генеративных моделей (sklearn, CPU-only). Зависимости запекаем
# на сборке (рантайм идёт во внутренней сети). Наружу — единственный кроме
# reverse-proxy внешний контур (И4): здесь живут рантайм-защиты.
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
RUN useradd -m appuser
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=5s --retries=18 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
