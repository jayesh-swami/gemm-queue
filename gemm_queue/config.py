from pathlib import Path                                                                             
from sqlalchemy import URL
from pydantic_settings import BaseSettings, SettingsConfigDict                                                                                                  

ROOT = Path(__file__).resolve().parent.parent                                                     

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env")

    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str
    postgres_port: int

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
