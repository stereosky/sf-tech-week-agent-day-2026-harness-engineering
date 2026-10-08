COMPOSE := docker compose
STEP ?= 5
LOGIN_URL := http://localhost:$(or $(shell sed -n 's/^HARNESS_PORT=//p' .env 2>/dev/null),8080)/login

.PHONY: help up login down doctor test catchup reset logs events check

help:
	@echo "make up                start the whole stack"
	@echo "make login             log the harness into Lenses (once)"
	@echo "make doctor            check every service from inside the harness"
	@echo "make test STEP=3       run the tests for steps 1 to 3"
	@echo "make catchup STEP=3    copy the solutions for steps 1 to 3 into harness/src"
	@echo "make logs              follow the harness trace"
	@echo "make events            print the session log from Kafka"
	@echo "make reset             delete both topics and seed them again"
	@echo "make down              stop everything and delete its data"

up:
	@grep -qs '^ACCEPT_EULA=true' .env || (echo "Copy .env.example to .env and set ACCEPT_EULA=true first." && exit 1)
	$(COMPOSE) up -d --wait
	@printf '\nNext: make login, then make doctor\n'

login:
	@echo "Open $(LOGIN_URL), sign into Lenses as admin / admin and click Authorise."
	@open "$(LOGIN_URL)" 2>/dev/null || xdg-open "$(LOGIN_URL)" 2>/dev/null || true

down:
	$(COMPOSE) down -v

doctor:
	$(COMPOSE) exec harness python -m harness.doctor

test:
	$(COMPOSE) exec harness sh -c "pytest -q $(foreach i,$(shell seq 1 $(STEP)),tests/test_$(i)_*.py)"

catchup:
	@[ "$(origin STEP)" = "command line" ] || (echo "usage: make catchup STEP=3" && exit 1)
	@for i in $$(seq 1 $(STEP)); do cp solutions/step$$i/*.py harness/src/harness/ && echo "copied solutions/step$$i"; done

logs:
	$(COMPOSE) logs -f --no-log-prefix harness

events:
	@$(COMPOSE) exec demo-kafka kafka-console-consumer --bootstrap-server demo-kafka:19092 \
		--topic agent.session --from-beginning --property print.key=true --timeout-ms 3000 2>&1 \
		| grep -vE "TimeoutException|Error processing message|^\s+at " || true

reset:
	$(COMPOSE) exec harness python -m harness.seed --reset

# For maintainers: every solution applied to a copy of the starter, then tests and lint.
check:
	@rm -rf /tmp/agent-harness-check && mkdir -p /tmp/agent-harness-check
	@rsync -a --exclude .venv harness /tmp/agent-harness-check/
	@for i in 1 2 3 4 5; do cp solutions/step$$i/*.py /tmp/agent-harness-check/harness/src/harness/; done
	cd /tmp/agent-harness-check/harness && uv run --frozen pytest -q && uv run --frozen ruff check src tests
