SHELL := /bin/bash

.PHONY: setup dev frontend backend check

setup:
	cd frontend && npm install
	python3 -m venv backend/.venv
	backend/.venv/bin/pip install -r backend/requirements.txt

dev:
	@set -euo pipefail; \
		echo "Starting frontend: http://localhost:5173"; \
		echo "Starting backend:  http://localhost:8000"; \
		(cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000) & \
		backend_pid=$$!; \
		(cd frontend && npm run dev) & \
		frontend_pid=$$!; \
		trap 'kill $$backend_pid $$frontend_pid 2>/dev/null || true' EXIT INT TERM; \
		for attempt in $$(seq 1 40); do \
			if curl -fsS http://localhost:5173 >/dev/null 2>&1; then \
				echo "Opening problem site: http://localhost:5173"; \
				open http://localhost:5173; \
				break; \
			fi; \
			sleep 0.25; \
		done; \
		wait

frontend:
	cd frontend && npm run dev

backend:
	cd backend && .venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

check:
	cd frontend && npm run build
	cd backend && .venv/bin/python -m compileall -q app
