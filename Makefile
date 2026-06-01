.PHONY: up up-full down config test logs ps

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

logs:      ## логи control-plane
	docker compose logs -f control-plane

ps:
	docker compose ps
