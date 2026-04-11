from __future__ import annotations


class ControlStatusCacheService:
    """Own control-status cache invalidation and cached payload retrieval."""

    @staticmethod
    def invalidate(cache: dict, *, lock) -> None:
        with lock:
            cache["computed_at"] = 0.0
            cache["payload"] = None

    @staticmethod
    def cached_payload(cache: dict, *, lock, max_age_seconds: float, monotonic_fn, compute_payload_fn) -> dict:
        now = monotonic_fn()
        cached_payload = cache.get("payload")
        cached_at = float(cache.get("computed_at") or 0.0)
        if isinstance(cached_payload, dict) and now - cached_at <= float(max_age_seconds):
            return dict(cached_payload)

        with lock:
            now = monotonic_fn()
            cached_payload = cache.get("payload")
            cached_at = float(cache.get("computed_at") or 0.0)
            if isinstance(cached_payload, dict) and now - cached_at <= float(max_age_seconds):
                return dict(cached_payload)

            payload = compute_payload_fn()
            cache["computed_at"] = monotonic_fn()
            cache["payload"] = dict(payload)
            return payload


CONTROL_STATUS_CACHE_SERVICE = ControlStatusCacheService()