from pydantic_settings import BaseSettings
import os

# Determine the root directory of the project
# This assumes the script is in backend/utils, so we go up two levels
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Correct path to the .env file
ENV_FILE_PATH = os.path.join(ROOT_DIR, '.env')

class Settings(BaseSettings):
    """
    Manages application settings and environment variables.
    """
    openai_api_key: str
    pdfco_api_key: str
    railway_static_url: str = ""
    cors_origins: str = "http://localhost:8501,http://localhost:3000"

    class Config:
        # Load the .env file from the project's root directory
        env_file = ENV_FILE_PATH

settings = Settings()