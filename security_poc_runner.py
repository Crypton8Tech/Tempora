"""Manual PoC security checks for all critical vulnerability cases."""

from __future__ import annotations

import os
from pathlib import Path
import re

os.environ.setdefault("DATABASE_URL", "sqlite:///./data/poc_security.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "admin123")

from fastapi.testclient import TestClient

from app.auth import hash_password
from app.config import settings
from app.database import SessionLocal, init_db
from app.main import app
from app.models import Category, Order, Product, User
from app.routers import admin as admin_router
from app.routers import api as api_router
from app.routers import auth as auth_router


def _extract_csrf_token(html: str) -> str:
    match = re.search(r'<meta name="csrf-token" content="([^"]+)"', html)
    if match:
        return match.group(1)
    hidden = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return hidden.group(1) if hidden else ""


def _csrf_token(client: TestClient, page: str = "/") -> str:
    response = client.get(page, follow_redirects=True)
    token = _extract_csrf_token(response.text)
    return token


def reset_state() -> None:
    for limiter in (
        api_router.quick_order_limiter,
        auth_router.auth_limiter,
        admin_router.admin_login_limiter,
    ):
        limiter._events.clear()

    db_file = Path("data/poc_security.db")
    db_file.parent.mkdir(parents=True, exist_ok=True)
    if db_file.exists():
        db_file.unlink()
    init_db()


def seed_data() -> int:
    db = SessionLocal()
    try:
        category = Category(slug="watches", name="Watches")
        product = Product(
            sku="SAFE-SKU-1",
            brand="Tempora",
            model="Security",
            name="Secure Watch",
            description="safe",
            price=100.0,
            category=category,
            is_active=True,
        )
        owner = User(email="owner@example.com", password_hash=hash_password("password123"), name="Owner")
        intruder = User(email="intruder@example.com", password_hash=hash_password("password123"), name="Intruder")

        db.add_all([category, product, owner, intruder])
        db.flush()
        db.add(Order(order_number="TS-IDOR-OWN-1", user_id=owner.id, status="pending", total=100, currency="eur"))
        db.add(Order(order_number="TS-IDOR-GUEST-1", guest_name="Alice", guest_email="alice@example.com", status="pending", total=120, currency="eur"))
        db.commit()
        return product.id
    finally:
        db.close()


def run_checks() -> list[tuple[str, bool]]:
    reset_state()
    product_id = seed_data()
    client = TestClient(app)
    results: list[tuple[str, bool]] = []

    # 1) XSS via set-lang payload
    client.cookies.set("lang", "en")
    client.cookies.set("currency", "eur")
    r = client.get('/set-lang/"><script>alert(1)</script>')
    set_cookie = r.headers.get("set-cookie", "").lower()
    results.append((
        "1) XSS via set-lang",
        r.status_code in (302, 404)
        and "<script>" not in r.text.lower()
        and "lang=\"<script" not in set_cookie
        and "lang=%22%3cscript" not in set_cookie,
    ))

    # 2) CSRF via set-currency
    csrf_home = _csrf_token(client, "/")
    r_get = client.get("/set-currency/usd")
    r_post = client.post("/set-currency", data={"cur": "usd", "next_url": "/"}, headers={"origin": "https://evil.example"})
    r_ok = client.post(
        "/set-currency",
        data={"cur": "usd", "next_url": "/", "csrf_token": csrf_home},
        headers={"origin": "http://testserver", "x-csrf-token": csrf_home},
        follow_redirects=False,
    )
    results.append((
        "2) CSRF set-currency",
        "currency=" not in r_get.headers.get("set-cookie", "").lower() and r_post.status_code == 403 and r_ok.status_code == 302,
    ))

    # 3) SQL injection payloads
    r_cat = client.get("/catalog", params={"category": "watches' OR '1'='1"})
    r_prod = client.get("/product/1' OR '1'='1", follow_redirects=False)
    results.append((
        "3) SQL injection in catalog/product",
        r_cat.status_code == 200 and "Secure Watch" not in r_cat.text and r_prod.status_code in (302, 307),
    ))

    # 4) Upload shell file
    csrf_admin_login = _csrf_token(client, "/admin/login")
    login = client.post(
        "/admin/login",
        data={"username": "admin", "password": "admin123", "csrf_token": csrf_admin_login},
        headers={"x-csrf-token": csrf_admin_login},
        follow_redirects=False,
    )
    csrf_admin_add = _csrf_token(client, "/admin/products/add")
    upload_dir = Path(settings.UPLOAD_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    php_before = {p.name for p in upload_dir.glob("*.php")}
    r_up = client.post(
        "/admin/products/add",
        data={
            "name": "Upload Test",
            "sku": "UPLOAD-SAFE-POC",
            "brand": "Tempora",
            "model": "Guard",
            "description": "test",
            "price": "10",
            "category_id": "1",
            "csrf_token": csrf_admin_add,
        },
        headers={"x-csrf-token": csrf_admin_add},
        files={"images": ("hack.php", b"<?php system($_GET['cmd']); ?>", "application/x-php")},
        follow_redirects=False,
    )
    php_after = {p.name for p in upload_dir.glob("*.php")}
    results.append((
        "4) Upload php shell",
        login.status_code in (302, 303) and r_up.status_code in (302, 303) and php_before == php_after,
    ))

    # 5) IDOR in tracking
    csrf_auth = _csrf_token(client, "/auth/login")
    auth_in = client.post(
        "/auth/login",
        data={"email": "intruder@example.com", "password": "password123", "csrf_token": csrf_auth},
        headers={"x-csrf-token": csrf_auth},
        follow_redirects=False,
    )
    r_forbidden = client.get("/track/result", params={"order_number": "TS-IDOR-OWN-1"})
    client.get("/auth/logout", follow_redirects=False)
    r_guest_bad = client.get("/track/result", params={"order_number": "TS-IDOR-GUEST-1"})
    r_guest_ok = client.get("/track/result", params={"order_number": "TS-IDOR-GUEST-1", "email": "alice@example.com"})
    results.append((
        "5) IDOR in track endpoint",
        auth_in.status_code in (302, 303)
        and "order-status" not in r_forbidden.text
        and "order-status" not in r_guest_bad.text
        and "order-status" in r_guest_ok.text,
    ))

    # 6) Rate limiting for quick-order and login
    csrf_quick = _csrf_token(client, "/quick-order/SAFE-SKU-1")
    csrf_login = _csrf_token(client, "/auth/login")
    quick_ok = True
    for _ in range(20):
        rr = client.post(
            "/api/quick-order",
            data={
                "product_id": str(product_id),
                "guest_name": "A",
                "guest_email": "a@a.com",
                "phone": "1",
                "address": "A",
                "quantity": "1",
                "csrf_token": csrf_quick,
            },
            headers={"x-forwarded-for": "198.51.100.10", "x-csrf-token": csrf_quick},
            follow_redirects=False,
        )
        if rr.status_code not in (302, 303):
            quick_ok = False

    r429 = client.post(
        "/api/quick-order",
        data={
            "product_id": str(product_id),
            "guest_name": "A",
            "guest_email": "a@a.com",
            "phone": "1",
            "address": "A",
            "quantity": "1",
            "csrf_token": csrf_quick,
        },
        headers={"x-forwarded-for": "198.51.100.10", "x-csrf-token": csrf_quick},
        follow_redirects=False,
    )

    for _ in range(12):
        client.post(
            "/auth/login",
            data={"email": "none@example.com", "password": "bad", "csrf_token": csrf_login},
            headers={"x-forwarded-for": "203.0.113.99", "x-csrf-token": csrf_login},
        )

    r_login_429 = client.post(
        "/auth/login",
        data={"email": "none@example.com", "password": "bad", "csrf_token": csrf_login},
        headers={"x-forwarded-for": "203.0.113.99", "x-csrf-token": csrf_login},
    )

    results.append((
        "6) Rate limiting",
        quick_ok and r429.status_code == 429 and r_login_429.status_code == 429,
    ))

    return results


if __name__ == "__main__":
    checks = run_checks()
    for title, ok in checks:
        print(f"{title}: {'PASS' if ok else 'FAIL'}")
    print(f"ALL_PASS={all(v for _, v in checks)}")
