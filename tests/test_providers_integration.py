"""Real integration check: hits every configured provider with an actual
request over the network and confirms it actually responds. No mocking —
the point is to catch a specific model going stale/rate-limited/misconfigured,
not just confirm the fallback chain has *some* working provider.

Run with `make test` (needs the compose network so `local` can resolve the
`ollama` hostname, and needs a real .env with whichever keys you want tested).
"""

import pytest

from app.config import PROVIDER_CHAINS
from app.upstream import ProviderError, call_provider

PROMPT = {"messages": [{"role": "user", "content": "Reply with exactly one word: pong"}]}


def _test_cases():
    """One case per distinct (provider, model) pair actually in use — so
    OpenRouter's separate code/chat free models both get exercised instead of
    being deduped away."""
    seen = set()
    cases = []
    for mode, chain in PROVIDER_CHAINS.items():
        for provider in chain:
            key = (provider.name, provider.model)
            if key in seen:
                continue
            seen.add(key)
            cases.append((mode, provider))
    return cases


_CASES = _test_cases()
_IDS = [f"{mode}:{provider.name}:{provider.model}" for mode, provider in _CASES]


def test_at_least_one_provider_is_configured():
    assert _CASES, "No providers configured at all — check .env (or docker-compose env_file wiring)"


@pytest.mark.parametrize("mode,provider", _CASES, ids=_IDS)
async def test_provider_actually_responds(mode, provider):
    if provider.name != "local" and not provider.api_key:
        pytest.skip(f"{provider.name}: no API key set in .env")

    try:
        result = await call_provider(provider, dict(PROMPT))
    except ProviderError as e:
        pytest.fail(
            f"{provider.name} ({provider.model}) failed: status={e.status_code} detail={e.detail[:300]}"
        )

    content = result["choices"][0]["message"]["content"].strip()
    assert content, f"{provider.name} ({provider.model}) returned empty content"
    print(f"\n{mode}:{provider.name} ({provider.model}) -> {content!r}")
