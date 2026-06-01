.PHONY: up up-full down config test demo pipeline logs ps

up:        ## core: поднять MVP-стек
	docker compose up -d --build

up-full:   ## core + observability (Loki/Grafana/Prometheus) + Gitea
	docker compose --profile full up -d --build

down:      ## остановить и убрать контейнеры
	docker compose down

config:    ## валидация compose-конфига
	docker compose config -q && echo "compose: OK"

test:      ## pytest-bdd против поднятого стека
	cd tests && python -m pytest -q

demo:      ## живой прогон money-shot'ов по поднятому стеку
	python3 scripts/demo.py

pipeline:  ## сквозной конвейер ЖЦ одной модели (приём→gate→HITL→деплой→атака→decommission)
	python3 scripts/pipeline.py

logs:      ## логи control-plane
	docker compose logs -f control-plane

ps:
	docker compose ps
