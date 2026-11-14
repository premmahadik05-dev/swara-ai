"""ORM models.  Money is stored as integer paise; quantities as Numeric(12,3)."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import JSON, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Product(Base):
    __tablename__ = "products"
    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    name_en: Mapped[str] = mapped_column(String(120))
    name_gu: Mapped[str] = mapped_column(String(120), default="")
    name_hi: Mapped[str] = mapped_column(String(120), default="")
    category: Mapped[str] = mapped_column(String(60), index=True, default="")
    unit: Mapped[str] = mapped_column(String(8))  # kg | l | pack | pc
    price_paise: Mapped[int] = mapped_column(Integer)
    stock: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal(0))
    reorder_level: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=Decimal(0))
    pack_size: Mapped[Optional[Decimal]] = mapped_column(Numeric(10, 3), nullable=True)
    pack_size_unit: Mapped[Optional[str]] = mapped_column(String(4), nullable=True)
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    default_for: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    brand: Mapped[str] = mapped_column(String(80), default="")
    ean: Mapped[Optional[str]] = mapped_column(String(14), nullable=True, index=True)
    # where the product record came from: curated (hand-written staple) | off_india (Open Food Facts via the catalogue) | manual (entered in the app)
    source: Mapped[str] = mapped_column(String(16), default="manual")
    source_ref: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    # where the selling price came from: demo (curator placeholder, NOT an observed price) | shop (set by the shopkeeper)
    price_basis: Mapped[str] = mapped_column(String(8), default="shop")
    cost_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # purchase cost; only the shopkeeper can know it
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class Customer(Base):
    """A shop customer. Demo rows are flagged synthetic; real ones are entered by the shopkeeper."""

    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), index=True)
    phone: Mapped[str] = mapped_column(String(20), default="")
    language: Mapped[str] = mapped_column(String(12), default="")  # preferred: a key from app/languages.py (gu, hi, en, hinglish, mr, bn, ta, te, kn, ml, pa) or ""
    notes: Mapped[str] = mapped_column(String(300), default="")
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class CatalogItem(Base):
    """Reference catalogue row built from Open Food Facts India by scripts/data/build_catalog.py (no prices)."""

    __tablename__ = "catalog_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    ean: Mapped[str] = mapped_column(String(14), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    name_raw: Mapped[str] = mapped_column(String(240), default="")
    brand: Mapped[str] = mapped_column(String(80), default="", index=True)
    category: Mapped[str] = mapped_column(String(60), index=True)
    pack_size: Mapped[Decimal] = mapped_column(Numeric(10, 4))
    pack_unit: Mapped[str] = mapped_column(String(4))  # kg | l | pc
    pack_label: Mapped[str] = mapped_column(String(20), default="")
    quantity_raw: Mapped[str] = mapped_column(String(40), default="")
    off_categories_raw: Mapped[str] = mapped_column(String(400), default="")
    last_modified: Mapped[str] = mapped_column(String(10), default="")
    source_id: Mapped[str] = mapped_column(String(40), default="")
    provenance: Mapped[str] = mapped_column(String(12), default="transformed")
    transforms: Mapped[str] = mapped_column(String(160), default="")
    split: Mapped[str] = mapped_column(String(5), default="train")


class Order(Base):
    __tablename__ = "orders"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(40), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="confirmed", index=True)  # confirmed|fulfilled|cancelled
    channel: Mapped[str] = mapped_column(String(8), default="text")  # voice | text | seed
    language: Mapped[str] = mapped_column(String(12), default="en")
    customer_name: Mapped[str] = mapped_column(String(80), default="Walk-in customer")
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True, index=True)
    total_paise: Mapped[int] = mapped_column(Integer, default=0)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    items: Mapped[list["OrderItem"]] = relationship(back_populates="order", cascade="all, delete-orphan", lazy="selectin")

    @property
    def code(self) -> str:
        return f"SW-{self.created_at:%y%m%d}-{self.id:04d}"


class OrderItem(Base):
    __tablename__ = "order_items"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    product_name: Mapped[str] = mapped_column(String(120))
    qty: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    unit: Mapped[str] = mapped_column(String(8))
    unit_price_paise: Mapped[int] = mapped_column(Integer)
    line_total_paise: Mapped[int] = mapped_column(Integer)
    order: Mapped[Order] = relationship(back_populates="items")


class StockMovement(Base):
    __tablename__ = "stock_movements"
    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), index=True)
    delta: Mapped[Decimal] = mapped_column(Numeric(12, 3))
    reason: Mapped[str] = mapped_column(String(16))  # order | cancel | restock | adjust
    order_id: Mapped[Optional[int]] = mapped_column(ForeignKey("orders.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ConversationSession(Base):
    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    state: Mapped[dict] = mapped_column(JSON, default=dict)  # DialogState.to_dict()
    language: Mapped[str] = mapped_column(String(12), default="en")
    customer_id: Mapped[Optional[int]] = mapped_column(ForeignKey("customers.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, index=True)
    turns: Mapped[list["Turn"]] = relationship(back_populates="session", cascade="all, delete-orphan", order_by="Turn.id")


class Turn(Base):
    __tablename__ = "turns"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(ForeignKey("sessions.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # customer | assistant
    text: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(12), default="")
    input_mode: Mapped[str] = mapped_column(String(8), default="text")  # voice | stream | text
    stt_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    nlu_ms: Mapped[Optional[float]] = mapped_column(Numeric(8, 2), nullable=True)
    tts_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    audio_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)  # parse + events, for the Live screen
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    session: Mapped[ConversationSession] = relationship(back_populates="turns")


class ApiCall(Base):
    """Metadata of every outbound model call (never payloads, never keys)."""

    __tablename__ = "api_calls"
    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(24), index=True)  # gnani-stt | gnani-tts | evon
    model: Mapped[str] = mapped_column(String(32), default="")
    ok: Mapped[bool] = mapped_column(Boolean, default=True)
    status_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    units: Mapped[int] = mapped_column(Integer, default=0)  # audio bytes in / characters synthesised
    attempts: Mapped[int] = mapped_column(Integer, default=1)  # how many tries the call needed (2.6.0; older rows count as 1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


Index("ix_orders_created_status", Order.created_at, Order.status)


class User(Base):
    """A person who can sign in. Passwords are stored only as salted scrypt hashes."""

    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)  # always lower-case
    full_name: Mapped[str] = mapped_column(String(80))
    password_hash: Mapped[str] = mapped_column(String(300))
    role: Mapped[str] = mapped_column(String(8), default="staff")  # owner | staff
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    email_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    terms_accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    preferences: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuthSession(Base):
    """One signed-in browser. The cookie holds a random secret; only its SHA-256 is stored here."""

    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(primary_key=True)
    public_id: Mapped[str] = mapped_column(String(16), unique=True, index=True)  # shown in the session list; not a credential
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    remember: Mapped[bool] = mapped_column(Boolean, default=False)
    user_agent: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class AuthToken(Base):
    """Single-use link tokens for e-mail verification and password reset (hash stored, never the token)."""

    __tablename__ = "auth_tokens"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(8))  # verify | reset
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class ContactMessage(Base):
    __tablename__ = "contact_messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    email: Mapped[str] = mapped_column(String(254))
    topic: Mapped[str] = mapped_column(String(24), default="general")
    message: Mapped[str] = mapped_column(Text)
    emailed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    handled_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


# ---- payments (2.7.0) ---------------------------------------------------------------------------------------------------------
# Payments are separate records that point at an order. Confirming an order, and taking stock off the shelf, never wait for a payment and
# never repeat because of one: an order without any payment keeps working exactly as before. Money is integer paise throughout.
PAYMENT_STATUSES = ("pending", "paid", "failed", "cancelled", "refunded", "partially_refunded")
PAID_STATUSES = ("paid", "partially_refunded", "refunded")  # the customer's money was collected (it may since have been given back)


class Payment(Base):
    __tablename__ = "payments"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    method: Mapped[str] = mapped_column(String(8))  # cash | upi | razorpay
    # who confirms it: none (cash, recorded by a person) | manual (a person confirms a UPI payment) | razorpay | razorpay_qr (Razorpay's dynamic UPI QR)
    provider: Mapped[str] = mapped_column(String(12), default="none")
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    amount_paise: Mapped[int] = mapped_column(Integer)  # what was due: the order total at the moment the payment was started
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    amount_received_paise: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # cash handed over (may be more than due); provider: amount captured
    refunded_paise: Mapped[int] = mapped_column(Integer, default=0)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    provider_order_id: Mapped[Optional[str]] = mapped_column(String(48), unique=True, nullable=True)
    provider_payment_id: Mapped[Optional[str]] = mapped_column(String(48), unique=True, nullable=True)
    provider_qr_id: Mapped[Optional[str]] = mapped_column(String(48), unique=True, nullable=True)
    qr_image_url: Mapped[Optional[str]] = mapped_column(String(300), nullable=True)  # Razorpay's hosted QR picture (provider QR only)
    provider_method: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # what the customer used in Checkout: upi, card, netbanking, wallet ...
    upi_payee: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)  # the shop's UPI ID the manual QR pointed at
    verified: Mapped[bool] = mapped_column(Boolean, default=False)  # True only when Razorpay itself confirmed it (signature plus a provider lookup, or a signed webhook)
    verification: Mapped[str] = mapped_column(String(16), default="none")  # none | cash | manual | signature | webhook | provider
    reference_note: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)  # manual UPI: the bank reference the person saw
    failure_code: Mapped[Optional[str]] = mapped_column(String(48), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    attention: Mapped[Optional[str]] = mapped_column(String(24), nullable=True)  # duplicate_collection | late_payment | amount_mismatch: needs the owner's eyes
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # copied from the order, so the Demo data switch filters payments too
    created_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    paid_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, index=True)
    order: Mapped[Order] = relationship(lazy="joined")
    refunds: Mapped[list["Refund"]] = relationship(back_populates="payment", order_by="Refund.id", lazy="selectin")

    __table_args__ = (
        CheckConstraint("amount_paise > 0", name="ck_payments_amount_positive"),
        CheckConstraint("refunded_paise >= 0 AND refunded_paise <= COALESCE(amount_paise, 0)", name="ck_payments_refunded_in_range"),
        # At most one open attempt per order, enforced by the database, so two simultaneous taps cannot start two payments.
        Index("uq_payments_one_pending_per_order", "order_id", unique=True, sqlite_where=text("status = 'pending'"), postgresql_where=text("status = 'pending'")),
    )

    @property
    def code(self) -> str:
        return f"PAY-{self.created_at:%y%m%d}-{self.id:04d}"


class PaymentEvent(Base):
    """What happened to a payment, in order: the audit trail. Holds ids, amounts and statuses only, never card numbers, UPI IDs or PINs."""

    __tablename__ = "payment_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[Optional[int]] = mapped_column(ForeignKey("payments.id"), nullable=True, index=True)
    source: Mapped[str] = mapped_column(String(10))  # webhook | checkout | user | system
    event_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)  # Razorpay's unique event id: a delivered event is processed once
    event_type: Mapped[str] = mapped_column(String(48))
    status_before: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    status_after: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    signature_ok: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    actor_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    message: Mapped[str] = mapped_column(String(240), default="")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class Refund(Base):
    __tablename__ = "refunds"
    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id"), index=True)
    kind: Mapped[str] = mapped_column(String(8))  # provider (Razorpay API) | manual (cash or manual UPI, recorded by the owner)
    amount_paise: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)  # pending | processed | failed
    reason: Mapped[str] = mapped_column(String(200), default="")
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True)
    provider_refund_id: Mapped[Optional[str]] = mapped_column(String(48), unique=True, nullable=True)
    speed_processed: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    failure_reason: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    initiated_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    processed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    payment: Mapped[Payment] = relationship(back_populates="refunds")

    __table_args__ = (CheckConstraint("amount_paise > 0", name="ck_refunds_amount_positive"),)

    @property
    def code(self) -> str:
        return f"REF-{self.created_at:%y%m%d}-{self.id:04d}"


class Invoice(Base):
    """One numbered invoice per order, created the first time it is asked for. The shop name is kept as it was on the day."""

    __tablename__ = "invoices"
    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), unique=True)
    year: Mapped[int] = mapped_column(Integer)
    seq: Mapped[int] = mapped_column(Integer)
    number: Mapped[str] = mapped_column(String(24), unique=True)  # INV-2026-000001
    shop_name: Mapped[str] = mapped_column(String(80))
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    issued_by_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    __table_args__ = (UniqueConstraint("year", "seq", name="uq_invoices_year_seq"),)


class SchemaMigration(Base):
    """Which additive migrations this database has had applied (see app/migrations.py)."""

    __tablename__ = "schema_migrations"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    description: Mapped[str] = mapped_column(String(160), default="")
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
