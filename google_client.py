import os
import io
from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
from config import settings
from logger import logger

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

# Paths relative to this script's directory
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CREDENTIALS_PATH = os.path.join(_BASE_DIR, "credentials.json")

# Token search paths: local first, then Render secret file location
_TOKEN_SEARCH_PATHS = [
    os.path.join(_BASE_DIR, "token.json"),
    "/etc/secrets/token.json",
]


def _find_token_path() -> str | None:
    """Return the first existing token.json path, or None."""
    for p in _TOKEN_SEARCH_PATHS:
        if os.path.exists(p):
            return p
    return None


class GoogleClient:
    def __init__(self):
        self._credentials = None
        self._drive_service = None
        self._sheets_service = None

    def _ensure_initialized(self):
        """
        Initialize Google credentials.
        Priority (OAuth2 FIRST — service accounts can't upload to Drive):
        1. OAuth2 User Credentials (token.json — works for Drive + Sheets)
        2. Interactive OAuth flow (credentials.json — first-time local setup)
        3. Service Account (ONLY if no OAuth available — Sheets only, Drive will fail)
        """
        if self._credentials is not None and self._credentials.valid:
            return

        creds = None
        token_path = _find_token_path()

        # 1. Try OAuth2 token.json first (works for both Drive and Sheets)
        if token_path:
            try:
                logger.info(f"Loading OAuth2 token from: {token_path}")
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
                if creds and creds.expired and creds.refresh_token:
                    logger.info("Refreshing expired OAuth token...")
                    creds.refresh(Request())
                    # Save refreshed token (only if writable — Render /etc/secrets is read-only)
                    try:
                        with open(token_path, "w") as f:
                            f.write(creds.to_json())
                    except OSError:
                        logger.info("Token path is read-only, skipping save (normal on Render)")
                if creds and creds.valid:
                    logger.info("Loaded OAuth2 user credentials successfully")
            except Exception as e:
                logger.warning(f"Failed to load/refresh token.json: {e}")
                creds = None

        # 2. Try interactive OAuth flow (local machine with browser)
        if not creds and os.path.exists(_CREDENTIALS_PATH):
            try:
                logger.info("Starting interactive OAuth flow (browser)...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    _CREDENTIALS_PATH, SCOPES
                )
                creds = flow.run_local_server(port=0)
                local_token = os.path.join(_BASE_DIR, "token.json")
                with open(local_token, "w") as f:
                    f.write(creds.to_json())
                logger.info(f"OAuth token saved to {local_token}")
            except Exception as e:
                logger.warning(f"Interactive OAuth flow failed: {e}")
                creds = None

        # 3. Fallback: Service Account (Sheets works, Drive uploads will fail)
        if not creds:
            sa_path = settings.resolve_service_account_path()
            if os.path.exists(sa_path):
                try:
                    logger.warning(
                        "Using Service Account — Drive uploads will fail (no storage quota). "
                        "Generate token.json locally and deploy it for full functionality."
                    )
                    creds = service_account.Credentials.from_service_account_file(
                        sa_path, scopes=SCOPES
                    )
                except Exception as e:
                    logger.error(f"Failed to load service account: {e}")

        if not creds:
            msg = (
                "No valid Google credentials found.\n"
                "Options:\n"
                "  1. Run locally with credentials.json to generate token.json\n"
                "  2. Copy token.json to the deployment\n"
                "  3. Place service_account.json (Sheets only, no Drive uploads)"
            )
            logger.error(msg)
            raise RuntimeError(msg)

        self._credentials = creds
        self._drive_service = build("drive", "v3", credentials=self._credentials)
        self._sheets_service = build("sheets", "v4", credentials=self._credentials)
        logger.info("Google client initialized successfully.")

    def upload_transcript_to_drive(
        self, filename: str, content: str, folder_id: str | None = None
    ) -> dict:
        """
        Upload a .txt file to Google Drive.
        Returns file metadata dict with 'id' and 'webViewLink'.
        """
        self._ensure_initialized()
        folder_id = folder_id or settings.GOOGLE_DRIVE_FOLDER_ID

        file_metadata = {
            "name": filename,
            "parents": [folder_id],
            "mimeType": "text/plain",
        }

        media = MediaIoBaseUpload(
            io.BytesIO(content.encode("utf-8")),
            mimetype="text/plain",
            resumable=False,
        )

        file = (
            self._drive_service.files()
            .create(
                body=file_metadata,
                media_body=media,
                fields="id, webViewLink, name",
            )
            .execute()
        )

        logger.info(f"Uploaded '{filename}' to Drive. ID: {file['id']}")
        return file

    def append_to_sheet(self, date_str: str, content_link: str) -> dict:
        """
        Append a row [date, content_link] to the Google Sheet.
        """
        self._ensure_initialized()
        body = {"values": [[date_str, content_link]]}

        result = (
            self._sheets_service.spreadsheets()
            .values()
            .append(
                spreadsheetId=settings.GOOGLE_SHEET_ID,
                range=settings.GOOGLE_SHEET_RANGE,
                valueInputOption="USER_ENTERED",
                insertDataOption="INSERT_ROWS",
                body=body,
            )
            .execute()
        )

        logger.info(f"Appended row to sheet: date={date_str}, link={content_link}")
        return result


google_client = GoogleClient()
