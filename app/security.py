"""Security helpers for input validation, CSRF checks and rate limiting."""

from __future__ import annotations

import re
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import Request

from app.translations import SUPPORTED_CURRENCIES, SUPPORTED_LANGS


_SAFE_SLUG_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
_SAFE_SKU_RE = re.compile(r"^[A-Za-z0-9 ._\-/]{1,120}$")


def normalize_lang(value: str | None, default: str = "en") -> str:
    if not value:
        return default
    value = value.strip().lower()
    return value if value in SUPPORTED_LANGS else default


def normalize_currency(value: str | None, default: str = "eur") -> str:
    if not value:
        return default
    value = value.strip().lower()
    return value if value in SUPPORTED_CURRENCIES else default


def is_safe_category_slug(value: str | None) -> bool:
    if not value:
        return False
    return bool(_SAFE_SLUG_RE.fullmatch(value.strip().lower()))


def is_safe_sku(value: str | None) -> bool:
    if not value:
        return False
    return bool(_SAFE_SKU_RE.fullmatch(value.strip()))


def safe_redirect_target(request: Request, fallback: str = "/", value: str | None = None) -> str:
    """Allow only local redirect paths to avoid open redirects and header abuse."""
    candidate = (value or "").strip()
    if not candidate:
        candidate = request.headers.get("referer", "").strip()

    if candidate.startswith("/") and not candidate.startswith("//"):
        return candidate

    if candidate:
        parsed = urlparse(candidate)
        if parsed.scheme in ("http", "https") and parsed.netloc == request.url.netloc:
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            return path

    return fallback


def is_same_origin_request(request: Request) -> bool:
    """Browser-oriented CSRF check for unsafe methods."""
    origin = request.headers.get("origin", "").strip()
    referer = request.headers.get("referer", "").strip()
    host = request.url.netloc

    if origin:
        parsed_origin = urlparse(origin)
        if parsed_origin.scheme in ("http", "https"):
            return parsed_origin.netloc == host

    if referer:
        parsed_referer = urlparse(referer)
        if parsed_referer.scheme in ("http", "https"):
            return parsed_referer.netloc == host

    sec_fetch_site = request.headers.get("sec-fetch-site", "").strip().lower()
    # Treat missing header as acceptable for non-browser clients.
    return sec_fetch_site in ("", "same-origin", "same-site", "none")


class InMemoryRateLimiter:
    """Simple process-local sliding window limiter."""

    def __init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        now = time.time()
        threshold = now - window_seconds
        with self._lock:
            dq = self._events[key]
            while dq and dq[0] < threshold:
                dq.popleft()
            if len(dq) >= limit:
                return False
            dq.append(now)
            return True


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"
