import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    database_url: str
    checker_interval_secs: int = 30
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        bot_token = os.environ["BOT_TOKEN"]
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            host = os.environ.get("POSTGRES_HOST", "postgres")
            port = os.environ.get("POSTGRES_PORT", "5432")
            db = os.environ.get("POSTGRES_DB", "gz_checker")
            user = os.environ.get("POSTGRES_USER", "gz_checker")
            password = os.environ.get("POSTGRES_PASSWORD", "gz_checker")
            database_url = f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"
        return cls(
            bot_token=bot_token,
            database_url=database_url,
            checker_interval_secs=int(os.environ.get("CHECKER_INTERVAL_SECS", "30")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
