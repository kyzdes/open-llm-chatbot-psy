from dataclasses import dataclass
import os

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openrouter_api_key: str
    default_model: str = "stepfun/step-3.5-flash:free"
    db_path: str = "data/freepsy.db"


def get_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set in .env")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY is not set in .env")
    return Settings(
        telegram_bot_token=token,
        openrouter_api_key=api_key,
    )


settings = get_settings()
