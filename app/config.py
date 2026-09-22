from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(BaseSettings):
    name: str
    base_url: str
    api_key: str = ""
    model: str
    timeout: float


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    gateway_api_key: str = ""

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.5-flash"

    openrouter_api_key: str = ""
    openrouter_model_code: str = "qwen/qwen3-coder:free"
    openrouter_model_chat: str = "meta-llama/llama-3.3-70b-instruct:free"

    enable_local_fallback: bool = True
    ollama_base_url: str = "http://ollama:11434/v1"
    ollama_model: str = "qwen2.5-coder:7b-instruct-q4_K_M"

    request_timeout_seconds: float = 30.0
    local_request_timeout_seconds: float = 90.0

    rate_limit_cooldown_seconds: float = 60.0
    quota_cooldown_seconds: float = 3600.0
    server_error_cooldown_seconds: float = 15.0
    config_error_cooldown_seconds: float = 300.0


settings = Settings()

_local_provider = (
    Provider(
        name="local",
        base_url=settings.ollama_base_url,
        model=settings.ollama_model,
        timeout=settings.local_request_timeout_seconds,
    )
    if settings.enable_local_fallback
    else None
)


def _build_chain(openrouter_model: str) -> list[Provider]:
    candidates = [
        Provider(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            timeout=settings.request_timeout_seconds,
        ),
        Provider(
            name="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout=settings.request_timeout_seconds,
        ),
        Provider(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key=settings.openrouter_api_key,
            model=openrouter_model,
            timeout=settings.request_timeout_seconds,
        ),
    ]
    chain = [p for p in candidates if p.api_key]
    if _local_provider:
        chain.append(_local_provider)
    return chain


DEFAULT_MODE = "gateway-code"

PROVIDER_CHAINS: dict[str, list[Provider]] = {
    "gateway-code": _build_chain(settings.openrouter_model_code),
    "gateway-chat": _build_chain(settings.openrouter_model_chat),
}


def resolve_chain(requested_model: str | None) -> tuple[str, list[Provider]]:
    mode = requested_model if requested_model in PROVIDER_CHAINS else DEFAULT_MODE
    return mode, PROVIDER_CHAINS[mode]
