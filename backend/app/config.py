"""Application settings (environment variables / .env). Secrets never leave the backend."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent
ENV_FILE = REPO_ROOT / ".env"


def default_db_path(data_dir: Path) -> Path:
    """swara.db for new installs. A database created before the rename (dukaanmitra.db) keeps being used if it is
    there and the new file is not, so nobody loses their shop's data. Set DATABASE_URL to override either."""
    new, old = data_dir / "swara.db", data_dir / "dukaanmitra.db"
    return old if old.exists() and not new.exists() else new


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=str(ENV_FILE), env_file_encoding="utf-8", extra="ignore")

    api_docs: bool = True   # the API reference page at /docs and /openapi.json; set API_DOCS=false on a public server if you do not want it shown

    # --- Gnani AI (https://docs.gnani.ai)
    gnani_api_key: Optional[SecretStr] = None
    gnani_base_url: str = "https://api.vachana.ai"
    gnani_stt_model: str = "prisma-v2.5"  # prisma-v2.5 (default) | prisma-v3.0
    gnani_stt_format: str = "verbatim"  # verbatim | transcribe (ITN, hi-IN/en-IN only on v2.5)
    gnani_stt_bias: bool = False  # v2.5 bias_list from inventory vocabulary (experimental)
    gnani_tts_model: str = "timbre-v2.5"
    gnani_timeout_s: float = 40.0  # ceiling for every call (the one setting that existed before 2.6.0); the two below are the limits actually used
    gnani_stt_timeout_s: float = Field(default=20.0, ge=1.0, le=120.0)  # speech-to-text: audio is at most 30 s and Prisma answers in seconds
    gnani_tts_timeout_s: float = Field(default=15.0, ge=1.0, le=120.0)  # text-to-speech: replies are a sentence or two
    gnani_connect_timeout_s: float = Field(default=5.0, ge=0.5, le=60.0)  # opening a connection
    gnani_max_calls_per_hour: int = 300  # local guard so a bug or a loop cannot burn the free credits

    # voices (Timbre v2.5 catalogue)
    tts_voice_gu: str = "Falak"
    tts_voice_hi: str = "Nalini"
    tts_voice_en: str = "Devika"
    tts_voice_hinglish: str = "Poorvi"
    tts_voice_mr: str = "Zahira"
    tts_voice_bn: str = "Kirra"
    tts_voice_ta: str = "Asmita"
    tts_voice_te: str = "Lavanya"
    tts_voice_kn: str = "Saanvi"
    tts_voice_ml: str = "Reshma"
    tts_voice_pa: str = "Mehuli"
    verification_file: Path = REPO_ROOT / "eval" / "results" / "live_verification.json"  # written by scripts/verify_gnani.py, read by GET /api/languages
    disabled_languages: str = ""  # e.g. "mr,bn": switched off in the selector and refused by the API (English cannot be switched off)
    tts_speed: float = 1.0
    tts_sample_rate: int = 24000

    # --- optional reasoning model (Evon is NOT on Gnani's API; see docs/EVON.md)
    evon_base_url: Optional[str] = None  # OpenAI-compatible endpoint you host yourself
    evon_model: str = "evon-v3.3"
    evon_api_key: Optional[SecretStr] = None

    # --- app
    database_url: str = f"sqlite:///{default_db_path(BACKEND_DIR / 'data').as_posix()}"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"
    max_upload_bytes: int = 8 * 1024 * 1024
    max_audio_seconds: float = 30.0
    rate_limit_per_minute: int = 60
    store_name: str = "Patel Kirana & General Store (demo)"
    data_dir: Path = BACKEND_DIR / "data"
    seed_on_startup: bool = True
    # --- accounts (see docs/AUTHENTICATION.md)
    owner_email: str = ""  # if set, only this address becomes the owner; otherwise the first account created is the owner
    public_demo: bool = True  # False: POST /api/text/parse (the landing page's try-it box) needs a sign-in, so a stranger cannot probe the shop's items, prices and stock
    allow_signup: bool = True  # False: the sign-up form is closed (the owner still exists; use scripts/auth_admin.py to add people)
    public_url: str = "http://localhost:8000"  # used in e-mailed links; never taken from the request's Host header
    cookie_secure: Optional[bool] = None  # None = follow PUBLIC_URL (https => Secure cookie)
    session_hours: int = 12  # absolute lifetime of a normal session
    session_idle_minutes: int = 120  # signed out after this long without a request
    remember_days: int = 30  # absolute lifetime when "Remember me" is ticked
    remember_idle_days: int = 7
    scrypt_log2_n: int = Field(default=15, ge=10, le=20)  # password hashing cost; the tests lower it, nothing else should
    scrypt_p: int = Field(default=3, ge=1, le=8)
    auth_rate_per_minute: int = 20  # sign-in / sign-up / reset / contact requests per IP per minute
    login_max_failures: int = 5  # failed sign-ins per e-mail address (and 5x that per IP) before a temporary block
    login_lockout_minutes: int = 15
    require_email_verification: Optional[bool] = None  # None = required only when SMTP is configured
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: Optional[SecretStr] = None
    smtp_from: str = ""  # e.g. "SWARA AI <no-reply@yourdomain.com>"
    smtp_security: str = "starttls"  # starttls | ssl | none
    contact_to: str = ""  # if set (and SMTP works) contact-form messages are also e-mailed here
    # How many days of GENERATED demo orders to create on a fresh database (7-366). Enough to fill the weekly/monthly charts
    # and to compare one 30-day window with the one before it.
    demo_history_days: int = 120

    # --- payments (2.7.0, see docs/PAYMENTS_API.md and docs/RAZORPAY_SETUP.md). Secrets live here and never leave the backend.
    payment_mode: str = "test"  # test | live. Live needs live keys (rzp_live_...) AND PAYMENT_MODE=live; nothing switches it on by itself
    razorpay_key_id: str = ""  # the public key id, for example rzp_test_xxxx; the browser needs it to open Checkout
    razorpay_key_secret: Optional[SecretStr] = None
    razorpay_webhook_secret: Optional[SecretStr] = None  # the secret typed into Razorpay's webhook screen; different from the key secret
    razorpay_base_url: str = "https://api.razorpay.com"
    razorpay_timeout_s: float = Field(default=20.0, ge=2.0, le=60.0)
    razorpay_upi_qr: bool = False  # Razorpay's dynamic UPI QR needs to be switched on for your account by Razorpay; see docs/RAZORPAY_SETUP.md
    upi_vpa: str = ""  # the shop's own UPI ID for the manual QR (not a secret); changed on the Settings page
    upi_payee_name: str = ""  # shown in the customer's UPI app next to the amount; defaults to the shop name
    payment_pending_minutes: int = Field(default=30, ge=5, le=1440)  # a pending payment older than this is shown as stale (it is never closed on its own)

    @field_validator("payment_mode")
    @classmethod
    def _payment_mode(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("test", "live"):
            raise ValueError("PAYMENT_MODE must be test or live")
        return v

    @field_validator("gnani_stt_model")
    @classmethod
    def _stt_model(cls, v: str) -> str:
        if v not in ("prisma-v2.5", "prisma-v3.0"):
            raise ValueError("GNANI_STT_MODEL must be prisma-v2.5 or prisma-v3.0")
        return v

    @field_validator("smtp_security")
    @classmethod
    def _smtp_security(cls, v: str) -> str:
        v = v.strip().lower()
        if v not in ("starttls", "ssl", "none"):
            raise ValueError("SMTP_SECURITY must be starttls, ssl or none")
        return v

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host.strip() and self.smtp_from.strip())

    @property
    def verification_required(self) -> bool:
        """E-mail verification is only enforced when mail can actually be sent; otherwise nobody could ever sign in."""
        if not self.smtp_configured:
            return False
        return True if self.require_email_verification is None else self.require_email_verification

    @property
    def secure_cookies(self) -> bool:
        return self.public_url.lower().startswith("https://") if self.cookie_secure is None else self.cookie_secure

    @property
    def gnani_key(self) -> Optional[str]:
        return self.gnani_api_key.get_secret_value() if self.gnani_api_key else None

    @property
    def gnani_configured(self) -> bool:
        k = self.gnani_key
        return bool(k and k.strip() and not k.startswith("your_"))

    @property
    def razorpay_secret(self) -> Optional[str]:
        return self.razorpay_key_secret.get_secret_value() if self.razorpay_key_secret else None

    @property
    def razorpay_webhook_key(self) -> Optional[str]:
        k = self.razorpay_webhook_secret.get_secret_value() if self.razorpay_webhook_secret else None
        return k if k and k.strip() else None

    @property
    def razorpay_problem(self) -> Optional[str]:
        """Why Razorpay is switched off, in words the owner can act on; None when it is ready to use. Test keys need test mode and live keys
        need live mode, so a live key can never be used by accident while PAYMENT_MODE is test."""
        kid, sec = self.razorpay_key_id.strip(), (self.razorpay_secret or "").strip()
        if not kid or not sec:
            return "Razorpay keys are not set. Add RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET to .env."
        if kid.startswith("your_") or sec.startswith("your_"):
            return "Razorpay keys are still the placeholders from .env.example."
        want = "rzp_test_" if self.payment_mode == "test" else "rzp_live_"
        if not kid.startswith(want):
            return (f"PAYMENT_MODE is {self.payment_mode} but the key id does not start with {want}. Use matching keys, or change PAYMENT_MODE.")
        return None

    @property
    def razorpay_enabled(self) -> bool:
        return self.razorpay_problem is None

    @property
    def cors_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def tts_dir(self) -> Path:
        return self.data_dir / "tts_cache"


@lru_cache
def get_settings() -> Settings:
    return Settings()
