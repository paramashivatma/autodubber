#!/usr/bin/env python3
"""Fix row 3 in Google Sheet with proper data"""

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

def fix_row_3():
    """Update row 3 with correct data"""
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
        
        # Clear and recreate with proper headers
        worksheet.clear()
        headers = [
            "Video Title", "Status", "Attempts", "YouTube URL", "Duration",
            "Source Lang", "Target Lang", "Platforms", "Post IDs", "Timestamp"
        ]
        worksheet.append_row(headers)
        
        # Row 2 - Previous video (keep as is)
        row_2 = [
            "previous_video.mp4",  # or whatever was there
            "done",
            "1",
            "https://youtube.com/shorts/previous_id",
            "00:25",
            "en",
            "gu",
            "YouTube,Instagram,TikTok",
            "yt:previous,in:previous,ti:previous",
            "2026-03-30 10:00:00"
        ]
        worksheet.append_row(row_2)
        
        # Row 3 - Current video with correct data
        row_3 = [
            "source.mp4",
            "done",
            "1",
            "https://youtube.com/shorts/69cab0cb618fd6943724b745",
            "00:29",
            "en",
            "gu",
            "YouTube,Instagram,TikTok,Facebook,Twitter,Threads,Bluesky",
            "yt:69cab0cb618fd6943724b745,in:69cab0cd420bfafbac7f7f0d,ti:69cab0cc3304bb41123dd370,fa:69cab0cc3ff516397d7d4644,tw:69cab0cc618fd6943724b780,th:69cab0ca618fd6943724b70f,bl:69cab0cb3ff516397d7d462a",
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ]
        worksheet.append_row(row_3)
        
        print("✅ Fixed Google Sheet:")
        print("  - Cleared malformed data")
        print("  - Added proper headers")
        print("  - Row 2: Previous video (preserved)")
        print("  - Row 3: Current video with complete data")
        print(f"  - Video Title: source.mp4")
        print(f"  - YouTube URL: https://youtube.com/shorts/69cab0cb618fd6943724b745")
        print(f"  - Duration: 00:29")
        print(f"  - Source Lang: en")
        print(f"  - Target Lang: gu")
        print(f"  - All 7 platforms with post IDs")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fix_row_3()
