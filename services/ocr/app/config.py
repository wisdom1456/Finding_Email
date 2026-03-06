from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Raw JSON string (not base64). Injected by Secret Manager.
    google_credentials_json: str = Field(
        ..., alias="GOOGLE_CREDENTIALS_JSON"
    )
    max_pages: int = Field(25, alias="OCR_MAX_PAGES")
    max_request_bytes: int = Field(
        100 * 1024 * 1024, alias="OCR_MAX_REQUEST_BYTES"
    )
    max_image_bytes: int = Field(
        40 * 1024 * 1024, alias="OCR_MAX_IMAGE_BYTES"
    )
    page_render_dpi: int = Field(200, alias="OCR_PAGE_RENDER_DPI")
    vision_timeout_seconds: float = Field(
        30.0, alias="OCR_VISION_TIMEOUT"
    )
    service_token: str = Field(..., alias="OCR_SERVICE_TOKEN")
    log_level: str = Field("INFO", alias="LOG_LEVEL")

    model_config = SettingsConfigDict(env_file=".env")
