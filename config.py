import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


# Resolve paths relative to this file's directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Settings(BaseSettings):
    # Fathom API
    FATHOM_API_KEY: str = Field(..., description="Fathom API key")
    FATHOM_API_URL: str = "https://api.fathom.ai/external/v1"

    # Google Service Account (optional — used if file exists)
    GOOGLE_SERVICE_ACCOUNT_FILE: str = "service_account.json"

    # Google Drive
    GOOGLE_DRIVE_FOLDER_ID: str = "14ettD6eiSSWcPUigY9z_GtltB4MlChiH"

    # Google Sheets
    GOOGLE_SHEET_ID: str = "1RU4LaFKIxIWPzcFzCABf54wzmhoHvf16R1t8WhRYbY0"
    GOOGLE_SHEET_RANGE: str = "Sheet1!A:B"

    # Scheduler
    SYNC_INTERVAL_MINUTES: int = 30

    # Local state
    STATE_FILE: str = os.path.join(BASE_DIR, "data", "state.json")

    model_config = SettingsConfigDict(
        env_file=os.path.join(BASE_DIR, ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def ensure_dirs(self):
        os.makedirs(os.path.dirname(self.STATE_FILE), exist_ok=True)
        os.makedirs(os.path.join(BASE_DIR, "logs"), exist_ok=True)

    def resolve_service_account_path(self) -> str:
        """Return absolute path to service account file."""
        path = self.GOOGLE_SERVICE_ACCOUNT_FILE
        if not os.path.isabs(path):
            path = os.path.join(BASE_DIR, path)
        return path


settings = Settings()
settings.ensure_dirs()
