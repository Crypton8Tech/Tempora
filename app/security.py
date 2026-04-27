"""Утилиты безопасности: валидация входных данных, CSRF и rate limiting."""

from __future__ import annotations

import re
import secrets
import threading
import time
from collections import defaultdict, deque
from hmac import compare_digest
from urllib.parse import parse_qs
from urllib.parse import urlparse

from fastapi import Request

from app.translations import SUPPORTED_CURRENCIES, SUPPORTED_LANGS


_SAFE_SLUG_RE = re.compile(r"^[a-z0-9_-]{1,64}$")
_SAFE_SKU_RE = re.compile(r"^[A-Za-z0-9 ._\-/]{1,120}$")


def normalize_lang(value: str | None, default: str = "en") -> str:
    # Принимаем только известные коды языка, иначе используем безопасный дефолт.
    if not value:
        return default
    value = value.strip().lower()
    return value if value in SUPPORTED_LANGS else default


def normalize_currency(value: str | None, default: str = "eur") -> str:
    # Принимаем только поддерживаемые валюты, иначе безопасный дефолт.
    if not value:
        return default
    value = value.strip().lower()
    return value if value in SUPPORTED_CURRENCIES else default


def is_safe_category_slug(value: str | None) -> bool:
    # Проверка по белому списку блокирует инъекционные payload-ы в фильтре категории.
    if not value:
        return False
    return bool(_SAFE_SLUG_RE.fullmatch(value.strip().lower()))


def is_safe_sku(value: str | None) -> bool:
    # SKU приходит из URL пользователя, поэтому набор разрешённых символов строгий.
    if not value:
        return False
    return bool(_SAFE_SKU_RE.fullmatch(value.strip()))


def safe_redirect_target(request: Request, fallback: str = "/", value: str | None = None) -> str:
    """Разрешает только локальные redirect-пути, чтобы исключить open redirect."""
    candidate = (value or "").strip()
    if not candidate:
        candidate = request.headers.get("referer", "").strip()

    if candidate.startswith("/") and not candidate.startswith("//"):
        # Внутренние относительные редиректы безопасны.
        return candidate

    if candidate:
        parsed = urlparse(candidate)
        if parsed.scheme in ("http", "https") and parsed.netloc == request.url.netloc:
            # Абсолютный URL разрешён только если ведёт на этот же хост.
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            return path

    return fallback


def is_same_origin_request(request: Request) -> bool:
    """Проверка CSRF по origin/referer для небезопасных HTTP-методов."""
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
    # Для небраузерных клиентов допускаем отсутствие заголовка.
    return sec_fetch_site in ("", "same-origin", "same-site", "none")


class InMemoryRateLimiter:
    """Простой process-local лимитер по схеме sliding window."""

    def __init__(self):
        self._events: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def allowed(self, key: str, limit: int, window_seconds: int) -> bool:
        # Если число запросов в окне выше лимита — запрос отклоняется.
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
    # Предпочитаем реальный IP из заголовка reverse proxy.
    xff = request.headers.get("x-forwarded-for", "").strip()
    if xff:
        return xff.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def generate_csrf_token() -> str:
    # Криптостойкий токен, связывающий браузер и отправку форм.
    return secrets.token_urlsafe(32)


def is_valid_csrf_token(expected: str | None, provided: str | None) -> bool:
    # Сравнение constant-time снижает риск timing-атак.
    if not expected or not provided:
        return False
    return compare_digest(expected, provided)


async def extract_csrf_token(request: Request) -> str:
    """Извлекает CSRF-токен из заголовка/тела, не ломая дальнейший разбор запроса."""
    header = request.headers.get("x-csrf-token", "").strip()
    if header:
        return header

    content_type = request.headers.get("content-type", "").lower()
    if "application/x-www-form-urlencoded" not in content_type and "multipart/form-data" not in content_type:
        return ""

    body = await request.body()
    if not body:
        return ""

    if "application/x-www-form-urlencoded" in content_type:
        parsed = parse_qs(body.decode("utf-8", errors="ignore"), keep_blank_values=True)
        return (parsed.get("csrf_token", [""])[0] or "").strip()

    # Упрощённое извлечение csrf_token из multipart-формы.
    match = re.search(rb'name="csrf_token"\r\n\r\n([^\r\n]+)', body)
    if not match:
        return ""
    return match.group(1).decode("utf-8", errors="ignore").strip()
