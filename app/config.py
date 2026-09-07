from pydantic_settings import BaseSettings, SettingsConfigDict


class Provider(BaseSettings):
    name: str
    base_url: str
    api_key: str = ""
    model: str


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"

    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash"

    cerebras_api_key: str = ""
    cerebras_model: str = "llama-3.3-70b"

    enable_local_fallback: bool = True
    ollama_base_url: str = "http://ollama:11434/v1"
    ollama_model: str = "qwen2.5:3b"

    request_timeout_seconds: float = 30.0
    rate_limit_cooldown_seconds: float = 60.0
    server_error_cooldown_seconds: float = 15.0


settings = Settings()

_remote_providers = [
    p
    for p in [
        Provider(
            name="groq",
            base_url="https://api.groq.com/openai/v1",
            api_key=settings.groq_api_key,
            model=settings.groq_model,
        ),
        Provider(
            name="gemini",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
        ),
        Provider(
            name="cerebras",
            base_url="https://api.cerebras.ai/v1",
            api_key=settings.cerebras_api_key,
            model=settings.cerebras_model,
        ),
    ]
    if p.api_key
]

PROVIDER_CHAIN: list[Provider] = _remote_providers + (
    [
        Provider(
            name="local",
            base_url=settings.ollama_base_url,
            model=settings.ollama_model,
        )
    ]
    if settings.enable_local_fallback
    else []
)
