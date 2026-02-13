import time
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config import settings
from logger import logger


class FathomClient:
    def __init__(self):
        self.base_url = settings.FATHOM_API_URL
        self.headers = {
            "X-Api-Key": settings.FATHOM_API_KEY,
            "Content-Type": "application/json",
            "User-Agent": "FathomSync/1.0",
        }

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def list_meetings(self, limit: int = 100) -> list:
        """
        Fetch all meetings with cursor-based pagination.
        Fathom rate limit: 60 requests per 60s window.
        """
        all_meetings = []
        cursor = None
        page = 0

        while True:
            params = {
                "limit": limit,
                "calendar_invitees_domains_type": "all",
            }
            if cursor:
                params["cursor"] = cursor

            page += 1
            logger.info(f"Fetching meetings page {page} (cursor={cursor})")

            response = requests.get(
                f"{self.base_url}/meetings",
                headers=self.headers,
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                meetings = data
            elif isinstance(data, dict):
                meetings = (
                    data.get("meetings")
                    or data.get("items")
                    or data.get("recordings")
                    or []
                )
            else:
                meetings = []

            all_meetings.extend(meetings)

            # Check for next page
            next_cursor = data.get("next_cursor") if isinstance(data, dict) else None
            if not next_cursor or not meetings:
                break
            cursor = next_cursor

            # Respect rate limit
            time.sleep(1.0)

        logger.info(f"Fetched {len(all_meetings)} total meetings")
        return all_meetings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def get_transcript(self, recording_id: str) -> dict | None:
        """
        Fetch transcript for a recording.
        Returns: {"transcript": [{"speaker": {...}, "text": "...", "timestamp": "HH:MM:SS"}, ...]}
        """
        url = f"{self.base_url}/recordings/{recording_id}/transcript"
        logger.info(f"Fetching transcript for recording {recording_id}")

        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()


fathom_client = FathomClient()
