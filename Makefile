.PHONY: up down logs restart be fe deps test

up:
	docker compose up --build -d

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

restart:
	docker compose restart backend frontend

be:
	cd backend && uvicorn app.main:app --reload --port 8000

fe:
	cd frontend && npm run dev

deps:
	cd backend && pip install -r requirements.txt
	cd frontend && npm install

test:
	cd backend && python -m compileall -q app
