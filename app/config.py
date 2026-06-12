from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str
    supabase_url: str
    supabase_key: str
    razorpay_key_id: str
    razorpay_key_secret: str
    razorpay_webhook_secret: str = ""
    razorpay_plan_pro: str = ""        # Razorpay Plan ID for the ₹699 tier
    razorpay_plan_business: str = ""   # Razorpay Plan ID for the ₹1999 tier
    resend_api_key: str
    email_from: str = "onboarding@resend.dev"
    gupshup_api_key: str
    gupshup_source: str = ""    # WhatsApp sender number registered with Gupshup
    gupshup_app_name: str = ""  # Gupshup app name
    reminder_lead_hours: int = 24
    redis_url: str
    secret_key: str
    environment: str = "development"
    sentry_dsn: str = ""  # blank = error monitoring disabled (dev)
    r2_account_id: str = ""
    r2_access_key_id: str = ""
    r2_secret_access_key: str = ""
    r2_bucket: str = ""
    r2_public_base_url: str = ""  # e.g. https://pub-xxxx.r2.dev or a custom domain

    class Config:
        env_file = ".env"

settings = Settings()