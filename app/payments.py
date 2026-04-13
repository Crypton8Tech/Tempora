"""Payment providers abstraction layer.

Built-in providers: stripe, yookassa, cloudpayments, paypal.
Custom providers can be added through the admin panel.
Each provider implements create_checkout() and handle_webhook().
"""

import json
import logging
from sqlalchemy.orm import Session
from app.models import SiteSetting, Order
from app.config import settings

logger = logging.getLogger(__name__)

PROVIDERS = {
    "stripe": "Stripe",
    "yookassa": "YooKassa",
    "cloudpayments": "CloudPayments",
    "paypal": "PayPal",
}

# Fields each provider needs (key in SiteSetting → label for admin form)
PROVIDER_FIELDS = {
    "stripe": [
        ("stripe_public_key", "Public Key (pk_...)", "text", "pk_test_..."),
        ("stripe_secret_key", "Secret Key (sk_...)", "password", "sk_test_..."),
        ("stripe_webhook_secret", "Webhook Secret (whsec_...)", "password", "whsec_..."),
    ],
    "yookassa": [
        ("yookassa_shop_id", "Shop ID", "text", "123456"),
        ("yookassa_secret_key", "Секретный ключ", "password", "live_..."),
    ],
    "cloudpayments": [
        ("cp_public_id", "Public ID", "text", "pk_..."),
        ("cp_api_secret", "API Secret", "password", ""),
    ],
    "paypal": [
        ("paypal_client_id", "Client ID", "text", ""),
        ("paypal_client_secret", "Client Secret", "password", ""),
        ("paypal_mode", "Режим (sandbox / live)", "text", "sandbox"),
    ],
}

PROVIDER_INSTRUCTIONS = {
    "stripe": {
        "title": "Как настроить Stripe",
        "steps": [
            'Зарегистрируйтесь на <a href="https://dashboard.stripe.com/register" target="_blank">stripe.com</a>',
            "Перейдите в <strong>Developers → API keys</strong>",
            "Скопируйте <strong>Publishable key</strong> и <strong>Secret key</strong>",
            'Для Webhook создайте endpoint в <strong>Developers → Webhooks</strong>: <code>{site_url}/api/stripe/webhook</code>',
            "Выберите событие <code>checkout.session.completed</code>",
        ],
    },
    "yookassa": {
        "title": "Как настроить YooKassa",
        "steps": [
            'Зарегистрируйтесь на <a href="https://yookassa.ru" target="_blank">yookassa.ru</a>',
            "В личном кабинете перейдите в <strong>Интеграция → Ключи API</strong>",
            "Скопируйте <strong>shopId</strong> и <strong>Секретный ключ</strong>",
            'Укажите URL для уведомлений: <code>{site_url}/api/yookassa/webhook</code>',
        ],
    },
    "cloudpayments": {
        "title": "Как настроить CloudPayments",
        "steps": [
            'Зарегистрируйтесь на <a href="https://cloudpayments.ru" target="_blank">cloudpayments.ru</a>',
            "В личном кабинете найдите <strong>Public ID</strong> и <strong>API Secret</strong>",
            'Укажите URL для уведомлений: <code>{site_url}/api/cloudpayments/webhook</code>',
        ],
    },
    "paypal": {
        "title": "Как настроить PayPal",
        "steps": [
            'Зайдите в <a href="https://developer.paypal.com" target="_blank">PayPal Developer</a>',
            "Создайте приложение в <strong>Apps & Credentials</strong>",
            "Скопируйте <strong>Client ID</strong> и <strong>Client Secret</strong>",
            'Укажите Webhook URL: <code>{site_url}/api/paypal/webhook</code>',
        ],
    },
}


def get_active_provider(db: Session) -> str:
    """Return active payment provider slug (default: stripe)."""
    row = db.query(SiteSetting).filter(SiteSetting.key == "payment_provider").first()
    if not row or not row.value:
        return "stripe"
    slug = row.value
    if slug in PROVIDERS:
        return slug
    # Check custom providers
    customs = get_custom_providers(db)
    if slug in customs:
        return slug
    return "stripe"


def get_all_providers(db: Session) -> dict[str, str]:
    """Return dict of all providers (built-in + custom)."""
    result = dict(PROVIDERS)
    result.update(get_custom_providers(db))
    return result


def get_provider_settings(db: Session, provider: str) -> dict[str, str]:
    """Return all saved settings for a given provider."""
    fields = PROVIDER_FIELDS.get(provider, [])
    if not fields:
        # Custom provider — load from custom_provider_<slug>_fields
        customs = get_custom_providers(db)
        if provider in customs:
            fields = get_custom_provider_fields(db, provider)
    keys = [f[0] for f in fields]
    result = {k: "" for k in keys}
    for row in db.query(SiteSetting).filter(SiteSetting.key.in_(keys)).all():
        result[row.key] = row.value or ""
    return result


# ── Custom providers ──────────────────────────────────────────────────────────

def get_custom_providers(db: Session) -> dict[str, str]:
    """Return {slug: name} for all custom providers stored in DB."""
    row = db.query(SiteSetting).filter(SiteSetting.key == "custom_providers").first()
    if not row or not row.value:
        return {}
    try:
        return json.loads(row.value)
    except (json.JSONDecodeError, TypeError):
        return {}


def save_custom_providers(db: Session, providers: dict[str, str]):
    """Save custom providers dict to DB."""
    row = db.query(SiteSetting).filter(SiteSetting.key == "custom_providers").first()
    val = json.dumps(providers, ensure_ascii=False)
    if row:
        row.value = val
    else:
        db.add(SiteSetting(key="custom_providers", value=val))


def get_custom_provider_fields(db: Session, slug: str) -> list[tuple]:
    """Return field definitions for a custom provider."""
    row = db.query(SiteSetting).filter(SiteSetting.key == f"custom_provider_{slug}_fields").first()
    if not row or not row.value:
        return _default_custom_fields(slug)
    try:
        raw = json.loads(row.value)
        return [(f["key"], f["label"], f.get("type", "text"), f.get("placeholder", "")) for f in raw]
    except (json.JSONDecodeError, TypeError):
        return _default_custom_fields(slug)


def save_custom_provider_fields(db: Session, slug: str, fields: list[dict]):
    """Save custom field definitions for a provider."""
    key = f"custom_provider_{slug}_fields"
    row = db.query(SiteSetting).filter(SiteSetting.key == key).first()
    val = json.dumps(fields, ensure_ascii=False)
    if row:
        row.value = val
    else:
        db.add(SiteSetting(key=key, value=val))


def delete_custom_provider(db: Session, slug: str):
    """Remove a custom provider and all its settings."""
    customs = get_custom_providers(db)
    customs.pop(slug, None)
    save_custom_providers(db, customs)
    # Remove field definitions
    fields_key = f"custom_provider_{slug}_fields"
    row = db.query(SiteSetting).filter(SiteSetting.key == fields_key).first()
    if row:
        db.delete(row)
    # Remove field values
    field_defs = get_custom_provider_fields(db, slug)
    for fkey, _, _, _ in field_defs:
        vrow = db.query(SiteSetting).filter(SiteSetting.key == fkey).first()
        if vrow:
            db.delete(vrow)
    # Reset active provider if it was this one
    active = db.query(SiteSetting).filter(SiteSetting.key == "payment_provider").first()
    if active and active.value == slug:
        active.value = "stripe"


def _default_custom_fields(slug: str) -> list[tuple]:
    """Default fields for a new custom provider."""
    return [
        (f"custom_{slug}_api_url", "API URL платёжки", "text", "https://api.example.com/payments"),
        (f"custom_{slug}_api_key", "API Key", "text", ""),
        (f"custom_{slug}_api_secret", "API Secret", "password", ""),
        (f"custom_{slug}_webhook_secret", "Webhook Secret", "password", ""),
    ]


# ── Stripe ────────────────────────────────────────────────────────────────────

def _stripe_checkout(db: Session, order: Order, cart_products: list) -> str | None:
    """Create Stripe checkout session. Returns redirect URL or None."""
    s = get_provider_settings(db, "stripe")
    sk = s.get("stripe_secret_key") or settings.STRIPE_SECRET_KEY
    if not sk:
        return None
    try:
        import stripe
        stripe.api_key = sk

        line_items = []
        for product, qty, _ in cart_products:
            line_items.append({
                "price_data": {
                    "currency": order.currency or "rub",
                    "product_data": {"name": product.name},
                    "unit_amount": int(product.price * 100),
                },
                "quantity": qty,
            })

        site_url = settings.SITE_URL.rstrip("/")
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=line_items,
            mode="payment",
            success_url=f"{site_url}/order-success/{order.order_number}?paid=1",
            cancel_url=f"{site_url}/cart",
            metadata={"order_number": order.order_number},
        )
        order.stripe_session_id = session.id
        db.commit()
        return session.url
    except Exception as e:
        logger.error(f"Stripe checkout error: {e}")
        return None


def _stripe_webhook(db: Session, payload: bytes, sig_header: str) -> bool:
    """Handle Stripe webhook. Returns True if processed."""
    s = get_provider_settings(db, "stripe")
    sk = s.get("stripe_secret_key") or settings.STRIPE_SECRET_KEY
    wh = s.get("stripe_webhook_secret") or settings.STRIPE_WEBHOOK_SECRET
    if not sk:
        return False
    try:
        import stripe
        import json
        stripe.api_key = sk
        if wh:
            event = stripe.Webhook.construct_event(payload, sig_header, wh)
        else:
            event = json.loads(payload)
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return False

    if event.get("type") == "checkout.session.completed":
        session_data = event["data"]["object"]
        order_number = session_data.get("metadata", {}).get("order_number")
        if order_number:
            order = db.query(Order).filter(Order.order_number == order_number).first()
            if order:
                order.status = "paid"
                order.stripe_payment_intent = session_data.get("payment_intent", "")
                db.commit()
    return True


# ── YooKassa ──────────────────────────────────────────────────────────────────

def _yookassa_checkout(db: Session, order: Order, cart_products: list) -> str | None:
    """Create YooKassa payment. Returns redirect URL or None."""
    s = get_provider_settings(db, "yookassa")
    shop_id = s.get("yookassa_shop_id", "")
    secret = s.get("yookassa_secret_key", "")
    if not shop_id or not secret:
        return None
    try:
        import httpx
        import json

        site_url = settings.SITE_URL.rstrip("/")
        total_kopecks = sum(p.price * q for p, q, _ in cart_products)

        payment_data = {
            "amount": {"value": f"{total_kopecks:.2f}", "currency": "RUB"},
            "confirmation": {
                "type": "redirect",
                "return_url": f"{site_url}/order-success/{order.order_number}?paid=1",
            },
            "capture": True,
            "description": f"Заказ {order.order_number}",
            "metadata": {"order_number": order.order_number},
        }

        import uuid as _uuid
        resp = httpx.post(
            "https://api.yookassa.ru/v3/payments",
            json=payment_data,
            auth=(shop_id, secret),
            headers={"Idempotence-Key": str(_uuid.uuid4()), "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("confirmation", {}).get("confirmation_url")
    except Exception as e:
        logger.error(f"YooKassa checkout error: {e}")
        return None


def _yookassa_webhook(db: Session, payload: bytes, sig_header: str) -> bool:
    """Handle YooKassa webhook."""
    try:
        import json
        data = json.loads(payload)
        if data.get("event") == "payment.succeeded":
            obj = data.get("object", {})
            order_number = obj.get("metadata", {}).get("order_number")
            if order_number:
                order = db.query(Order).filter(Order.order_number == order_number).first()
                if order:
                    order.status = "paid"
                    db.commit()
        return True
    except Exception as e:
        logger.error(f"YooKassa webhook error: {e}")
        return False


# ── CloudPayments ─────────────────────────────────────────────────────────────

def _cloudpayments_checkout(db: Session, order: Order, cart_products: list) -> str | None:
    """Create CloudPayments payment link. Returns redirect URL or None."""
    s = get_provider_settings(db, "cloudpayments")
    public_id = s.get("cp_public_id", "")
    api_secret = s.get("cp_api_secret", "")
    if not public_id or not api_secret:
        return None
    try:
        import httpx
        import json

        total = sum(p.price * q for p, q, _ in cart_products)
        site_url = settings.SITE_URL.rstrip("/")

        description = f"Заказ {order.order_number}"
        items = []
        for product, qty, _ in cart_products:
            items.append({
                "label": product.name,
                "price": float(product.price),
                "quantity": float(qty),
                "amount": float(product.price * qty),
                "object": 1, "method": 1,
            })

        payload = {
            "Amount": float(total),
            "Currency": "RUB",
            "Description": description,
            "InvoiceId": order.order_number,
            "SuccessRedirectUrl": f"{site_url}/order-success/{order.order_number}?paid=1",
            "FailRedirectUrl": f"{site_url}/cart",
            "JsonData": json.dumps({"order_number": order.order_number}),
        }

        resp = httpx.post(
            "https://api.cloudpayments.ru/orders/create",
            json=payload,
            auth=(public_id, api_secret),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("Success"):
            return data.get("Model", {}).get("Url")
        return None
    except Exception as e:
        logger.error(f"CloudPayments checkout error: {e}")
        return None


def _cloudpayments_webhook(db: Session, payload: bytes, sig_header: str) -> bool:
    """Handle CloudPayments webhook (Pay notification)."""
    try:
        from urllib.parse import parse_qs
        data = parse_qs(payload.decode())
        status = data.get("Status", [None])[0]
        invoice_id = data.get("InvoiceId", [None])[0]
        if status == "Completed" and invoice_id:
            order = db.query(Order).filter(Order.order_number == invoice_id).first()
            if order:
                order.status = "paid"
                db.commit()
        return True
    except Exception as e:
        logger.error(f"CloudPayments webhook error: {e}")
        return False


# ── PayPal ────────────────────────────────────────────────────────────────────

def _paypal_checkout(db: Session, order: Order, cart_products: list) -> str | None:
    """Create PayPal order. Returns redirect URL or None."""
    s = get_provider_settings(db, "paypal")
    client_id = s.get("paypal_client_id", "")
    client_secret = s.get("paypal_client_secret", "")
    mode = s.get("paypal_mode", "sandbox")
    if not client_id or not client_secret:
        return None

    base_url = "https://api-m.paypal.com" if mode == "live" else "https://api-m.sandbox.paypal.com"
    try:
        import httpx

        # Get access token
        token_resp = httpx.post(
            f"{base_url}/v1/oauth2/token",
            data={"grant_type": "client_credentials"},
            auth=(client_id, client_secret),
            timeout=15,
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        total = sum(p.price * q for p, q, _ in cart_products)
        site_url = settings.SITE_URL.rstrip("/")

        order_data = {
            "intent": "CAPTURE",
            "purchase_units": [{
                "reference_id": order.order_number,
                "amount": {"currency_code": "USD", "value": f"{total:.2f}"},
            }],
            "application_context": {
                "return_url": f"{site_url}/order-success/{order.order_number}?paid=1",
                "cancel_url": f"{site_url}/cart",
            },
        }

        resp = httpx.post(
            f"{base_url}/v2/checkout/orders",
            json=order_data,
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        for link in data.get("links", []):
            if link.get("rel") == "approve":
                return link["href"]
        return None
    except Exception as e:
        logger.error(f"PayPal checkout error: {e}")
        return None


def _paypal_webhook(db: Session, payload: bytes, sig_header: str) -> bool:
    """Handle PayPal webhook."""
    try:
        import json
        data = json.loads(payload)
        if data.get("event_type") == "CHECKOUT.ORDER.APPROVED":
            resource = data.get("resource", {})
            for unit in resource.get("purchase_units", []):
                order_number = unit.get("reference_id")
                if order_number:
                    order = db.query(Order).filter(Order.order_number == order_number).first()
                    if order:
                        order.status = "paid"
                        db.commit()
        return True
    except Exception as e:
        logger.error(f"PayPal webhook error: {e}")
        return False


# ── Dispatcher ────────────────────────────────────────────────────────────────

_CHECKOUT_FN = {
    "stripe": _stripe_checkout,
    "yookassa": _yookassa_checkout,
    "cloudpayments": _cloudpayments_checkout,
    "paypal": _paypal_checkout,
}

_WEBHOOK_FN = {
    "stripe": _stripe_webhook,
    "yookassa": _yookassa_webhook,
    "cloudpayments": _cloudpayments_webhook,
    "paypal": _paypal_webhook,
}


# ── Custom provider generic checkout/webhook ─────────────────────────────────

def _custom_checkout(db: Session, order: Order, cart_products: list, provider_slug: str) -> str | None:
    """Generic checkout for custom providers.

    Sends POST to the provider's API URL with order data and API key.
    Expects JSON response with a redirect URL in one of:
      {"url": "..."}, {"redirect_url": "..."}, {"payment_url": "..."},
      {"confirmation": {"confirmation_url": "..."}}, {"data": {"url": "..."}}
    """
    s = get_provider_settings(db, provider_slug)

    api_url = ""
    api_key = ""
    api_secret = ""
    for k, v in s.items():
        if "api_url" in k and v:
            api_url = v
        elif "api_key" in k and v:
            api_key = v
        elif "api_secret" in k and v:
            api_secret = v

    if not api_url or not api_key:
        logger.warning(f"Custom provider '{provider_slug}': missing api_url or api_key")
        return None

    try:
        import httpx

        total = sum(p.price * q for p, q, _ in cart_products)
        site_url = settings.SITE_URL.rstrip("/")

        items = []
        for product, qty, _ in cart_products:
            items.append({
                "name": product.name,
                "price": float(product.price),
                "quantity": qty,
                "amount": float(product.price * qty),
            })

        payload = {
            "order_number": order.order_number,
            "amount": float(total),
            "currency": order.currency or "RUB",
            "description": f"Order {order.order_number}",
            "items": items,
            "success_url": f"{site_url}/order-success/{order.order_number}?paid=1",
            "cancel_url": f"{site_url}/cart",
            "webhook_url": f"{site_url}/api/custom-webhook/{provider_slug}",
        }

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-API-Key": api_key,
        }

        auth = (api_key, api_secret) if api_secret else None

        resp = httpx.post(api_url, json=payload, headers=headers, auth=auth, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Try to find redirect URL in response
        redirect_url = (
            data.get("url")
            or data.get("redirect_url")
            or data.get("payment_url")
            or data.get("checkout_url")
            or (data.get("confirmation", {}) or {}).get("confirmation_url")
            or (data.get("data", {}) or {}).get("url")
            or (data.get("data", {}) or {}).get("payment_url")
        )

        if redirect_url:
            return redirect_url

        logger.warning(f"Custom provider '{provider_slug}': no redirect URL in response: {data}")
        return None
    except Exception as e:
        logger.error(f"Custom provider '{provider_slug}' checkout error: {e}")
        return None


def _custom_webhook(db: Session, payload: bytes, sig_header: str, provider_slug: str) -> bool:
    """Generic webhook handler for custom providers.

    Tries to find order_number and payment status from the payload.
    Supports JSON and form-encoded payloads.
    """
    try:
        # Try JSON first
        try:
            data = json.loads(payload)
        except (json.JSONDecodeError, ValueError):
            from urllib.parse import parse_qs
            raw = parse_qs(payload.decode())
            data = {k: v[0] if len(v) == 1 else v for k, v in raw.items()}

        # Try to extract order number from various common structures
        order_number = (
            data.get("order_number")
            or data.get("order_id")
            or data.get("InvoiceId")
            or data.get("invoice_id")
            or (data.get("metadata", {}) or {}).get("order_number")
            or (data.get("object", {}) or {}).get("metadata", {}).get("order_number")
            or (data.get("data", {}) or {}).get("order_number")
        )

        if not order_number:
            logger.warning(f"Custom webhook '{provider_slug}': could not find order_number in payload")
            return True  # Don't fail, just log

        # Check if payment is successful
        status_value = (
            data.get("status")
            or data.get("event")
            or data.get("type")
            or data.get("Status")
            or ""
        )
        status_lower = str(status_value).lower()
        success_keywords = {"succeeded", "success", "completed", "paid", "approved", "captured", "confirmed"}

        if any(kw in status_lower for kw in success_keywords):
            order = db.query(Order).filter(Order.order_number == order_number).first()
            if order:
                order.status = "paid"
                db.commit()
                logger.info(f"Custom webhook '{provider_slug}': order {order_number} marked as paid")

        return True
    except Exception as e:
        logger.error(f"Custom webhook '{provider_slug}' error: {e}")
        return False


def create_checkout(db: Session, order: Order, cart_products: list) -> str | None:
    """Create a checkout session with the active payment provider. Returns redirect URL."""
    provider = get_active_provider(db)
    fn = _CHECKOUT_FN.get(provider)
    if fn:
        return fn(db, order, cart_products)
    # Custom provider
    customs = get_custom_providers(db)
    if provider in customs:
        return _custom_checkout(db, order, cart_products, provider)
    return None


def handle_webhook(provider: str, db: Session, payload: bytes, sig_header: str) -> bool:
    """Handle incoming webhook for a specific provider."""
    fn = _WEBHOOK_FN.get(provider)
    if fn:
        return fn(db, payload, sig_header)
    # Custom provider
    return _custom_webhook(db, payload, sig_header, provider)
