# llm-gateway

A small self-hosted, OpenAI-compatible `/v1/chat/completions` gateway that fans
requests out across free-tier LLM providers before falling back to a local
Ollama model. Point any OpenAI-compatible client (VS Code agent, CLI tool,
script) at it instead of a single provider, and it absorbs rate limits/outages
for you.

## How it works

Each request tries providers **in order** until one succeeds:

```
Groq → Gemini → OpenRouter → local Ollama (last resort)
```

- A provider is only tried if it has an API key configured.
- If a provider fails, the gateway marks it "cooling down" for a while and
  moves to the next one. Cooldown length depends on *why* it failed:
  - `429` with quota/billing wording (daily cap hit) → long cooldown
    (`QUOTA_COOLDOWN_SECONDS`, default 1h)
  - `429` otherwise (plain rate limit) → short cooldown
    (`RATE_LIMIT_COOLDOWN_SECONDS`, default 60s)
  - `5xx` / connection error → `SERVER_ERROR_COOLDOWN_SECONDS` (default 15s)
  - Any other `4xx` (bad key, renamed/removed model slug, etc.) →
    `CONFIG_ERROR_COOLDOWN_SECONDS` (default 5m) — these don't fix themselves
    on retry, so we back off instead of hammering it every request.
  - If every provider is cooling down, the gateway retries the full chain
    anyway rather than failing outright.
- Both streaming (`"stream": true`, SSE) and non-streaming requests are
  supported.

### Modes

The `model` field in your request selects a **mode**, not a literal model
name — the gateway maps it to a whole provider chain:

- `gateway-code` — OpenRouter's free slot uses `OPENROUTER_MODEL_CODE`
- `gateway-chat` — OpenRouter's free slot uses `OPENROUTER_MODEL_CHAT`

Groq/Gemini use the same model for both modes; only OpenRouter's free model
roster is split by use case. Any unrecognized `model` value falls back to
`gateway-code`. `GET /v1/models` (auth required) lists the available modes.

## Setup

```bash
cp .env.example .env
```

Fill in `.env`:

| Var | Required | Notes |
|---|---|---|
| `GATEWAY_API_KEY` | yes | Bearer token clients must send. Generate with `openssl rand -hex 32`. |
| `GROQ_API_KEY` / `GROQ_MODEL` | optional | Free tier at groq.com |
| `GEMINI_API_KEY` / `GEMINI_MODEL` | optional | Free tier via Gemini's OpenAI-compatible endpoint |
| `OPENROUTER_API_KEY` / `OPENROUTER_MODEL_CODE` / `OPENROUTER_MODEL_CHAT` | optional | OpenRouter's free (`:free`) model slugs change often — check [openrouter.ai/models](https://openrouter.ai/models) if requests start failing |
| `ENABLE_LOCAL_FALLBACK` / `OLLAMA_MODEL` | no (defaults on) | Last-resort local model via Ollama |

At least one remote provider key (or local fallback) must be set, or every
request will 500 with "No provider API keys configured".

## Running

```bash
make up             # docker compose up -d --build
make logs-gateway   # tail gateway logs
make pull-model     # pull the configured Ollama model (first run only)
make down
```

The gateway listens on `localhost:8000`. Ollama data persists in a named
Docker volume across restarts.

## API

All endpoints except `/healthz` require `Authorization: Bearer <GATEWAY_API_KEY>`.

- `GET /healthz` — status + which providers are configured/cooling down per mode. No auth, don't put secrets in it.
- `GET /v1/models` — lists the two modes as if they were models.
- `POST /v1/chat/completions` — standard OpenAI chat completions body. Set
  `"model": "gateway-code"` or `"gateway-chat"`; `"stream": true` for SSE.

```bash
curl -s http://localhost:8000/v1/chat/completions \
  -H "Authorization: Bearer $GATEWAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gateway-chat","messages":[{"role":"user","content":"hi"}]}'
```

## Deploying elsewhere

The whole thing is just the `Dockerfile` + `docker-compose.yml` — clone the
repo on the target box, drop in a real `.env`, and `make up`. No external
state beyond the `ollama-data` volume and whatever's in `.env`.
