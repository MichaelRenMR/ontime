.PHONY: up down logs migrate revision test lint seed poll psql

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=100

migrate:
	cd backend && uv run alembic upgrade head

revision:
	cd backend && uv run alembic revision --autogenerate -m "$(m)"

test:
	cd backend && uv run pytest

lint:
	cd backend && uv run ruff check . && uv run pyright

seed:
	cd backend && uv run ontime-ingest seed

poll:
	cd backend && uv run ontime-ingest poll --tier $(tier)

psql:
	docker compose exec db psql -U ontime ontime
