"""SQLAlchemy ORM models."""

import datetime
import uuid
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Float
)
from sqlalchemy.orm import relationship

from app.database import Base


def _uuid():
    return str(uuid.uuid4())


# ── Categories ────────────────────────────────────────────────────────────────

class Category(Base):
    __tablename__ = "categories"

    id   = Column(Integer, primary_key=True, autoincrement=True)
    slug = Column(String(50),  unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)

    # Localised names
    name_en = Column(String(100), nullable=True)
    name_de = Column(String(100), nullable=True)
    name_fr = Column(String(100), nullable=True)
    name_it = Column(String(100), nullable=True)
    name_es = Column(String(100), nullable=True)

    products = relationship("Product", back_populates="category", lazy="selectin")


# ── Products ──────────────────────────────────────────────────────────────────

class Product(Base):
    __tablename__ = "products"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    sku         = Column(String(100), unique=True, nullable=False, index=True)
    brand       = Column(String(100), nullable=False, default="")
    model       = Column(String(200), nullable=False, default="")
    price       = Column(Float, nullable=False, default=0)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    is_active   = Column(Boolean, default=True)
    characteristics = Column(JSON, nullable=True)
    created_at  = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.datetime.utcnow,
                         onupdate=datetime.datetime.utcnow)

    # ── Russian (master / fallback) ──────────────────────────────────────
    name        = Column(String(300), nullable=False)
    description = Column(Text, nullable=False, default="")

    # ── English ──────────────────────────────────────────────────────────
    name_en        = Column(String(300), nullable=True)
    description_en = Column(Text, nullable=True)

    # ── German ───────────────────────────────────────────────────────────
    name_de        = Column(String(300), nullable=True)
    description_de = Column(Text, nullable=True)

    # ── French ───────────────────────────────────────────────────────────
    name_fr        = Column(String(300), nullable=True)
    description_fr = Column(Text, nullable=True)

    # ── Italian ──────────────────────────────────────────────────────────
    name_it        = Column(String(300), nullable=True)
    description_it = Column(Text, nullable=True)

    # ── Spanish ──────────────────────────────────────────────────────────
    name_es        = Column(String(300), nullable=True)
    description_es = Column(Text, nullable=True)

    category = relationship("Category", back_populates="products")
    images   = relationship(
        "ProductImage", back_populates="product", lazy="selectin",
        order_by="ProductImage.sort_order", cascade="all, delete-orphan"
    )


class ProductImage(Base):
    __tablename__ = "product_images"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    url        = Column(String(500), nullable=False)
    sort_order = Column(Integer, default=0)

    product = relationship("Product", back_populates="images")


# ── Users ─────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    email         = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    name          = Column(String(200), nullable=False, default="")
    phone         = Column(String(50),  nullable=True)
    telegram_id   = Column(String(100), nullable=True, index=True)
    is_verified   = Column(Boolean, default=False)
    created_at    = Column(DateTime, default=datetime.datetime.utcnow)

    cart_items = relationship("CartItem", back_populates="user", cascade="all, delete-orphan")
    orders     = relationship("Order",    back_populates="user", lazy="selectin")


# ── Cart ──────────────────────────────────────────────────────────────────────

class CartItem(Base):
    __tablename__ = "cart_items"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id",    ondelete="CASCADE"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False)
    quantity   = Column(Integer, nullable=False, default=1)

    user    = relationship("User",    back_populates="cart_items")
    product = relationship("Product", lazy="selectin")


# ── Orders ────────────────────────────────────────────────────────────────────

class Order(Base):
    __tablename__ = "orders"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    order_number          = Column(String(50), unique=True, nullable=False, default=_uuid)
    user_id               = Column(Integer, ForeignKey("users.id"), nullable=True)
    guest_name            = Column(String(200), nullable=True)
    guest_email           = Column(String(255), nullable=True)
    status                = Column(String(50), nullable=False, default="pending")
    total                 = Column(Float, nullable=False, default=0)
    currency              = Column(String(10), nullable=False, default="eur")   # ← was "rub"
    address               = Column(Text, nullable=True)
    phone                 = Column(String(50), nullable=True)
    note                  = Column(Text, nullable=True)
    tracking_number       = Column(String(100), nullable=True)
    stripe_session_id     = Column(String(255), nullable=True)
    stripe_payment_intent = Column(String(255), nullable=True)
    created_at            = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at            = Column(DateTime, default=datetime.datetime.utcnow,
                                   onupdate=datetime.datetime.utcnow)

    user  = relationship("User",      back_populates="orders")
    items = relationship("OrderItem", back_populates="order", lazy="selectin",
                         cascade="all, delete-orphan")


class OrderItem(Base):
    __tablename__ = "order_items"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    order_id     = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False)
    product_id   = Column(Integer, ForeignKey("products.id"), nullable=True)
    product_name = Column(String(300), nullable=False)
    product_sku  = Column(String(100), nullable=False)
    price        = Column(Float, nullable=False)
    quantity     = Column(Integer, nullable=False, default=1)
    image_url    = Column(String(500), nullable=True)

    order = relationship("Order", back_populates="items")


# ── Site Settings ─────────────────────────────────────────────────────────────

class SiteSetting(Base):
    __tablename__ = "site_settings"

    id    = Column(Integer, primary_key=True, autoincrement=True)
    key   = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
