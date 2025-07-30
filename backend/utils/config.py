from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """
    Manages application settings and environment variables.
    """
    openai_api_key: str
    pdfco_api_key: str
    railway_static_url: str = ""
    cors_origins: str = "http://localhost:8501,http://localhost:3000"

    class Config:
        env_file = ".env"

import os

if os.getenv("TESTING"):
    from tests.conftest import TestSettings
    settings = TestSettings()
else:
    settings = Settings()