#!/usr/bin/env python3
"""Properly fix ONLY row 3 without touching headers or other rows"""

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

def proper_fix_row3():
    """Update ONLY row 3 with correct data, preserving headers and other rows"""
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
        
        # Get current content to see what we have
        all_values = worksheet.get_all_values()
        
        print("Current sheet content:")
        for i, row in enumerate(all_values, start=1):
            print(f"Row {i}: {row}")
        print()
        
        # Prepare proper data for row 3
        # Using a meaningful title based on the video URL
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
        
        # Update ONLY row 3 (range A3:J3)
        worksheet.update("A3:J3", [row_3_data])
        
        print("✅ Updated ONLY row 3 with correct data:")
        print(f"  Row 3, Column A (Video Title): {video_title}")
        print(f"  Row 3, Column D (YouTube URL): https://youtube.com/shorts/69cab0cb618fd6943724b745")
        print(f"  Row 3, Column E (Duration): 00:29")
        print(f"  Row 3, Column F (Source Lang): en")
        print(f"  Row 3, Column G (Target Lang): gu")
        print(f"  Row 3, Column H (Platforms): All 7 platforms")
        print(f"  Row 3, Column I (Post IDs): All post IDs recorded")
        print("  Headers and other rows were NOT modified")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    proper_fix_row3()
