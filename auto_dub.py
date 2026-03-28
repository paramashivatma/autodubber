import os, json, time, sys
import gspread
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request
from dotenv import load_dotenv
from dubber.utils import log
from dubber.fetcher import fetch_shorts_urls
from dubber import (
    transcribe_audio, merge_short_segments, translate_segments,
    generate_tts_audio, build_dubbed_video,
    extract_vision, generate_all_captions,
    generate_teaser, generate_teasers, publish_to_platforms,
)

# Load environment
load_dotenv()

# Configuration from .env
SOURCE_CHANNEL = os.getenv("SOURCE_CHANNEL")
DUB_VOICE = os.getenv("DUB_VOICE", "gu-IN-NiranjanNeural")
DUB_SOURCE_LANG = os.getenv("DUB_SOURCE_LANG", "en")
DUB_TARGET_LANG = os.getenv("DUB_TARGET_LANG", "gu")
DUB_WHISPER_MODEL = os.getenv("DUB_WHISPER_MODEL", "medium")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
SEMI_AUTO_PUBLISH = os.getenv("SEMI_AUTO_PUBLISH", "false").lower() == "true"
MAX_RETRIES = int(os.getenv("MAX_RETRIES", "2"))
ARCHIVE_DIR = os.getenv("ARCHIVE_DIR", "archive")
DAILY_LOG_DIR = os.getenv("DAILY_LOG_DIR", "logs")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_DAILY_LIMIT = int(os.getenv("GEMINI_DAILY_LIMIT", "200"))
ARCHIVE_RETENTION_DAYS = int(os.getenv("ARCHIVE_RETENTION_DAYS", "30"))
MIN_DISK_GB = int(os.getenv("MIN_DISK_GB", "2"))
GEMINI_VISION_KEY = os.getenv("GEMINI_VISION_KEY")
MISTRAL_API_KEY = os.getenv("MISTRAL_API_KEY")
ZERNIO_API_KEY = os.getenv("ZERNIO_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

# Global counters
gemini_call_count = 0

def _check_disk_space():
    """Check if minimum disk space is available"""
    import shutil
    total, used, free = shutil.disk_usage("/")
    free_gb = free // (1024**3)
    log("SYSTEM", f"  Disk space: {free_gb}GB free (require {MIN_DISK_GB}GB)")
    return free_gb >= MIN_DISK_GB

def _test_api_keys():
    """Test if API keys are valid"""
    import requests
    
    # Test Gemini API
    if GEMINI_VISION_KEY:
        try:
            response = requests.get(
                "https://generativelanguage.googleapis.com/v1/models",
                headers={"Authorization": f"Bearer {GEMINI_VISION_KEY}"},
                timeout=10
            )
            if response.status_code == 200:
                log("SYSTEM", "  Gemini API key valid")
            else:
                log("SYSTEM", f"  Gemini API key invalid: {response.status_code}")
                return False
        except Exception as e:
            log("SYSTEM", f"  Gemini API test failed: {e}")
            return False
    else:
        log("SYSTEM", "  WARNING: No Gemini API key configured")
    
    # Test Groq API
    if GROQ_API_KEY:
        try:
            response = requests.get(
                "https://api.groq.com/v1/models",
                headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
                timeout=10
            )
            if response.status_code == 200:
                log("SYSTEM", "  Groq API key valid")
            else:
                log("SYSTEM", f"  Groq API key invalid: {response.status_code}")
                return False
        except Exception as e:
            log("SYSTEM", f"  Groq API test failed: {e}")
            return False
    else:
        log("SYSTEM", "  WARNING: No Groq API key configured")
    
    return True

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
        log("SYSTEM", f"  Google Sheets auth failed: {e}")
        return None

def _load_queue_backup():
    """Load local CSV backup if Sheets is unavailable"""
    backup_file = "queue_backup.csv"
    if os.path.exists(backup_file):
        try:
            with open(backup_file, 'r') as f:
                lines = f.readlines()
                if len(lines) > 1:  # Skip header
                    return [line.strip().split(',') for line in lines[1:]]
        except Exception as e:
            log("SYSTEM", f"  Failed to load backup: {e}")
    return []

def _save_queue_backup(queue):
    """Save queue to local CSV backup"""
    backup_file = "queue_backup.csv"
    with open(backup_file, 'w') as f:
        f.write("URL,Status,Attempts,Output File,Notes,Timestamp\n")
        for row in queue:
            f.write(f"{row['url']},{row['status']},{row['attempts']},{row['output_file']},{row['notes']},{row['timestamp']}\n")

def _setup_daily_log():
    """Setup daily log file"""
    os.makedirs(DAILY_LOG_DIR, exist_ok=True)
    log_file = os.path.join(DAILY_LOG_DIR, time.strftime("%Y-%m-%d.txt"))
    return log_file

def _log(message, log_file):
    """Write message to daily log with timestamp"""
    timestamp = time.strftime("[%H:%M:%S]")
    with open(log_file, 'a') as f:
        f.write(f"{timestamp} {message}\n")

def main():
    """Main auto-dubbing pipeline"""
    global gemini_call_count
    
    # Step 1: Pre-flight checks
    log_file = _setup_daily_log()
    _log("START — AutoDubber daily run", log_file)
    
    # Check API keys
    if not _test_api_keys():
        _log("CRITICAL: API key validation failed - exiting", log_file)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            _send_telegram_alert("CRITICAL: API key validation failed")
        sys.exit(1)
    
    # Check disk space
    if not _check_disk_space():
        _log("CRITICAL: Insufficient disk space - exiting", log_file)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            _send_telegram_alert("CRITICAL: Insufficient disk space")
        sys.exit(1)
    
    # Check source channel
    if not SOURCE_CHANNEL:
        _log("CRITICAL: SOURCE_CHANNEL not set in .env - exiting", log_file)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            _send_telegram_alert("CRITICAL: SOURCE_CHANNEL not configured")
        sys.exit(1)
    
    _log("PRE-FLIGHT — all checks passed", log_file)
    
    # Step 2: Fetch and queue
    try:
        sheet = _get_sheet_client()
        if sheet:
            # Read existing URLs from sheet
            worksheet = sheet.worksheet("AutoDubQueue")
            existing_data = worksheet.get_all_values()
            existing_urls = set()
            if existing_data and len(existing_data) > 1:
                existing_urls = {row[0] for row in existing_data[1:] if row[0]}
            
            # Fetch new URLs
            new_urls = fetch_shorts_urls(SOURCE_CHANNEL, existing_urls=existing_urls)
            
            # Append to sheet
            for url in new_urls:
                timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ")
                worksheet.append_row([url, "pending", 0, "", "", timestamp])
            
            _log(f"FETCH — {len(new_urls)} new URLs added to queue", log_file)
        else:
            # Fallback to local backup
            _log("FETCH — Google Sheets unavailable, using local backup", log_file)
            existing_urls = set()
            backup_queue = _load_queue_backup()
            new_urls = fetch_shorts_urls(SOURCE_CHANNEL, existing_urls=existing_urls)
            
            # Save updated queue
            updated_queue = backup_queue + [[url, "pending", 0, "", "", time.strftime("%Y-%m-%dT%H:%M:%SZ")] for url in new_urls]
            _save_queue_backup(updated_queue)
            _log(f"FETCH — {len(new_urls)} new URLs processed from backup", log_file)
            
    except Exception as e:
        _log(f"CRITICAL: Fetch failed: {e}", log_file)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            _send_telegram_alert(f"CRITICAL: Fetch failed: {e}")
        sys.exit(1)
    
    # Step 3: Process queue
    try:
        sheet = _get_sheet_client()
        if sheet:
            worksheet = sheet.worksheet("AutoDubQueue")
            
            # Get all pending rows
            data = worksheet.get_all_values()
            pending_rows = []
            if data and len(data) > 1:
                pending_rows = [data[1:]]  # Skip header
            
            processed_count = 0
            success_count = 0
            failed_count = 0
            skipped_count = 0
            
            for row in pending_rows:
                if len(row) < 5:  # Skip incomplete rows
                    continue
                
                url, status, attempts, output_file, notes, timestamp = row
                
                if status == "done":
                    continue  # Skip already processed
                
                # Check if output file already exists
                if output_file and os.path.exists(output_file):
                    _log(f"VIDEO {url[:50]} — output exists, skipping", log_file)
                    worksheet.update_cell(len(pending_rows) + 1, 5, "skipped: output exists")
                    skipped_count += 1
                    continue
                
                # Check Gemini daily limit
                if gemini_call_count >= GEMINI_DAILY_LIMIT:
                    _log(f"DAILY LIMIT REACHED — stopping batch", log_file)
                    _send_telegram_alert("Gemini daily limit reached - stopping batch")
                    break
                
                processed_count += 1
                gemini_call_count += 1  # Estimate (each video uses multiple Gemini calls)
                
                _log(f"VIDEO {processed_count}/{len(pending_rows)} — {url[:50]} — processing", log_file)
                
                try:
                    # Run dubbing pipeline
                    def status_cb(msg): _log(f"VIDEO {processed_count} — {msg}", log_file)
                    def caption_ready_cb(**kwargs): pass  # Auto-publish mode
                    def done_cb(success, msg, pub_results=None):
                        nonlocal success_count, failed_count
                        if success:
                            success_count += 1
                            worksheet.update_cell(processed_count + 1, 2, "done")
                            worksheet.update_cell(processed_count + 1, 5, f"Published {time.strftime('%Y-%m-%dT%H:%M:%SZ')}")
                        else:
                            failed_count += 1
                            worksheet.update_cell(processed_count + 1, 2, "failed")
                            worksheet.update_cell(processed_count + 1, 4, f"Error: {msg}")
                    
                    run_dub_pipeline(
                        video_input=url,
                        voice=DUB_VOICE,
                        model_size=DUB_WHISPER_MODEL,
                        src_lang=DUB_SOURCE_LANG,
                        tgt_lang=DUB_TARGET_LANG,
                        use_bgm=False,
                        bgm_volume=0.5,
                        gemini_vision_key=GEMINI_VISION_KEY,
                        mistral_key=MISTRAL_API_KEY,
                        zernio_key=ZERNIO_API_KEY,
                        selected_platforms=["instagram", "youtube", "tiktok", "facebook", "threads", "bluesky"],
                        publish_now=SEMI_AUTO_PUBLISH,
                        scheduled_for=None,
                        auto_teaser=True,
                        manual_teaser_path=None,
                        image_paths=[],
                        status_cb=status_cb,
                        caption_ready_cb=caption_ready_cb,
                        done_cb=done_cb
                    )
                    
                except Exception as e:
                    _log(f"VIDEO {processed_count} — failed: {e}", log_file)
                    worksheet.update_cell(processed_count + 1, 2, "failed")
                    worksheet.update_cell(processed_count + 1, 4, f"Error: {e}")
                    failed_count += 1
                    
            # Step 4: Archive rotation
            _log("ARCHIVE — cleaning old files", log_file)
            archive_path = os.path.join(ARCHIVE_DIR, time.strftime("%Y-%m-%d"))
            os.makedirs(archive_path, exist_ok=True)
            
            # Delete old archive folders
            current_time = time.time()
            for item in os.listdir(ARCHIVE_DIR):
                item_path = os.path.join(ARCHIVE_DIR, item)
                if os.path.isdir(item_path):
                    item_time = os.path.getmtime(item_path)
                    age_days = (current_time - item_time) / (24 * 3600)
                    if age_days > ARCHIVE_RETENTION_DAYS:
                        import shutil
                        shutil.rmtree(item_path)
                        _log(f"ARCHIVE — deleted {item} ({age_days:.1f} days old)", log_file)
            
            # Step 5: Summary
            _log(f"COMPLETE — {processed_count} processed, {success_count} done, {failed_count} failed, {skipped_count} skipped", log_file)
            _send_telegram_summary(processed_count, success_count, failed_count, skipped_count)
            
    except Exception as e:
        _log(f"CRITICAL: Processing failed: {e}", log_file)
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            _send_telegram_alert(f"CRITICAL: Processing failed: {e}")

def _send_telegram_alert(message):
    """Send Telegram alert"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    try:
        import requests
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": f"🚨 AutoDubber Alert: {message}"},
            timeout=10
        )
        log("TELEGRAM", f"  Alert sent: {message}")
    except Exception as e:
        log("TELEGRAM", f"  Failed to send alert: {e}")

def _send_telegram_summary(processed, done, failed, skipped):
    """Send daily summary to Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    try:
        import requests
        message = f"""📊 AutoDubber Daily Run — {time.strftime('%Y-%m-%d')}
✅ Dubbed: {done}
❌ Failed: {failed}
⏭️ Skipped: {skipped}
📁 Archive: {ARCHIVE_DIR}/{time.strftime('%Y-%m-%d')}/
⏱️ Total time: {time.strftime('%H:%M')}"""
        
        response = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={"chat_id": TELEGRAM_CHAT_ID, "text": message},
            timeout=10
        )
        log("TELEGRAM", f"  Summary sent")
    except Exception as e:
        log("TELEGRAM", f"  Failed to send summary: {e}")

if __name__ == "__main__":
    main()
