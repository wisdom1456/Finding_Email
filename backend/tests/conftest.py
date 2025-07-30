import pytest
from pydantic_settings import BaseSettings
from typing import Optional

class TestSettings(BaseSettings):
    openai_api_key: str = "test_key"
    pdfco_api_key: str = "test_key"
    cors_origins: str = "*"
    railway_static_url: Optional[str] = None

@pytest.fixture
def test_settings():
    return TestSettings()
