"""Centralized security regression tests for critical endpoints."""

from __future__ import annotations

import os
from pathlib import Path
import re
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient


os.environ.setdefault("DATABASE_URL", "sqlite:///./data/test_security.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from app.auth import hash_password
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Category, Order, Product, User
from app.routers import admin as admin_router
from app.routers import api as api_router
from app.routers import auth as auth_router

@pytest.fixture(autouse=True)
def clean_state():
    api_router.quick_order_limiter._events.clear()
    auth_router.auth_limiter._events.clear()
    admin_router.admin_login_limiter._events.clear()

    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _seed_product() -> Product:
    db = SessionLocal()
    try:
        category = Category(slug="watches", name="Watches")
        product = Product(
            sku="SAFE-SKU-1",
            brand="Tempora",
            model="Security",
            name="Secure Watch",
            description="A safe product",
            price=99.0,
            category=category,
            is_active=True,
        )
        db.add_all([category, product])
        db.commit()
        db.refresh(product)
        return product
    finally:
        db.close()


def _extract_csrf_token(html: str) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    if match:
        return match.group(1)
    hidden = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return hidden.group(1) if hidden else ""


def _csrf_token(client: TestClient, page: str = "/") -> str:
    response = client.get(page, follow_redirects=True)
    token = _extract_csrf_token(response.text)
    assert token
    return token


def test_xss_payload_in_set_lang_get_does_not_change_state(client: TestClient):
    client.cookies.set("lang", "en")
    client.cookies.set("currency", "eur")
    response = client.get('/set-lang/"><script>alert("XSS")</script>', headers={"referer": "http://testserver/catalog"})
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert response.status_code in (302, 404)
    assert "<script>" not in response.text.lower()
    assert "lang=\"<script" not in set_cookie
    assert "lang=%22%3cscript" not in set_cookie


def test_malicious_lang_cookie_is_normalized_before_render(client: TestClient):
    client.cookies.set("lang", '"><script>alert("x")</script>')
    response = client.get("/")
    assert response.status_code == 200
    assert '<script>alert("x")</script>' not in response.text
    assert 'lang="en"' in response.text


def test_csrf_currency_switch_blocked_for_cross_site_post_and_get_is_noop(client: TestClient):
    client.cookies.set("lang", "en")
    client.cookies.set("currency", "eur")

    csrf = _csrf_token(client, "/")

    get_response = client.get("/set-currency/usd", headers={"referer": "http://testserver/catalog"}, follow_redirects=False)
    assert get_response.status_code == 302
    assert "currency=usd" not in get_response.headers.get("set-cookie", "").lower()

    blocked = client.post(
        "/set-currency",
        data={"cur": "usd", "next_url": "/"},
        headers={"origin": "https://evil.example"},
    )
    assert blocked.status_code == 403

    allowed = client.post(
        "/set-currency",
        data={"cur": "usd", "next_url": "/", "csrf_token": csrf},
        headers={"origin": "http://testserver"},
        follow_redirects=False,
    )
    assert allowed.status_code == 302
    assert "currency=usd" in allowed.headers.get("set-cookie", "").lower()


def test_catalog_and_product_reject_sqli_payloads(client: TestClient):
    _seed_product()

    catalog_response = client.get("/catalog", params={"category": "watches' OR '1'='1"})
    assert catalog_response.status_code == 200
    assert "Secure Watch" not in catalog_response.text

    product_response = client.get("/product/1' OR '1'='1", follow_redirects=False)
    assert product_response.status_code in (302, 307)
    assert product_response.headers["location"] == "/catalog"


def test_admin_upload_rejects_php_shell_file(client: TestClient):
    csrf_login = _csrf_token(client, "/admin/login")

    db = SessionLocal()
    try:
        category = Category(slug="watches", name="Watches")
        db.add(category)
        db.commit()
        db.refresh(category)
        category_id = category.id
    finally:
        db.close()

    login = client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin123", "csrf_token": csrf_login},
        follow_redirects=False,
    )
    assert login.status_code in (302, 303)

    csrf_admin = _csrf_token(client, "/admin/products/add")

    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    php_before = {p.name for p in upload_dir.glob("*.php")}

    shell_name = f"shell_{uuid4().hex}.php"
    response = client.post(
        "/admin/products/add",
        data={
            "name": "Upload Test",
            "sku": "UPLOAD-SAFE-1",
            "brand": "Tempora",
            "model": "Guard",
            "description": "Shell test",
            "price": "100",
            "category_id": str(category_id),
            "csrf_token": csrf_admin,
        },
        files={"images": (shell_name, b"<?php system($_GET['cmd']); ?>", "application/x-php")},
        follow_redirects=False,
    )
    assert response.status_code in (302, 303)

    php_after = {p.name for p in upload_dir.glob("*.php")}
    assert php_after == php_before

    db = SessionLocal()
    try:
        product = db.query(Product).filter(Product.sku == "UPLOAD-SAFE-1").first()
        assert product is not None
        assert len(product.images) == 0
    finally:
        db.close()


def test_track_endpoint_blocks_idor_for_guest_and_wrong_user(client: TestClient):
    csrf_login = _csrf_token(client, "/auth/login")

    db = SessionLocal()
    try:
        owner = User(email="owner@example.com", password_hash=hash_password("password123"), name="Owner")
        intruder = User(email="intruder@example.com", password_hash=hash_password("password123"), name="Intruder")
        db.add_all([owner, intruder])
        db.flush()

        owner_order = Order(
            order_number="TS-IDOR-OWN-1",
            user_id=owner.id,
            status="pending",
            total=100,
            currency="eur",
        )
        guest_order = Order(
            order_number="TS-IDOR-GUEST-1",
            guest_name="Alice",
            guest_email="alice@example.com",
            status="pending",
            total=120,
            currency="eur",
        )
        db.add_all([owner_order, guest_order])
        db.commit()
    finally:
        db.close()

    login_intruder = client.post(
        "/auth/login",
        data={"email": "intruder@example.com", "password": "password123", "csrf_token": csrf_login},
        follow_redirects=False,
    )
    assert login_intruder.status_code in (302, 303)

    forbidden_for_other_user = client.get("/track/result", params={"order_number": "TS-IDOR-OWN-1"})
    assert "order-status" not in forbidden_for_other_user.text

    client.get("/auth/logout", follow_redirects=False)

    no_email = client.get("/track/result", params={"order_number": "TS-IDOR-GUEST-1"})
    wrong_email = client.get(
        "/track/result",
        params={"order_number": "TS-IDOR-GUEST-1", "email": "other@example.com"},
    )
    correct_email = client.get(
        "/track/result",
        params={"order_number": "TS-IDOR-GUEST-1", "email": "alice@example.com"},
    )

    assert "order-status" not in no_email.text
    assert "order-status" not in wrong_email.text
    assert "order-status" in correct_email.text


def test_rate_limiting_for_quick_order_and_login(client: TestClient):
    product = _seed_product()
    csrf_quick = _csrf_token(client, f"/quick-order/{product.sku}")
    csrf_login = _csrf_token(client, "/auth/login")

    for _ in range(20):
        response = client.post(
            "/api/quick-order",
            data={
                "product_id": str(product.id),
                "guest_name": "Rate Limit",
                "guest_email": "rate@example.com",
                "phone": "+100000000",
                "address": "Test street",
                "quantity": "1",
                "csrf_token": csrf_quick,
            },
            headers={"x-forwarded-for": "198.51.100.10", "x-csrf-token": csrf_quick},
            follow_redirects=False,
        )
        assert response.status_code in (302, 303)

    blocked_quick_order = client.post(
        "/api/quick-order",
        data={
            "product_id": str(product.id),
            "guest_name": "Rate Limit",
            "guest_email": "rate@example.com",
            "phone": "+100000000",
            "address": "Test street",
            "quantity": "1",
            "csrf_token": csrf_quick,
        },
        headers={"x-forwarded-for": "198.51.100.10", "x-csrf-token": csrf_quick},
        follow_redirects=False,
    )
    assert blocked_quick_order.status_code == 429

    for _ in range(12):
        login_response = client.post(
            "/auth/login",
            data={"email": "unknown@example.com", "password": "bad-password", "csrf_token": csrf_login},
            headers={"x-forwarded-for": "203.0.113.99", "x-csrf-token": csrf_login},
        )
        assert login_response.status_code == 200

    blocked_login = client.post(
        "/auth/login",
        data={"email": "unknown@example.com", "password": "bad-password", "csrf_token": csrf_login},
        headers={"x-forwarded-for": "203.0.113.99", "x-csrf-token": csrf_login},
    )
    assert blocked_login.status_code == 429


def test_security_headers_are_present(client: TestClient):
    response = client.get("/")
    assert response.headers.get("content-security-policy")
    assert response.headers.get("x-frame-options") == "DENY"
    assert response.headers.get("x-content-type-options") == "nosniff"
    set_cookie = response.headers.get("set-cookie", "").lower()
    assert "csrf_token=" in set_cookie
    assert "samesite=strict" in set_cookie
