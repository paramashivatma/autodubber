"""Google Sheet updater for post-publish video tracking."""
import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSHEET_AVAILABLE = True
except ImportError:
    GSHEET_AVAILABLE = False
    print("[SHEET] Warning: gspread not installed. Run: pip install gspread")

from .utils import log

# Google Sheet config
SHEET_NAME = "AutoDubQueue"
CREDENTIALS_FILE = "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly"
]


def _get_sheet_id_from_env() -> Optional[str]:
    """Get Google Sheet ID from environment."""
    return os.getenv("GOOGLE_SHEET_ID") or os.getenv("SHEET_ID")


def _parse_logs_for_data(log_buffer: List[str]) -> Dict:
    """Extract all relevant data from pipeline logs."""
    data = {
        "title": "",
        "status": "Published ✅",
        "attempts": 1,
        "youtube_url": "",
        "duration": "",
        "source_lang": "",
        "target_lang": "",
        "platforms": [],
        "post_ids": {},
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    
    log_text = "\n".join(log_buffer) if isinstance(log_buffer, list) else str(log_buffer)
    
    # Extract video title from DOWNLOAD or workspace
    download_match = re.search(r'DOWNLOAD\].*?→\s*(.+?\.mp4)', log_text, re.IGNORECASE)
    if download_match:
        data["title"] = os.path.basename(download_match.group(1).strip())
    else:
        # Try to find from workspace/source.mp4 or output.mp4
        output_match = re.search(r'(?:source|output)\.mp4|workspace[\\/]([^\s\]]+\.mp4)', log_text)
        if output_match:
            data["title"] = output_match.group(1) if output_match.group(1) else "source.mp4"
    
    # Extract source language from TRANSCRIBE
    lang_match = re.search(r'Language detected:\s*(\w{2})', log_text, re.IGNORECASE)
    if lang_match:
        data["source_lang"] = lang_match.group(1)
    
    # Extract target language from TTS Voice
    tts_match = re.search(r'Voice:\s*(\w{2})-IN-', log_text)
    if tts_match:
        data["target_lang"] = tts_match.group(1)
    elif re.search(r'gu-IN-', log_text):
        data["target_lang"] = "gu"
    elif re.search(r'ta-IN-', log_text):
        data["target_lang"] = "ta"
    
    # Extract duration from STITCH logs
    duration_match = re.search(r'(\d{2}:\d{2}:\d{2}|\d{2}:\d{2})', log_text)
    if duration_match:
        data["duration"] = duration_match.group(1)
    
    # Extract YouTube post ID and build URL
    yt_match = re.search(r'youtube\s+OK\s*-?\s*id[:\s]+(\w+)', log_text, re.IGNORECASE)
    if yt_match:
        yt_id = yt_match.group(1)
        data["post_ids"]["youtube"] = yt_id
        data["youtube_url"] = f"https://youtube.com/shorts/{yt_id}"
    
    # Extract all platform post IDs from PUBLISH OK lines
    publish_pattern = r'(\w+)\s+(?:OK|Fetched)\s*-?\s*(?:id[:\s]+)?(\w+)'
    for match in re.finditer(publish_pattern, log_text, re.IGNORECASE):
        platform = match.group(1).lower()
        post_id = match.group(2)
        if platform in ["youtube", "instagram", "tiktok", "facebook", 
                       "twitter", "threads", "bluesky", "linkedin"]:
            data["post_ids"][platform] = post_id
            if platform not in data["platforms"]:
                data["platforms"].append(platform)
    
    # Also look for PUBLISH Fetched patterns
    fetched_pattern = r'Fetched\s+(\w+)\s+account.*?(\w{8,})'
    for match in re.finditer(fetched_pattern, log_text, re.IGNORECASE):
        platform = match.group(1).lower()
        if platform not in data["platforms"]:
            data["platforms"].append(platform)
    
    return data


def _format_platforms_list(platforms: List[str]) -> str:
    """Format platforms list for column H."""
    platform_names = {
        "youtube": "YouTube",
        "instagram": "Instagram", 
        "tiktok": "TikTok",
        "facebook": "Facebook",
        "twitter": "Twitter",
        "threads": "Threads",
        "bluesky": "Bluesky",
        "linkedin": "LinkedIn",
        "reddit": "Reddit",
        "telegram": "Telegram",
        "snapchat": "Snapchat",
        "gmb": "Google Business"
    }
    formatted = [platform_names.get(p, p.title()) for p in platforms]
    return ",".join(formatted) if formatted else ""


def _format_post_ids(post_ids: Dict[str, str]) -> str:
    """Format post IDs for column I."""
    if not post_ids:
        return ""
    parts = []
    for platform, post_id in post_ids.items():
        abbrev = platform[:2] if platform != "youtube" else "yt"
        parts.append(f"{abbrev}:{post_id}")
    return ",".join(parts)


def update_video_tracker(
    log_buffer: List[str],
    sheet_id: Optional[str] = None,
    credentials_path: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Update Video Tracker Google Sheet after successful publish.
    
    Args:
        log_buffer: List of log lines from the pipeline
        sheet_id: Google Sheet ID (or from env GOOGLE_SHEET_ID)
        credentials_path: Path to service account JSON
        
    Returns:
        (success: bool, message: str)
    """
    if not GSHEET_AVAILABLE:
        return False, "gspread not installed"
    
    try:
        # Get sheet ID
        sheet_id = sheet_id or _get_sheet_id_from_env()
        if not sheet_id:
            return False, "No Google Sheet ID found (set GOOGLE_SHEET_ID)"
        
        # Get credentials path
        creds_path = credentials_path or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            CREDENTIALS_FILE
        )
        
        if not os.path.exists(creds_path):
            return False, f"Credentials file not found: {creds_path}"
        
        # Parse log data
        data = _parse_logs_for_data(log_buffer)
        
        if not data["title"]:
            return False, "Could not extract video title from logs"
        
        # Connect to Google Sheets
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        
        try:
            spreadsheet = client.open_by_key(sheet_id)
        except gspread.exceptions.SpreadsheetNotFound:
            return False, f"Sheet not found: {sheet_id}"
        
        # Get or create "Video Tracker" worksheet
        try:
            worksheet = spreadsheet.worksheet(SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            # Create worksheet with headers
            worksheet = spreadsheet.add_worksheet(SHEET_NAME, rows=1000, cols=10)
            headers = [
                "Video Title", "Status", "Attempts", "YouTube URL", "Duration",
                "Source Lang", "Target Lang", "Platforms", "Post IDs", "Timestamp"
            ]
            worksheet.append_row(headers)
            log("SHEET", f"Created '{SHEET_NAME}' worksheet with headers")
        
        # Find existing row by title
        all_values = worksheet.get_all_values()
        row_index = None
        first_empty_row = None
        
        for i, row in enumerate(all_values[1:], start=2):  # Skip header
            if row and len(row) > 0:
                # Exact match on filename (not partial)
                existing_title = row[0] if len(row) > 0 else ""
                if existing_title == data["title"]:  # Exact match only
                    row_index = i
                    # Increment attempts if updating
                    try:
                        current_attempts = int(row[2]) if len(row) > 2 and row[2] else 0
                        data["attempts"] = current_attempts + 1
                    except (ValueError, IndexError):
                        data["attempts"] = 1
                    break
                # Track first empty row (no title in column A)
                if not existing_title and first_empty_row is None:
                    first_empty_row = i
        
        # If no exact match found, use first empty row or append
        if row_index is None:
            if first_empty_row:
                row_index = first_empty_row
                log("SHEET", f"Using empty row {row_index}")
            # else: will append new row at end
        
        # Prepare row data (columns A-J)
        platforms_str = _format_platforms_list(data["platforms"])
        post_ids_str = _format_post_ids(data["post_ids"])
        
        row_data = [
            data["title"],
            data["status"],
            data["attempts"],
            data["youtube_url"],
            data["duration"],
            data["source_lang"],
            data["target_lang"],
            platforms_str,
            post_ids_str,
            data["timestamp"]
        ]
        
        if row_index:
            # Update existing row
            worksheet.update(f"A{row_index}:J{row_index}", [row_data])
            log("SHEET", f"Updated row {row_index} for '{data['title']}'")
            return True, f"Updated row {row_index}"
        else:
            # Append new row
            worksheet.append_row(row_data)
            new_row = len(all_values) + 1
            log("SHEET", f"Appended new row {new_row} for '{data['title']}'")
            return True, f"Appended row {new_row}"
            
    except Exception as e:
        error_msg = f"Sheet update failed: {str(e)}"
        log("SHEET", error_msg)
        return False, error_msg


def quick_update_from_publish_result(
    video_title: str,
    publish_results: Dict[str, Dict],
    duration: str = "",
    source_lang: str = "",
    target_lang: str = "",
    sheet_id: Optional[str] = None
) -> Tuple[bool, str]:
    """
    Quick update using publish results dict instead of log parsing.
    
    Args:
        video_title: Video filename or title
        publish_results: Dict from publisher {platform: {"post_id": "...", "url": "..."}}
        duration: Video duration string
        source_lang: Source language code
        target_lang: Target language code
        sheet_id: Optional sheet ID
    """
    if not GSHEET_AVAILABLE:
        return False, "gspread not installed"
    
    try:
        sheet_id = sheet_id or _get_sheet_id_from_env()
        if not sheet_id:
            return False, "No Google Sheet ID found"
        
        creds_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), 
            CREDENTIALS_FILE
        )
        
        if not os.path.exists(creds_path):
            return False, f"Credentials not found: {creds_path}"
        
        # Build data structure
        data = {
            "title": video_title,
            "status": "Published ✅",
            "attempts": 1,
            "youtube_url": "",
            "duration": duration,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "platforms": list(publish_results.keys()),
            "post_ids": {p: r.get("post_id", "") for p, r in publish_results.items()},
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        # Get YouTube URL specifically
        if "youtube" in publish_results:
            yt_data = publish_results["youtube"]
            data["youtube_url"] = yt_data.get("url", "")
            if not data["youtube_url"] and yt_data.get("post_id"):
                data["youtube_url"] = f"https://youtube.com/shorts/{yt_data['post_id']}"
        
        # Connect and update
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)
        
        try:
            worksheet = spreadsheet.worksheet(SHEET_NAME)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(SHEET_NAME, rows=1000, cols=10)
            headers = [
                "Video Title", "Status", "Attempts", "YouTube URL", "Duration",
                "Source Lang", "Target Lang", "Platforms", "Post IDs", "Timestamp"
            ]
            worksheet.append_row(headers)
        
        # Find existing row by title, or find first empty row, or append
        all_values = worksheet.get_all_values()
        row_index = None
        first_empty_row = None
        
        for i, row in enumerate(all_values[1:], start=2):  # Skip header
            # Check if this row matches our video title (exact match only)
            if row and len(row) > 0:
                existing_title = row[0] if len(row) > 0 else ""
                if existing_title == video_title:  # Exact match only
                    row_index = i
                    try:
                        current = int(row[2]) if len(row) > 2 and row[2] else 0
                        data["attempts"] = current + 1
                    except:
                        pass
                    break
                # Track first empty row (no title in column A)
                if not existing_title and first_empty_row is None:
                    first_empty_row = i
        
        # If no match found, use first empty row or append
        if row_index is None:
            if first_empty_row:
                row_index = first_empty_row
                log("SHEET", f"Using empty row {row_index}")
            # else: will append new row at end
        
        platforms_str = _format_platforms_list(data["platforms"])
        post_ids_str = _format_post_ids(data["post_ids"])
        
        row_data = [
            data["title"], data["status"], data["attempts"],
            data["youtube_url"], data["duration"], data["source_lang"],
            data["target_lang"], platforms_str, post_ids_str, data["timestamp"]
        ]
        
        if row_index:
            worksheet.update(f"A{row_index}:J{row_index}", [row_data])
            log("SHEET", f"Updated row {row_index}")
            return True, f"Updated row {row_index}"
        else:
            worksheet.append_row(row_data)
            new_row = len(all_values) + 1
            log("SHEET", f"Appended row {new_row}")
            return True, f"Appended row {new_row}"
            
    except Exception as e:
        error_msg = f"Quick update failed: {str(e)}"
        log("SHEET", error_msg)
        return False, error_msg
