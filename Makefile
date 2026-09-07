.PHONY: up down logs logs-gateway logs-ollama pull-model shell-ollama

MODEL ?= qwen2.5:7b

up:
	docker compose up -d --build

down:
	docker compose down

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
