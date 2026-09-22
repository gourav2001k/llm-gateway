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

## Testing

```bash
make test
```

Real integration check, no mocking — calls every provider currently
configured in your `.env` (Groq, Gemini, both OpenRouter modes, local Ollama)
with an actual request and confirms each one actually responds. Runs inside
the built gateway image on the compose network, so `local` can resolve the
`ollama` hostname. Needs a real `.env` and, for the local case, the model
already pulled (`make pull-model`). `make test` always rebuilds first, so it
never runs against a stale image.

## Deploying elsewhere

The whole thing is just the `Dockerfile` + `docker-compose.yml` — clone the
repo on the target box, drop in a real `.env`, and `make up`. No external
state beyond the `ollama-data` volume and whatever's in `.env`.

### Deploying via Dokploy

1. **Git provider**: connect GitHub under Dokploy's Git settings. This is a
   two-step handshake — creating the GitHub App in Dokploy is not enough, you
   must also go to the App's page on GitHub itself and click **Install App**,
   picking this repo. Skipping that step leaves the provider stuck showing
   "Action Required" with no working button to fix it from Dokploy's side.
2. **Service type**: create a **Compose** service (not "Application" — that's
   for single-Dockerfile apps). Point it at this repo/branch `main`; Dokploy
   auto-detects `./docker-compose.yml` at the repo root correctly as-is.
3. **Environment tab**: paste in real values for every var from
   `.env.example`. Dokploy writes them to a `.env` file next to the compose
   file on the server, which is exactly what `env_file: .env` on the `gateway`
   service already expects — no compose changes needed.
4. **Domains tab**: map your hostname to the `gateway` service on port `8000`
   only. Leave `ollama` unmapped — it has no `ports:` entry in
   `docker-compose.yml`, so it's already unreachable from outside the Docker
   network. Once this is public over HTTPS, `GATEWAY_API_KEY` is the only
   thing standing between the internet and your free-tier quota — use a long
   random one.
5. **Pull the local model**: after the first deploy, use Dokploy's **Open
   Terminal** button. It drops you inside a *container's own shell*
   (`docker exec` style), not the host — so pick the **ollama** container in
   the dropdown, not `gateway` (the gateway image has no Docker CLI in it,
   `docker ps` will fail there with "command not found", that's expected).
   Inside the ollama container, run the `ollama` binary directly:
   ```
   ollama pull qwen2.5-coder:7b-instruct-q4_K_M
   ```
   (or whatever `OLLAMA_MODEL` you set). Confirm after any future redeploy
   that the `ollama-data` volume survived and the model's still there.
