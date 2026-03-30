#!/usr/bin/env python3
"""Restore proper headers and update row 3"""

import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def restore_headers_and_fix_row3():
    """Restore proper headers and update row 3"""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("No GOOGLE_SHEET_ID found")
        return
    
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if not os.path.exists(creds_path):
        print(f"Credentials not found: {creds_path}")
        return
    
    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly"
        ])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet("AutoDubQueue")
        
        # Restore proper headers (Row 1)
        proper_headers = [
            "Video Title", "Status", "Attempts", "YouTube URL", "Duration",
            "Source Lang", "Target Lang", "Platforms", "Post IDs", "Timestamp"
        ]
        worksheet.update("A1:J1", [proper_headers])
        
        # Update row 3 with correct data
        video_title = "Nithyananda - Spiritual Teaching [qTto4ZFktZs]"
        
        row_3_data = [
            video_title,  # Column A: Video Title
            "done",  # Column B: Status
            "1",  # Column C: Attempts
            "https://youtube.com/shorts/69cab0cb618fd6943724b745",  # Column D: YouTube URL
            "00:29",  # Column E: Duration
            "en",  # Column F: Source Lang
            "gu",  # Column G: Target Lang
            "YouTube,Instagram,TikTok,Facebook,Twitter,Threads,Bluesky",  # Column H: Platforms
            "yt:69cab0cb618fd6943724b745,in:69cab0cd420bfafbac7f7f0d,ti:69cab0cc3304bb41123dd370,fa:69cab0cc3ff516397d7d4644,tw:69cab0cc618fd6943724b780,th:69cab0ca618fd6943724b70f,bl:69cab0cb3ff516397d7d462a",  # Column I: Post IDs
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Column J: Timestamp
        ]
        
        worksheet.update("A3:J3", [row_3_data])
        
        print("✅ Fixed Google Sheet:")
        print("  ✅ Restored proper headers in Row 1")
        print("  ✅ Updated Row 3 with correct data:")
        print(f"    - Video Title: {video_title}")
        print(f"    - YouTube URL: https://youtube.com/shorts/69cab0cb618fd6943724b745")
        print(f"    - Duration: 00:29")
        print(f"    - Source Lang: en")
        print(f"    - Target Lang: gu")
        print(f"    - All 7 platforms with post IDs")
        print("  ✅ Row 2 left unchanged")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    restore_headers_and_fix_row3()
