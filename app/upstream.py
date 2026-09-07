import httpx

from app.config import Provider, settings


class ProviderError(Exception):
    def __init__(self, provider: str, status_code: int | None, detail: str):
        self.provider = provider
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"{provider}: {detail}")


async def call_provider(provider: Provider, body: dict) -> dict:
    payload = {**body, "model": provider.model}
    async with httpx.AsyncClient(timeout=settings.request_timeout_seconds) as client:
        try:
            resp = await client.post(
                f"{provider.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {provider.api_key}"},
                json=payload,
            )
        except httpx.RequestError as e:
            raise ProviderError(provider.name, None, str(e)) from e

    if resp.status_code >= 400:
        raise ProviderError(provider.name, resp.status_code, resp.text)

    return resp.json()
