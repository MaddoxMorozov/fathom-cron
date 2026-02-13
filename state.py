import json
import os
from config import settings
from logger import logger


class StateManager:
    """Tracks which recording_ids have been processed via a JSON file."""

    def __init__(self):
        self.state_file = settings.STATE_FILE
        self.processed: dict = self._load()

    def _load(self) -> dict:
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load state file: {e}")
        return {}

    def _save(self):
        try:
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump(self.processed, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save state file: {e}")

    def is_processed(self, recording_id: str) -> bool:
        return str(recording_id) in self.processed

    def mark_processed(self, recording_id: str, drive_file_id: str, synced_at: str):
        self.processed[str(recording_id)] = {
            "drive_file_id": drive_file_id,
            "synced_at": synced_at,
        }
        self._save()

    def get_processed_count(self) -> int:
        return len(self.processed)


state_manager = StateManager()
