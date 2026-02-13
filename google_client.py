import os
import io
from google.auth.transport.requests import Request
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
        Lazy init with OAuth2 user credentials.
        - First run: opens browser for Google login, saves token.json
        - Subsequent runs: loads token.json, auto-refreshes if expired
        """
        if self._credentials is not None and self._credentials.valid:
            return

        creds = None

        # Load saved token if it exists
        if os.path.exists(_TOKEN_PATH):
            creds = Credentials.from_authorized_user_file(_TOKEN_PATH, SCOPES)

        # If no valid credentials, refresh or run the interactive browser flow
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("Refreshing expired Google OAuth token...")
                creds.refresh(Request())
            else:
                if not os.path.exists(_CREDENTIALS_PATH):
                    raise FileNotFoundError(
                        f"OAuth credentials file not found at: {_CREDENTIALS_PATH}\n"
                        f"Download it from Google Cloud Console:\n"
                        f"  1. Go to https://console.cloud.google.com/apis/credentials\n"
                        f"  2. Create Credentials > OAuth client ID > Desktop app\n"
                        f"  3. Download JSON and save as: {_CREDENTIALS_PATH}"
                    )
                logger.info("No saved token found. Opening browser for Google authorization...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    _CREDENTIALS_PATH, SCOPES
                )
                creds = flow.run_local_server(port=0)

            # Save the token for future runs
            with open(_TOKEN_PATH, "w") as token_file:
                token_file.write(creds.to_json())
            logger.info(f"Google OAuth token saved to {_TOKEN_PATH}")

        self._credentials = creds
        self._drive_service = build("drive", "v3", credentials=self._credentials)
        self._sheets_service = build("sheets", "v4", credentials=self._credentials)
        logger.info("Google client initialized (OAuth2 user credentials)")

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
