from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # Auth
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours

    # Login rate limiting (redis-backed, see services/auth.py). Two independent
    # gates: per-account (brute force against one email) and per-IP (credential
    # spraying across many emails from one source). Either tripping → HTTP 429.
    LOGIN_MAX_ATTEMPTS_PER_ACCOUNT: int = 5
    LOGIN_MAX_ATTEMPTS_PER_IP: int = 20
    LOGIN_LOCKOUT_WINDOW_SECONDS: int = 900  # 15 minutes

    # Encryption (for platform tokens at rest)
    ENCRYPTION_KEY: str

    # Meta app credentials. Used by the connect-flow debug_token expiry read and
    # (later) the worker fb_exchange_token refresh task. Must be the same Meta
    # app that minted the pasted token, else debug_token/exchange fails.
    META_APP_ID: str = ""
    META_APP_SECRET: str = ""

    # TikTok OAuth
    TIKTOK_APP_ID: str = ""
    TIKTOK_APP_SECRET: str = ""
    TIKTOK_REDIRECT_URI: str = "http://localhost:8000/api/v1/connections/tiktok/oauth/callback"
    FRONTEND_URL: str = "http://localhost:3000"

    # Google Ads OAuth + API
    # developer_token + an MCC login_customer_id are required in addition to the
    # OAuth client — see docs/google-ads-api-v24.1-comprehensive-links.md (auth).
    GOOGLE_ADS_DEVELOPER_TOKEN: str = ""
    GOOGLE_ADS_CLIENT_ID: str = ""
    GOOGLE_ADS_CLIENT_SECRET: str = ""
    GOOGLE_ADS_LOGIN_CUSTOMER_ID: str = ""  # MCC/manager customer id, digits only
    GOOGLE_ADS_REDIRECT_URI: str = "http://localhost:8000/api/v1/connections/google/oauth/callback"

    # OpenAI (on-demand AI narrative summary — see services/ai_summary.py)
    # Safe defaults so the app boots without a key; the summary endpoint returns
    # a distinguishable 502 (never a fake summary) when the key is empty.
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # Email delivery. Two transports (see services/email.py):
    #   1. Resend HTTP API (port 443) — preferred. Set RESEND_API_KEY. Required
    #      on hosts that block outbound SMTP ports (e.g. Railway blocks 25/465/587).
    #   2. SMTP (smtplib) — local/dev fallback, used only when RESEND_API_KEY is
    #      empty and SMTP_HOST is set.
    # If BOTH are empty the link is logged instead of emailed (dev fallback) —
    # the account/invite/reset row is still created either way.
    RESEND_API_KEY: str = ""
    RESEND_FROM: str = ""  # sender for Resend; falls back to SMTP_FROM / SMTP_USER

    # SMTP (fallback transport). STARTTLS on 587 (default); for implicit SSL use
    # port 465 with SMTP_USE_SSL=true.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = ""  # sender address; falls back to SMTP_USER when empty
    SMTP_FROM_NAME: str = "DashMet"
    SMTP_USE_TLS: bool = True   # STARTTLS (port 587)
    SMTP_USE_SSL: bool = False  # implicit SSL (port 465)

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000"

    # Environment
    ENVIRONMENT: str = "development"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",")]

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT == "production"


settings = Settings()
