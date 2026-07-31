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

    # Encryption (for platform tokens at rest)
    ENCRYPTION_KEY: str

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
