.PHONY: db api server web test train migrate install

install:
	cd backend && uv sync
	cd frontend && npm install

db:
	docker compose up -d --wait
	docker compose exec -T db psql -U scythe -tc "select 1 from pg_database where datname='scythe_test'" | grep -q 1 || \
		docker compose exec -T db psql -U scythe -c "create database scythe_test"

migrate:
	cd backend && uv run alembic upgrade head

api: migrate
	cd backend && uv run uvicorn scythe.main:app --reload --port 8000

server:
	cd backend && ALLOWED_ORIGINS=http://localhost:5173,http://localhost:4173 uv run uvicorn --app-dir ../server main:app --reload --reload-dir ../server --port 8081

web:
	cd frontend && npm run dev

test:
	cd backend && uv run pytest -q
	cd frontend && npx tsc -b && npx eslint src

train:
	cd backend && uv run python -m scythe.train $(ARGS)
