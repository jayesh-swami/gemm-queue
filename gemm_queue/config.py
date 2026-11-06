from pathlib import Path
from urllib.parse import quote
from sqlalchemy import URL
from pydantic_settings import BaseSettings, SettingsConfigDict                                                                                                  

ROOT = Path(__file__).resolve().parent.parent                                                     

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env")

    # PostgreSQL
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int

    # RabbitMQ
    rabbitmq_user: str
    rabbitmq_password: str
    rabbitmq_host: str
    rabbitmq_port: int

    # API
    api_key: str

    @property
    def rabbitmq_url(self) -> str:
        user = quote(self.rabbitmq_user, safe="")
        password = quote(self.rabbitmq_password, safe="")
        return f"amqp://{user}:{password}@{self.rabbitmq_host}:{self.rabbitmq_port}/"

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )
    

settings = Settings()
