.PHONY: up up-full up-test dev down config test demo pipeline selfscan logs ps

up:        ## core: поднять MVP-стек (лимит загрузки 2 ГиБ — реальные модели проходят)
	docker compose up -d --build

up-full:   ## core + observability (Loki/Grafana/Prometheus) + Gitea
	docker compose --profile full up -d --build

up-test:   ## тест-стек: как core, но малый лимит загрузки (25 МиБ) для сценария DOS-02
	docker compose -f docker-compose.yml -f docker-compose.test.yml up -d --build

dev:       ## hot-reload control-plane (правки .py без пересборки; НЕ для прод/демо)
	docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

down:      ## остановить и убрать контейнеры
	docker compose down

config:    ## валидация compose-конфига
	docker compose config -q && echo "compose: OK"

test:      ## pytest-bdd против поднятого стека (для полного набора с DOS-02: сначала `make up-test`)
	cd tests && python -m pytest -q

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
