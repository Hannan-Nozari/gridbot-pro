import os
from pathlib import Path
from typing import List


class Settings:
    """Application settings loaded from environment variables."""

    def __init__(self) -> None:
        self.DATABASE_PATH: str = os.getenv(
            "DATABASE_PATH", "./data/trading.db"
        )
        self.AUTH_PASSWORD: str = os.getenv("AUTH_PASSWORD", "admin")

        # Binance
        self.BINANCE_API_KEY: str = os.getenv("BINANCE_API_KEY", "")
        self.BINANCE_API_SECRET: str = os.getenv("BINANCE_API_SECRET", "")

        # Alert - Email
        self.ALERT_EMAIL_ENABLED: bool = (
            os.getenv("ALERT_EMAIL_ENABLED", "false").lower() == "true"
        )
        self.ALERT_EMAIL_SMTP_HOST: str = os.getenv(
            "ALERT_EMAIL_SMTP_HOST", ""
        )
        self.ALERT_EMAIL_SMTP_PORT: int = int(
            os.getenv("ALERT_EMAIL_SMTP_PORT", "587")
        )
        self.ALERT_EMAIL_USERNAME: str = os.getenv(
            "ALERT_EMAIL_USERNAME", ""
        )
        self.ALERT_EMAIL_PASSWORD: str = os.getenv(
            "ALERT_EMAIL_PASSWORD", ""
        )
        self.ALERT_EMAIL_FROM: str = os.getenv("ALERT_EMAIL_FROM", "")
        self.ALERT_EMAIL_TO: str = os.getenv("ALERT_EMAIL_TO", "")

        # Alert - Telegram
        self.ALERT_TELEGRAM_ENABLED: bool = (
            os.getenv("ALERT_TELEGRAM_ENABLED", "false").lower() == "true"
        )
        self.ALERT_TELEGRAM_BOT_TOKEN: str = os.getenv(
            "ALERT_TELEGRAM_BOT_TOKEN", ""
        )
        self.ALERT_TELEGRAM_CHAT_ID: str = os.getenv(
            "ALERT_TELEGRAM_CHAT_ID", ""
        )

        # CORS
        self.CORS_ORIGINS: List[str] = [
            origin.strip()
            for origin in os.getenv(
                "CORS_ORIGINS", "http://localhost:3000,http://localhost:5173"
            ).split(",")
            if origin.strip()
        ]

    @property
    def database_dir(self) -> Path:
        return Path(self.DATABASE_PATH).parent


settings = Settings()
