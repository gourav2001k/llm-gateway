import time

_cooldowns: dict[str, tuple[float, str]] = {}


def is_cooling_down(provider_name: str) -> bool:
    entry = _cooldowns.get(provider_name)
    return entry is not None and time.monotonic() < entry[0]


def mark_cooldown(provider_name: str, seconds: float, reason: str) -> None:
    _cooldowns[provider_name] = (time.monotonic() + seconds, reason)


def status(provider_name: str) -> dict:
    entry = _cooldowns.get(provider_name)
    if entry is None or time.monotonic() >= entry[0]:
        return {"cooling_down": False}
    expiry, reason = entry
    return {
        "cooling_down": True,
        "reason": reason,
        "retry_after_seconds": round(expiry - time.monotonic(), 1),
    }
