from collections.abc import AsyncIterator

import httpx

from app.config import Provider


class ProviderError(Exception):
    def __init__(self, provider: str, status_code: int | None, detail: str):
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{provider}: {detail}")


async def call_provider(provider: Provider, body: dict) -> dict:
    payload = {**body, "model": provider.model, "stream": False}
    headers = {"Authorization": f"Bearer {provider.api_key}"} if provider.api_key else {}
    async with httpx.AsyncClient(timeout=provider.timeout) as client:
        try:
            resp = await client.post(
                f"{provider.base_url}/chat/completions",
                headers=headers,
                json=payload,
            )
        except httpx.RequestError as e:
            raise ProviderError(provider.name, None, str(e) or type(e).__name__) from e

    if resp.status_code >= 400:
        raise ProviderError(provider.name, resp.status_code, resp.text)

    data = resp.json()
    if "choices" not in data:
        # Some providers (e.g. OpenRouter's free-tier router) occasionally
        # return 200 OK with a malformed/error body instead of an HTTP error.
        # Treat it as a failure so the fallback chain still kicks in.
        raise ProviderError(provider.name, resp.status_code, resp.text)

    return data


async def stream_provider(provider: Provider, body: dict) -> AsyncIterator[bytes]:
    """Raises ProviderError before yielding anything if the upstream call fails,
    so the caller's fallback chain can still try the next provider cleanly."""
    payload = {**body, "model": provider.model, "stream": True}
    headers = {"Authorization": f"Bearer {provider.api_key}"} if provider.api_key else {}
    client = httpx.AsyncClient(timeout=provider.timeout)
    try:
        req = client.build_request(
            "POST", f"{provider.base_url}/chat/completions", headers=headers, json=payload
        )
        resp = await client.send(req, stream=True)
    except httpx.RequestError as e:
        await client.aclose()
        raise ProviderError(provider.name, None, str(e) or type(e).__name__) from e

    if resp.status_code >= 400:
        detail = (await resp.aread()).decode(errors="replace")
        await resp.aclose()
        await client.aclose()
        raise ProviderError(provider.name, resp.status_code, detail)

    async def body_iter() -> AsyncIterator[bytes]:
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await client.aclose()

    return body_iter()
