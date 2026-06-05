.PHONY: install backend-install frontend-install backend-dev backend-dev-reload frontend-dev backend-test frontend-build db-up db-down docker-up docker-down integration-up integration-test integration-down

export UV_CACHE_DIR := $(CURDIR)/.uv-cache
DB_COMPOSE := docker compose -p g26-q-db -f dev/db/docker-compose.yml

install: backend-install frontend-install

backend-install:
	cd src/backend && uv sync --extra test

frontend-install:
	cd src/frontend && npm ci

backend-dev:
	cd src/backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000

backend-dev-reload:
	cd src/backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

frontend-dev:
	cd src/frontend && npm run dev -- --host 127.0.0.1 --port 5173

backend-test:
	cd src/backend && uv run pytest

frontend-build:
	cd src/frontend && npm run build

db-up:
	$(DB_COMPOSE) up -d
	@port=$$(bash scripts/compose-port.sh -p g26-q-db -f dev/db/docker-compose.yml -- db 5432); \
	echo "PostgreSQL: 127.0.0.1:$$port"

db-down:
	$(DB_COMPOSE) down

docker-up:
	docker compose up --build -d
	@echo "Backend: http://127.0.0.1:$${BACKEND_PUBLISH_PORT:-34167}"

docker-down:
	docker compose down

integration-up:
	bash scripts/integration/dev-up.sh

integration-test:
	python3 -m pip install -q -r scripts/integration/requirements.txt
	set -a && . dev/integration/.env.integration && set +a && \
	cd scripts/integration && python3 two_team_rls_test.py

integration-down:
	bash scripts/integration/dev-down.sh
