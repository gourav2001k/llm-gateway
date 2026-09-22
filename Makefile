.PHONY: build up down logs logs-gateway logs-ollama pull-model shell-ollama test

MODEL ?= qwen2.5-coder:7b-instruct-q4_K_M

build:
	docker compose build

up:
	docker compose up -d --build

down:
	docker compose down

# Real integration check: calls every configured provider (Groq, Gemini,
# OpenRouter-code, OpenRouter-chat, local Ollama) with a real request and
# confirms each one actually responds. Needs a real .env; run `make
# pull-model` first if the local model hasn't been pulled yet.
test: build
	docker compose run --rm \
		-v $(CURDIR)/tests:/app/tests \
		-v $(CURDIR)/pytest.ini:/app/pytest.ini \
		-v $(CURDIR)/requirements-dev.txt:/app/requirements-dev.txt \
		gateway sh -c "pip install --quiet -r requirements-dev.txt && python -m pytest tests -v"

logs:
	docker compose logs -f

logs-gateway:
	docker compose logs -f gateway

logs-ollama:
	docker compose logs -f ollama

pull-model:
	docker compose exec ollama ollama pull $(MODEL)

shell-ollama:
	docker compose exec ollama bash
