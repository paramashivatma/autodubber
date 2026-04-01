"""Google Sheet updater for post-publish video tracking."""
import os
import re
import json
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from .config import get_sheet_id, get_credentials_file

try:
    import gspread
    from google.oauth2.service_account import Credentials
    GSHEET_AVAILABLE = True
except ImportError:
    GSHEET_AVAILABLE = False
    print("[SHEET] Warning: gspread not installed. Run: pip install gspread")

from .utils import log, PLATFORM_LIMITS, SHORT_MINIMUMS, REQUIRED_PLATFORMS

# Language code to full name mapping
LANGUAGE_CODES_TO_NAMES = {
    "en": "English",
    "hi": "Hindi", 
    "gu": "Gujarati",
    "ta": "Tamil",
    "te": "Telugu",
    "kn": "Kannada",
    "ml": "Malayalam",
    "bn": "Bengali"
}

def _get_full_language_name(lang_code: str) -> str:
    """Convert language code to full language name."""
    return LANGUAGE_CODES_TO_NAMES.get(lang_code, lang_code)

# Google Sheet config
SHEET_NAME = "AutoDubQueue"
CREDENTIALS_FILE = "credentials.json"
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly"
]


def _get_sheet_id_from_env() -> Optional[str]:
    """Get Google Sheet ID from environment."""
    return get_sheet_id()


def _parse_logs_for_data(log_buffer: List[str]) -> Dict:
    """Extract all relevant data from pipeline logs."""
    data = {
        "title": "",
        "status": "Published ✅",
        "attempts": 1,
        "format": "",
        "duration": "",
        "source_lang": "",
        "target_lang": "",
        "platforms": [],
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
    
    # Extract YouTube presence and set format
    yt_match = re.search(r'youtube\s+OK\s*-?\s*id[:\s]+(\w+)', log_text, re.IGNORECASE)
    if yt_match:
        # Set format to video since we have YouTube content
        data["format"] = "video"
        data["platforms"].append("youtube")
    
    # Extract all platforms from PUBLISH OK lines
    publish_pattern = r'(\w+)\s+(?:OK|Fetched)\s*-?\s*(?:id[:\s]+)?(\w+)'
    for match in re.finditer(publish_pattern, log_text, re.IGNORECASE):
        platform = match.group(1).lower()
        if platform in ["youtube", "instagram", "tiktok", "facebook", 
                       "twitter", "threads", "bluesky", "linkedin"]:
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

def _format_post_ids(publish_results: Dict[str, Dict]) -> str:
    """Build a comma-separated list of platform:post_id values."""
    parts = []
    if not isinstance(publish_results, dict):
        return ""
    for platform, result in publish_results.items():
        if isinstance(result, dict):
            post_id = result.get("post_id") or result.get("_id") or result.get("id")
            if post_id:
                parts.append(f"{platform}:{post_id}")
    return ",".join(parts)

def _is_success_result(result) -> bool:
    if isinstance(result, bool):
        return result
    if not isinstance(result, dict):
        return False
    if "error" in result:
        return False
    return str(result.get("status", "")).lower() in {
        "ok", "published", "success", "submitted", "queued", "processing"
    }

def _is_unconfirmed_result(result) -> bool:
    if not isinstance(result, dict):
        return False
    return str(result.get("status", "")).lower() in {
        "unconfirmed", "submitted_unconfirmed", "timeout-unconfirmed"
    }




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
        if credentials_path:
            creds_path = credentials_path
        else:
            configured_file = get_credentials_file(CREDENTIALS_FILE)
            if os.path.isabs(configured_file):
                creds_path = configured_file
            else:
                creds_path = os.path.join(
                    os.path.dirname(os.path.dirname(__file__)),
                    configured_file
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
            # Check if headers need updating (old "YouTube URL" -> new "Format")
            existing_headers = worksheet.row_values(1)
            if len(existing_headers) >= 4 and existing_headers[3] == "YouTube URL":
                # Update headers to new format
                new_headers = [
                    "Video Title", "Status", "Attempts", "Format", "Duration",
                    "Source Lang", "Target Lang", "Platforms", "Post IDs", "Timestamp"
                ]
                worksheet.update("A1:J1", [new_headers])
                log("SHEET", "Updated headers from 'YouTube URL' to 'Format'")
        except gspread.exceptions.WorksheetNotFound:
            # Create worksheet with headers
            worksheet = spreadsheet.add_worksheet(SHEET_NAME, rows=1000, cols=10)
            headers = [
                "Video Title", "Status", "Attempts", "Format", "Duration",
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
        
        row_data = [
            data["title"],
            data["status"],
            data["attempts"],
            data["format"],
            data["duration"],
            _get_full_language_name(data["source_lang"]),
            _get_full_language_name(data["target_lang"]),
            platforms_str,
            "",
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
    content_format: str = "video",  # "video" or "image"
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
        content_format: Content type - "video" or "image"
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
        successful_results = {
            platform: result
            for platform, result in (publish_results or {}).items()
            if _is_success_result(result)
        }
        unconfirmed_results = {
            platform: result
            for platform, result in (publish_results or {}).items()
            if _is_unconfirmed_result(result)
        }
        failed_count = max(
            0,
            len((publish_results or {}).keys()) - len(successful_results.keys()) - len(unconfirmed_results.keys())
        )

        if successful_results and failed_count == 0 and not unconfirmed_results:
            status_text = "Published ✅"
        elif successful_results and (failed_count > 0 or unconfirmed_results):
            status_text = "Partial ⚠️"
        elif unconfirmed_results and failed_count == 0:
            status_text = "Unconfirmed ⏳"
        elif unconfirmed_results and failed_count > 0:
            status_text = "Partial ⚠️"
        else:
            status_text = "Failed ❌"

        raw_format = str(content_format or "").strip().lower()
        if raw_format in ("", "video"):
            format_label = ""
        elif raw_format == "image":
            format_label = "Image"
        else:
            format_label = str(content_format or "").strip()

        data = {
            "title": video_title,
            "status": status_text,
            "attempts": 1,
            "format": format_label,  # "Video" or "Image"
            "duration": duration,
            "source_lang": source_lang,
            "target_lang": target_lang,
            "platforms": [
                p for p in (publish_results or {}).keys()
                if p in successful_results or p in unconfirmed_results
            ],
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        # Format will be set by the calling function based on content type
        
        # Connect and update
        creds = Credentials.from_service_account_file(creds_path, scopes=SCOPES)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)
        
        try:
            worksheet = spreadsheet.worksheet(SHEET_NAME)
            # Check if headers need updating (old "YouTube URL" -> new "Format")
            existing_headers = worksheet.row_values(1)
            if len(existing_headers) >= 4 and existing_headers[3] == "YouTube URL":
                # Update headers to new format
                new_headers = [
                    "Video Title", "Status", "Attempts", "Format", "Duration",
                    "Source Lang", "Target Lang", "Platforms", "Post IDs", "Timestamp"
                ]
                worksheet.update("A1:J1", [new_headers])
                log("SHEET", "Updated headers from 'YouTube URL' to 'Format'")
        except gspread.exceptions.WorksheetNotFound:
            worksheet = spreadsheet.add_worksheet(SHEET_NAME, rows=1000, cols=10)
            headers = [
                "Video Title", "Status", "Attempts", "Format", "Duration",
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
        post_ids_payload = dict(successful_results)
        for platform, result in unconfirmed_results.items():
            if platform not in post_ids_payload:
                pid = ""
                if isinstance(result, dict):
                    pid = result.get("post_id") or result.get("_id") or result.get("id") or "unconfirmed"
                post_ids_payload[platform] = {"post_id": f"{pid} (unconfirmed)"}
        post_ids_str = _format_post_ids(post_ids_payload)
        
        row_data = [
            data["title"], data["status"], data["attempts"],
            data["format"], data["duration"], _get_full_language_name(data["source_lang"]),
            _get_full_language_name(data["target_lang"]), platforms_str, post_ids_str, data["timestamp"]
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
