import time

_cooldowns: dict[str, float] = {}


def is_cooling_down(provider_name: str) -> bool:
    expiry = _cooldowns.get(provider_name)
    return expiry is not None and time.monotonic() < expiry


def mark_cooldown(provider_name: str, seconds: float) -> None:
    _cooldowns[provider_name] = time.monotonic() + seconds
