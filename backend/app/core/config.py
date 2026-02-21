from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    ENV: str = "dev"
    APP_NAME: str = "GlucoLens API"
    API_BASE_URL: str = "http://127.0.0.1:8000"
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    DATABASE_URL: str
    REDIS_URL: str

    JWT_SECRET: str
    JWT_ACCESS_TTL_MIN: int = 15
    JWT_REFRESH_TTL_DAYS: int = 30

    CORS_ALLOW_ORIGINS: str = "http://localhost:5173"

    PAYSTACK_SECRET_KEY: str = ""
    PAYSTACK_PUBLIC_KEY: str = ""
    PAYSTACK_WEBHOOK_SECRET: str = ""

    PHARMACY_MONTHLY_KOBO: int = 700000
    PHARMACY_ANNUAL_KOBO: int = 7000000
    CLINIC_MONTHLY_KOBO: int = 1000000
    CLINIC_ANNUAL_KOBO: int = 10000000
    HOSPITAL_MONTHLY_KOBO: int = 1500000
    HOSPITAL_ANNUAL_KOBO: int = 15000000

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()