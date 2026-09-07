from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import PROVIDER_CHAIN, settings
from app.cooldown import is_cooling_down, mark_cooldown
from app.upstream import ProviderError, call_provider

app = FastAPI(title="LLM Gateway")


@app.get("/healthz")
async def healthz():
    return {"status": "ok", "providers": [p.name for p in PROVIDER_CHAIN]}


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    if not PROVIDER_CHAIN:
        raise HTTPException(status_code=500, detail="No provider API keys configured")

    body = await request.json()
    errors = []

    candidates = [p for p in PROVIDER_CHAIN if not is_cooling_down(p.name)] or PROVIDER_CHAIN

    for provider in candidates:
        try:
            result = await call_provider(provider, body)
            result["gateway_provider"] = provider.name
            return JSONResponse(result)
        except ProviderError as e:
            errors.append({"provider": e.provider, "status_code": e.status_code, "detail": e.detail})
            if e.status_code == 429:
                mark_cooldown(e.provider, settings.rate_limit_cooldown_seconds)
            elif e.status_code is None or e.status_code >= 500:
                mark_cooldown(e.provider, settings.server_error_cooldown_seconds)
            continue

    raise HTTPException(status_code=502, detail={"message": "All providers failed", "errors": errors})
