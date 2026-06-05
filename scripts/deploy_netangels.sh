#!/usr/bin/env bash
# Развёртывание публичного демо-стенда Sirius Argus (core) на одном сервере с Docker.
# Безопасная последовательность: засев демоданных при DEV_AUTH=1 за закрытым периметром →
# перевод /api в DEV_AUTH=0 → префлайт (dev-токен должен отдавать 401) → (опц.) файрвол.
#
# Запуск на сервере из корня репозитория:
#   PUBLIC_HOST=sirius.example.ru DEMO_PASS='пароль-жюри' bash scripts/deploy_netangels.sh
#
# Переменные:
#   PUBLIC_HOST   (обяз.) домен с A-записью на этот сервер
#   DEMO_PASS     (обяз. при первом запуске) пароль HTTP Basic Auth для жюри
#   DEMO_USER     (по умолч. demo) логин Basic Auth
#   DO_FIREWALL=1 (опц.) настроить ufw 22/80/443 (иначе только печатает команды)
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$(pwd)"
ENV_FILE="$ROOT/.env.prod"
BASE=(-f docker-compose.yml -f docker-compose.prod.yml)
SEED=(-f docker-compose.seed.yml)

log(){ printf '\n== %s\n' "$*"; }
die(){ printf 'ОШИБКА: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null || die "нет docker — поставь Docker Engine + compose-plugin"
docker compose version >/dev/null 2>&1 || die "нет docker compose v2 (плагин)"
command -v python3 >/dev/null || die "нет python3 — нужен для засева (apt install -y python3)"
command -v openssl >/dev/null || die "нет openssl — нужен для генерации секретов"

# --- .env.prod: сгенерировать секреты при первом запуске ---
gen(){ openssl rand -hex 24; }
if [ ! -f "$ENV_FILE" ]; then
  log "Генерация .env.prod (секреты + bcrypt-хэш demo-пароля)"
  : "${PUBLIC_HOST:?задай PUBLIC_HOST}"
  : "${DEMO_PASS:?задай DEMO_PASS (пароль Basic Auth для жюри)}"
  DEMO_USER="${DEMO_USER:-demo}"
  HASH="$(docker run --rm caddy:2-alpine caddy hash-password --plaintext "$DEMO_PASS")"
  umask 077
  cat > "$ENV_FILE" <<EOF
PUBLIC_HOST=$PUBLIC_HOST
DEMO_USER=$DEMO_USER
DEMO_PASS_HASH='$HASH'
DEV_AUTH=0
POSTGRES_USER=sirius
POSTGRES_PASSWORD=$(gen)
KC_DB_USER=keycloak
KC_DB_PASSWORD=$(gen)
KEYCLOAK_ADMIN=admin
KEYCLOAK_ADMIN_PASSWORD=$(gen)
MINIO_USER=sirius
MINIO_PASSWORD=$(gen)
MLFLOW_DB_USER=mlflow
MLFLOW_DB_PASSWORD=$(gen)
REDIS_PASSWORD=$(gen)
CI_WEBHOOK_SECRET=$(gen)
SIGNING_SEED=$(openssl rand -hex 32)
VAULT_ROOT_TOKEN=$(gen)
SIRIUS_SERVICE_TOKEN=$(gen)
GRAFANA_OIDC_SECRET=$(gen)
GITEA_OIDC_SECRET=$(gen)
MINIO_OIDC_SECRET=$(gen)
EOF
  echo "  .env.prod создан (права 600). Доступ жюри: $DEMO_USER / $DEMO_PASS"
else
  log ".env.prod уже есть — использую его (секреты не трогаю)"
fi
set -a; . "$ENV_FILE"; set +a

cp_health(){ # $1 = массив compose-флагов через имя переменной
  docker compose "${BASE[@]}" "$@" exec -T control-plane \
    python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health',timeout=3)" 2>/dev/null
}

# --- Фаза 1: засев (DEV_AUTH=1, порты только на 127.0.0.1) ---
log "Фаза 1/3: подъём стека для засева (DEV_AUTH=1, локальные порты)"
docker compose "${BASE[@]}" "${SEED[@]}" up -d --build

log "Ожидание control-plane /health"
ok=0
for i in $(seq 1 60); do
  if docker compose "${BASE[@]}" "${SEED[@]}" exec -T control-plane \
       python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health',timeout=3)" 2>/dev/null; then
    ok=1; echo "  control-plane здоров"; break
  fi
  sleep 3
done
[ "$ok" = 1 ] || die "control-plane не поднялся за ~3 мин — смотри docker compose ${BASE[*]} ${SEED[*]} logs"

log "Засев демоданных (demo.py контейнером в docker-сети — money-shot'ы + критичная fraud-scoring в ожидании аппрува)"
# Сеем изнутри сети runtime (control-plane:8000 + serving:8000 по именам сервисов) —
# не зависим от host-порта/docker-proxy. demo.py — stdlib-only, образ python:slim.
SEED_NET="$(docker network ls --format '{{.Name}}' | grep -E '_runtime$' | head -1)"
docker run --rm --network "$SEED_NET" -v "$ROOT/scripts:/scripts:ro" \
  -e SIRIUS_BASE_URL=http://control-plane:8000 -e SERVING_URL=http://serving:8000 \
  python:3.12-slim python /scripts/demo.py \
  || echo "  (demo.py завершился с замечаниями — проверь вывод выше)"

# --- Фаза 2: запереть /api (DEV_AUTH=0), снять локальные порты ---
log "Фаза 2/3: пересоздание control-plane с DEV_AUTH=0 (стек без сид-оверрайда)"
docker compose "${BASE[@]}" up -d --build
ok=0
for i in $(seq 1 40); do
  if docker compose "${BASE[@]}" exec -T control-plane \
       python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health',timeout=3)" 2>/dev/null; then
    ok=1; break
  fi
  sleep 3
done
[ "$ok" = 1 ] || die "control-plane не поднялся после пересоздания"

# --- Фаза 3: префлайт — dev-токен на /api ОБЯЗАН вернуть 401 ---
log "Фаза 3/3: префлайт безопасности (dev-токен на /api → 401)"
CODE="$(docker compose "${BASE[@]}" exec -T control-plane python - <<'PY'
import urllib.request, urllib.error
r = urllib.request.Request("http://localhost:8000/api/findings",
                           headers={"Authorization": "Bearer dev:x:MLSecOps"})
try:
    urllib.request.urlopen(r, timeout=5); print("200")
except urllib.error.HTTPError as e: print(e.code)
except Exception: print("ERR")
PY
)"
[ "$CODE" = "401" ] || die "dev-токен вернул '$CODE' (ждали 401) — DEV_AUTH не выключен! Периметр НЕ открываю."
echo "  dev-токен → 401  /api заперт (DEV_AUTH=0)"

# --- Файрвол ---
if [ "${DO_FIREWALL:-0}" = "1" ] && command -v ufw >/dev/null; then
  log "ufw: 22/80/443 (22 разрешаем ДО enable, чтобы не отрезать SSH)"
  ufw allow 22/tcp; ufw allow 80/tcp; ufw allow 443/tcp; ufw --force enable; ufw status verbose
else
  log "Файрвол вручную (наружу нужны только 22/80/443):"
  echo "  ufw allow 22/tcp && ufw allow 80/tcp && ufw allow 443/tcp && ufw --force enable"
fi

log "ГОТОВО"
cat <<EOF
  Стенд:        https://$PUBLIC_HOST   (Basic Auth: $DEMO_USER / <твой DEMO_PASS>)
  Сертификат:   Caddy выпустит Let's Encrypt при первом обращении (нужны открытые 80/443 + A-запись).
  Демо HITL:    войти -> /map -> узел fraud-scoring (regulatory, "ожидает аппрува") -> Аппрув, approver = mlsecops
  MinIO-консоль: ssh -L 9001:127.0.0.1:9001 <user>@$PUBLIC_HOST  ->  http://localhost:9001
  Снос:         docker compose ${BASE[*]} down -v   (удалит контейнеры И тома с данными)
EOF
