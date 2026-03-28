import os, json, time, sys
import gspread
from google.oauth2.service_account import Credentials
from dotenv import load_dotenv
from dubber.utils import log
from dubber.publisher import publish_to_platforms

# Load environment
load_dotenv()

# Configuration from .env
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
SEMI_AUTO_PUBLISH = os.getenv("SEMI_AUTO_PUBLISH", "false").lower() == "true"
DAILY_LOG_DIR = os.getenv("DAILY_LOG_DIR", "logs")

def _get_sheet_client():
    """Initialize Google Sheets client"""
    try:
        creds = Credentials.from_service_account_file(
            GOOGLE_SERVICE_ACCOUNT_JSON,
            scopes=['https://www.googleapis.com/auth/spreadsheets']
        )
        client = gspread.authorize(creds)
        return client
    except Exception as e:
        log("PUBLISH", f"  Google Sheets auth failed: {e}")
        return None

def _setup_daily_log():
    """Setup daily publish log file"""
    os.makedirs(DAILY_LOG_DIR, exist_ok=True)
    log_file = os.path.join(DAILY_LOG_DIR, time.strftime("publish_%Y-%m-%d.txt"))
    return log_file

def _log(message, log_file):
    """Write message to daily publish log with timestamp"""
    timestamp = time.strftime("[%H:%M:%S]")
    with open(log_file, 'a') as f:
        f.write(f"{timestamp} {message}\n")

def main():
    """Main auto-publishing script"""
    log_file = _setup_daily_log()
    _log("START — AutoPublish daily run", log_file)
    
    # Check Google Sheets connection
    sheet = _get_sheet_client()
    if not sheet:
        _log("CRITICAL: Cannot connect to Google Sheets - exiting", log_file)
        sys.exit(1)
    
    try:
        worksheet = sheet.worksheet("AutoDubQueue")
        
        # Get all rows where Status=done and Output File exists
        data = worksheet.get_all_values()
        if not data or len(data) <= 1:
            _log("No completed videos found for publishing", log_file)
            return
        
        # Process each completed video
        processed_count = 0
        for row in data[1:]:  # Skip header
            if len(row) < 5:  # Skip incomplete rows
                continue
                
            url, status, attempts, output_file, notes, timestamp = row
            
            # Check if already published (has output file)
            if status.lower() == "done" and output_file and os.path.exists(output_file):
                processed_count += 1
                _log(f"PUBLISH — {url[:50]} — already published, skipping", log_file)
                continue
            
            # Read captions from workspace or archive
            caption_file = os.path.join("workspace", "captions.json")
            if not os.path.exists(caption_file):
                # Try archive path
                archive_path = os.path.join("archive", timestamp[:10], "captions.json")
                if os.path.exists(archive_path):
                    caption_file = archive_path
                else:
                    _log(f"PUBLISH — {url[:50]} — no captions found", log_file)
                    continue
            
            try:
                with open(caption_file, 'r') as f:
                    captions = json.load(f)
                
                _log(f"PUBLISH — {url[:50]} — publishing to platforms", log_file)
                
                # Call publish_to_platforms
                pub_results = publish_to_platforms(
                    api_key=os.getenv("ZERNIO_API_KEY"),
                    video_path=output_file,
                    captions=captions,
                    platforms=["instagram", "youtube", "tiktok", "facebook", "threads", "bluesky"],
                    publish_now=True,
                    scheduled_for=None,
                    teaser_path=None,
                    teaser_captions=None,
                    image_paths=[],
                    output_dir="workspace"
                )
                
                # Update sheet with results
                if pub_results:
                    success_platforms = [p for p, r in pub_results.items() if not (isinstance(r, dict) and "error" in r)]
                    if success_platforms:
                        notes = f"Published: {', '.join(success_platforms)} at {time.strftime('%Y-%m-%dT%H:%M:%SZ')}"
                        worksheet.update_cell(len(data) + processed_count, 4, notes)
                        worksheet.update_cell(len(data) + processed_count, 2, "done")
                        processed_count += 1
                        _log(f"PUBLISH — {url[:50]} — success: {', '.join(success_platforms)}", log_file)
                    else:
                        worksheet.update_cell(len(data) + processed_count, 4, f"Failed: {list(pub_results.keys())}")
                        _log(f"PUBLISH — {url[:50]} — failed: {list(pub_results.keys())}", log_file)
                else:
                    worksheet.update_cell(len(data) + processed_count, 4, "No publish results")
                    
            except Exception as e:
                _log(f"PUBLISH — {url[:50]} — error: {e}", log_file)
                worksheet.update_cell(len(data) + processed_count, 4, f"Error: {e}")
        
        _log(f"COMPLETE — {processed_count} videos processed", log_file)
        
    except Exception as e:
        _log(f"CRITICAL: Publishing failed: {e}", log_file)
        sys.exit(1)

if __name__ == "__main__":
    main()
