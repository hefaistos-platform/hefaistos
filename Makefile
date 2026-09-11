COMPOSE ?= docker compose

.PHONY: up up-workers up-obs up-devtools up-full down ps logs migrate seed

up:
	$(COMPOSE) up -d

up-workers:
	$(COMPOSE) --profile workers up -d

up-obs:
	$(COMPOSE) --profile obs up -d

up-devtools:
	$(COMPOSE) --profile devtools up -d

up-full:
	$(COMPOSE) --profile workers --profile obs --profile devtools up -d

down:
	$(COMPOSE) down --remove-orphans

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f

migrate:
	$(COMPOSE) --profile batch run --rm migrate

seed:
	$(COMPOSE) --profile batch run --rm seed
