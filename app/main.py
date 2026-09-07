from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

from app.config import PROVIDER_CHAIN
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

    for provider in PROVIDER_CHAIN:
        try:
            result = await call_provider(provider, body)
            result["gateway_provider"] = provider.name
            return JSONResponse(result)
        except ProviderError as e:
            errors.append({"provider": e.provider, "status_code": e.status_code, "detail": e.detail})
            continue

    raise HTTPException(status_code=502, detail={"message": "All providers failed", "errors": errors})
