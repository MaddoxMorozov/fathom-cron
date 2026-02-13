import time
import requests
from datetime import datetime
from tenacity import RetryError
from fathom_client import fathom_client
from google_client import google_client
from state import state_manager
from logger import logger


def format_transcript(title: str, meeting: dict, transcript_data: dict) -> str:
    """
    Format a Fathom transcript into a readable .txt string.
    """
    start_time = meeting.get("recording_start_time") or meeting.get("created_at") or ""
    end_time = meeting.get("recording_end_time") or ""

    # Build participant list from calendar_invitees
    participants = []
    for invitee in meeting.get("calendar_invitees") or []:
        name = invitee.get("name") or invitee.get("email") or "Unknown"
        participants.append(name)

    # Header
    lines = [
        "=" * 50,
        f"Meeting: {title}",
        f"Date: {start_time}",
    ]
    if start_time and end_time:
        lines.append(f"Recording: {start_time} to {end_time}")
    if participants:
        lines.append(f"Participants: {', '.join(participants)}")
    lines.append("=" * 50)
    lines.append("")

    # Transcript body
    if transcript_data and "transcript" in transcript_data:
        for entry in transcript_data["transcript"]:
            speaker = entry.get("speaker", {}).get("display_name", "Unknown")
            text = entry.get("text", "")
            timestamp = entry.get("timestamp", "")
            lines.append(f"[{timestamp}] {speaker}: {text}")
    else:
        lines.append("[No transcript content available]")

    lines.append("")
    return "\n".join(lines)


def extract_call_date(meeting: dict) -> str:
    """
    Extract the call date/time formatted as 'YYYY-MM-DD HH:MM' for the sheet.
    Priority: recording_start_time > scheduled_start_time > created_at.
    """
    raw = (
        meeting.get("recording_start_time")
        or meeting.get("scheduled_start_time")
        or meeting.get("created_at")
        or ""
    )
    if not raw:
        return datetime.now().strftime("%Y-%m-%d %H:%M")

    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt.strftime("%d %b %Y, %I:%M %p")
    except (ValueError, AttributeError):
        return raw


def make_filename(recording_id, title: str) -> str:
    """Create a safe filename: '118794290_unga_bunga.txt'."""
    safe = "".join(c if c.isalnum() or c == " " else "" for c in title).strip()
    safe = safe.replace(" ", "_")
    if not safe:
        safe = "untitled"
    return f"{recording_id}_{safe}.txt"


def run_sync():
    """
    Main sync flow:
    1. List all meetings from Fathom
    2. For each unprocessed meeting:
       a. Fetch transcript
       b. Format as text
       c. Upload .txt to Google Drive
       d. Append [date, drive_link] row to Google Sheet
       e. Mark as processed
    """
    logger.info("=" * 40)
    logger.info("Starting sync cycle")
    logger.info("=" * 40)

    stats = {"new": 0, "skipped": 0, "errors": 0}

    try:
        meetings = fathom_client.list_meetings()
    except Exception as e:
        logger.error(f"Failed to fetch meetings from Fathom: {e}")
        return stats

    if not meetings:
        logger.info("No meetings found.")
        return stats

    logger.info(
        f"Found {len(meetings)} total meetings, "
        f"{state_manager.get_processed_count()} already processed"
    )

    for meeting in meetings:
        recording_id = str(meeting.get("recording_id", ""))
        if not recording_id:
            logger.warning(f"Meeting has no recording_id, skipping: {meeting.get('title')}")
            continue

        if state_manager.is_processed(recording_id):
            stats["skipped"] += 1
            continue

        title = meeting.get("title") or meeting.get("meeting_title") or "Untitled Meeting"
        logger.info(f"Processing: '{title}' (recording_id={recording_id})")

        try:
            # Fetch transcript — handle HTTP errors for old/unavailable recordings
            try:
                transcript_data = fathom_client.get_transcript(recording_id)
            except RetryError:
                logger.warning(
                    f"Transcript unavailable for '{title}' ({recording_id}). "
                    f"Skipping — recording may be too old or deleted."
                )
                # Mark as processed so we don't retry forever
                state_manager.mark_processed(
                    recording_id,
                    drive_file_id="N/A",
                    synced_at=datetime.now().isoformat(),
                )
                stats["errors"] += 1
                continue
            except requests.HTTPError as e:
                logger.warning(
                    f"HTTP {e.response.status_code} for transcript '{title}' ({recording_id}). Skipping."
                )
                state_manager.mark_processed(
                    recording_id,
                    drive_file_id="N/A",
                    synced_at=datetime.now().isoformat(),
                )
                stats["errors"] += 1
                continue

            has_content = (
                transcript_data
                and "transcript" in transcript_data
                and len(transcript_data["transcript"]) > 0
            )
            if not has_content:
                logger.warning(
                    f"No transcript content for '{title}' ({recording_id}). "
                    f"Skipping — may not be ready yet."
                )
                stats["errors"] += 1
                continue

            # Format transcript text
            text_content = format_transcript(title, meeting, transcript_data)
            filename = make_filename(recording_id, title)

            # Upload to Google Drive
            drive_file = google_client.upload_transcript_to_drive(filename, text_content)
            drive_link = drive_file.get("webViewLink", "")
            drive_file_id = drive_file.get("id", "")

            if not drive_link:
                logger.warning(
                    f"Drive upload succeeded but no webViewLink for {recording_id}"
                )

            # Extract call date for sheet
            call_date = extract_call_date(meeting)

            # Append row to Google Sheet
            google_client.append_to_sheet(call_date, drive_link)

            # Mark as processed
            state_manager.mark_processed(
                recording_id,
                drive_file_id=drive_file_id,
                synced_at=datetime.now().isoformat(),
            )

            stats["new"] += 1
            logger.info(f"Synced '{title}' -> {drive_link}")

            # Brief pause to respect rate limits
            time.sleep(0.5)

        except Exception as e:
            logger.error(f"Error processing '{title}' ({recording_id}): {e}")
            stats["errors"] += 1
            continue

    logger.info(f"Sync cycle complete. Stats: {stats}")
    return stats
