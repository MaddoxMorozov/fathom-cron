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
_TOKEN_PATH = os.path.join(_BASE_DIR, "token.json")
_CREDENTIALS_PATH = os.path.join(_BASE_DIR, "credentials.json")


class GoogleClient:
    def __init__(self):
        self._credentials = None
        self._drive_service = None
        self._sheets_service = None

    def _ensure_initialized(self):
        """
        Initialize Google credentials.
        Priority:
        1. Service Account (if GOOGLE_SERVICE_ACCOUNT_FILE is set and valid)
        2. OAuth2 User Credentials (token.json or interactive flow)
        """
        if self._credentials is not None and self._credentials.valid:
            return

        creds = None

        # 1. Try Service Account
        sa_path = settings.resolve_service_account_path()
        if os.path.exists(sa_path):
            try:
                logger.info(f"Loading Service Account credentials from: {sa_path}")
                creds = service_account.Credentials.from_service_account_file(
                    sa_path, scopes=SCOPES
                )
            except Exception as e:
                logger.error(f"Failed to load service account: {e}")

        # 2. Try User Credentials (token.json)
        if not creds and os.path.exists(_TOKEN_PATH):
            try:
                creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)
            except Exception as e:
                logger.warning(f"Failed to load token.json: {e}")

        # 3. Interactive Flow (Local only provided credentials.json exists)
        if not creds:
            if os.path.exists(_CREDENTIALS_PATH):
                logger.info("No service account or token found. Starting interactive flow...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    _CREDENTIALS_PATH, SCOPES
                )
                creds = flow.run_local_server(port=0)
                # Save the token
                with open(_TOKEN_PATH, "w") as token_file:
                    token_file.write(creds.to_json())
            else:
                # If we are here, we have no valid creds and no means to get them
                msg = "No valid Google credentials found (Service Account or OAuth)."
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
