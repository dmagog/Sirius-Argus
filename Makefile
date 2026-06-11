.PHONY: secrets up up-full up-test dev down config test demo pipeline selfscan logs ps

secrets:   ## сгенерировать .env со случайными секретами (нужно один раз перед up; .env не коммитится)
	python3 scripts/gen_env.py

up:        ## core: поднять MVP-стек (сначала `make secrets`; лимит загрузки 2 ГиБ)
	@test -f .env || { echo "нет .env — выполни `make secrets`"; exit 1; }
	docker compose up -d --build

up-full:   ## core + observability (Loki/Grafana/Prometheus) + Gitea
	docker compose --profile full up -d --build

up-test:   ## тест-стек: как core, но малый лимит загрузки (25 МиБ) для сценария DOS-02
	docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build

up-prod:   ## БОЕВОЙ путь: production.yml (oauth2-proxy + Vault prod). Нужны .env.production, TLS-серт Vault, unseal — см. docs/runbooks/deploy-production.md
	docker compose -f docker-compose.yml -f docker-compose.production.yml --profile full up -d --build

dev:       ## hot-reload control-plane (правки .py без пересборки; НЕ для прод/демо)
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

down:      ## остановить и убрать контейнеры
	docker compose down

config:    ## валидация compose-конфига
	docker compose config -q && echo "compose: OK"

test:      ## pytest-bdd против поднятого стека (сначала `make secrets && make up-test`)
	@test -f .env || { echo "нет .env — выполни `make secrets`"; exit 1; }
	set -a; . ./.env; set +a; cd tests && python3 -m pytest -q   # .env → тесты, читающие SIRIUS_SERVICE_TOKEN/VAULT_ROOT_TOKEN

demo:      ## живой прогон money-shot'ов по поднятому стеку
	python3 scripts/demo.py

pipeline:  ## сквозной конвейер ЖЦ одной модели (приём→gate→аппрув-гейт→деплой→атака→decommission)
	python3 scripts/pipeline.py

selfscan:  ## догфудинг SAST: bandit по НАШЕМУ коду (control-plane + serving), порог medium+
	docker run --rm -v "$(PWD)":/src python:3.12-slim \
	  sh -c "pip install -q bandit && bandit -r -ll /src/control-plane/app /src/serving/app"

logs:      ## логи control-plane
	docker compose logs -f control-plane

ps:
	docker compose ps
