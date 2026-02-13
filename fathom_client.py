import time
import requests
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from config import settings
from logger import logger


class FathomClient:
    """
    Fathom API client with rate-limit awareness.
    Fathom allows 60 requests per 60-second window.
    We track request timestamps and throttle automatically.
    """

    def __init__(self):
        self.base_url = settings.FATHOM_API_URL
        self.headers = {
            "X-Api-Key": settings.FATHOM_API_KEY,
            "Content-Type": "application/json",
            "User-Agent": "FathomSync/1.0",
        }
        self._request_times: list[float] = []

    def _throttle(self):
        """
        Enforce rate limit: max 50 requests per 60s window (10-req safety margin).
        If we're close to the limit, sleep until the oldest request expires.
        """
        now = time.time()
        window = 60.0
        max_requests = 50  # generous safety margin below the 60 hard limit

        # Prune requests older than the window
        self._request_times = [t for t in self._request_times if now - t < window]

        if len(self._request_times) >= max_requests:
            oldest = self._request_times[0]
            sleep_for = window - (now - oldest) + 2.0  # +2s safety
            if sleep_for > 0:
                logger.info(f"Rate limit throttle: sleeping {sleep_for:.1f}s")
                time.sleep(sleep_for)
                # Prune again after sleeping
                now = time.time()
                self._request_times = [t for t in self._request_times if now - t < window]

        self._request_times.append(time.time())

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def _fetch_page(self, params: dict) -> dict:
        """
        Fetch a single page of meetings. Retry is per-page, not per-full-pagination.
        Handles 429 rate limit responses by sleeping before retry.
        """
        self._throttle()
        response = requests.get(
            f"{self.base_url}/meetings",
            headers=self.headers,
            params=params,
        )

        # If we hit a 429, sleep 60s before tenacity retries
        if response.status_code == 429:
            logger.warning("Hit 429 rate limit. Sleeping 65s before retry...")
            time.sleep(65)
            response.raise_for_status()

        response.raise_for_status()
        return response.json()

    def list_meetings(self, limit: int = 100) -> list:
        """
        Fetch all meetings with cursor-based pagination.
        Retry logic is on each individual page fetch (not the whole loop).
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
            logger.info(f"Fetching meetings page {page} (cursor={'...' + cursor[-20:] if cursor else 'None'})")

            try:
                data = self._fetch_page(params)
            except Exception as e:
                logger.error(f"Failed to fetch page {page} after retries: {e}")
                logger.info(f"Returning {len(all_meetings)} meetings fetched so far from {page - 1} pages")
                break

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

        logger.info(f"Fetched {len(all_meetings)} total meetings across {page} pages")
        return all_meetings

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=5, max=30),
        retry=retry_if_exception_type(requests.RequestException),
    )
    def get_transcript(self, recording_id: str) -> dict | None:
        """
        Fetch transcript for a recording.
        Returns: {"transcript": [{"speaker": {...}, "text": "...", "timestamp": "HH:MM:SS"}, ...]}
        """
        url = f"{self.base_url}/recordings/{recording_id}/transcript"
        logger.info(f"Fetching transcript for recording {recording_id}")

        self._throttle()
        response = requests.get(url, headers=self.headers)

        # Handle 429 explicitly
        if response.status_code == 429:
            logger.warning(f"Hit 429 on transcript {recording_id}. Sleeping 65s before retry...")
            time.sleep(65)
            response.raise_for_status()

        response.raise_for_status()
        return response.json()


fathom_client = FathomClient()
