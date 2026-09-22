import hmac
import logging
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import PROVIDER_CHAINS, settings, resolve_chain
from app.cooldown import is_cooling_down, mark_cooldown, status as cooldown_status
from app.upstream import ProviderError, call_provider, stream_provider

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger("gateway")

app = FastAPI(title="LLM Gateway")

_QUOTA_KEYWORDS = ("quota", "per day", "per-day", "daily", "credits", "resource_exhausted", "billing")


def _classify_failure(status_code: int | None, detail: str) -> tuple[float, str] | None:
    """Returns (cooldown_seconds, reason) for a failed provider call, or None if
    the failure shouldn't trigger a cooldown at all (e.g. a permanent config error)."""
    if status_code == 429:
        if any(kw in detail.lower() for kw in _QUOTA_KEYWORDS):
            return settings.quota_cooldown_seconds, "quota_exhausted"
        return settings.rate_limit_cooldown_seconds, "rate_limited"
    if status_code is None or status_code >= 500:
        return settings.server_error_cooldown_seconds, "server_error"
    if status_code < 400:
        # 2xx but call_provider rejected the body (e.g. missing "choices") —
        # a transient upstream hiccup, not a config problem. Back off briefly.
        return settings.server_error_cooldown_seconds, "invalid_response"
    if status_code >= 400:
        # Bad key, deprecated/renamed model slug, etc. Won't fix itself on the
        # next request, so back off instead of hot-looping the same failure.
        return settings.config_error_cooldown_seconds, "config_error"
    return None


def _check_auth(authorization: str | None) -> None:
    if not settings.gateway_api_key:
        raise HTTPException(status_code=500, detail="GATEWAY_API_KEY is not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token")
    token = authorization.removeprefix("Bearer ")
    if not hmac.compare_digest(token, settings.gateway_api_key):
        raise HTTPException(status_code=401, detail="Invalid bearer token")


@app.get("/healthz")
async def healthz():
    all_providers = {p.name for chain in PROVIDER_CHAINS.values() for p in chain}
    return {
        "status": "ok",
        "modes": {mode: [p.name for p in chain] for mode, chain in PROVIDER_CHAINS.items()},
        "provider_status": {name: cooldown_status(name) for name in sorted(all_providers)},
    }


@app.get("/v1/models")
async def list_models(authorization: str | None = Header(default=None)):
    _check_auth(authorization)
    return {
        "object": "list",
        "data": [{"id": mode, "object": "model", "owned_by": "llm-gateway"} for mode in PROVIDER_CHAINS],
    }


@app.post("/v1/chat/completions")
async def chat_completions(request: Request, authorization: str | None = Header(default=None)):
    _check_auth(authorization)

    body = await request.json()
    mode, chain = resolve_chain(body.get("model"))
    if not chain:
        raise HTTPException(status_code=500, detail="No provider API keys configured")

    errors = []
    candidates = [p for p in chain if not is_cooling_down(p.name)] or chain
    streaming = bool(body.get("stream"))
    skipped = [p.name for p in chain if p not in candidates]
    if skipped:
        logger.info("mode=%s skipping providers on cooldown: %s", mode, skipped)

    for provider in candidates:
        t0 = time.monotonic()
        try:
            if streaming:
                body_iter = await stream_provider(provider, body)
                logger.info(
                    "mode=%s provider=%s stream=True result=success duration=%.2fs",
                    mode, provider.name, time.monotonic() - t0,
                )
                return StreamingResponse(body_iter, media_type="text/event-stream")
            result = await call_provider(provider, body)
            result["gateway_provider"] = provider.name
            result["gateway_mode"] = mode
            logger.info(
                "mode=%s provider=%s stream=False result=success duration=%.2fs",
                mode, provider.name, time.monotonic() - t0,
            )
            return JSONResponse(result)
        except ProviderError as e:
            duration = time.monotonic() - t0
            errors.append({"provider": e.provider, "status_code": e.status_code, "detail": e.detail})
            classification = _classify_failure(e.status_code, e.detail)
            if classification:
                cooldown_seconds, reason = classification
                mark_cooldown(e.provider, cooldown_seconds, reason)
            else:
                reason = "unclassified"
            logger.warning(
                "mode=%s provider=%s stream=%s result=failed status=%s reason=%s duration=%.2fs detail=%.200s",
                mode, provider.name, streaming, e.status_code, reason, duration, e.detail,
            )
            continue

    logger.error("mode=%s result=all_failed errors=%s", mode, errors)
    raise HTTPException(status_code=502, detail={"message": "All providers failed", "errors": errors})
