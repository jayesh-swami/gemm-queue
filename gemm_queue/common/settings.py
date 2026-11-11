from pathlib import Path
from urllib.parse import quote

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class CommonSettings(BaseSettings):
    """What every service needs: the RabbitMQ connection. Services subclass this."""

    # extra="ignore": the shared .env also holds the other services' variables.
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    rabbitmq_user: str
    rabbitmq_password: str
    rabbitmq_host: str
    rabbitmq_port: int
    rabbitmq_vhost: str = "/"

    @property
    def rabbitmq_url(self) -> str:
        user = quote(self.rabbitmq_user, safe="")
        password = quote(self.rabbitmq_password, safe="")
        vhost = quote(self.rabbitmq_vhost, safe="")
        return f"amqp://{user}:{password}@{self.rabbitmq_host}:{self.rabbitmq_port}/{vhost}"
