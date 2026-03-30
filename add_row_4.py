#!/usr/bin/env python3
"""Add new video data to row 4 with correct info"""

import os
import sys
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def add_row_4():
    """Add new video data to row 4"""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("No GOOGLE_SHEET_ID found")
        return
    
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if not os.path.exists(creds_path):
        print(f"Credentials not found: {creds_path}")
        return
    
    # Read the latest video info from workspace
    captions_path = os.path.join(os.path.dirname(__file__), "workspace", "captions.json")
    try:
        with open(captions_path, 'r', encoding='utf-8') as f:
            captions = json.load(f)
        
        # Get YouTube title from latest video (this should be the new one)
        youtube_title = captions.get("youtube", {}).get("title", "")
        if not youtube_title:
            print("No YouTube title found in captions.json")
            return
            
        print(f"Using YouTube title: {youtube_title}")
        
    except Exception as e:
        print(f"Error reading captions.json: {e}")
        return
    
    try:
        creds = Credentials.from_service_account_file(creds_path, scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive.readonly"
        ])
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(sheet_id)
        worksheet = spreadsheet.worksheet("AutoDubQueue")
        
        # Data for row 4 (new video)
        row_4_data = [
            youtube_title,  # Column A: Video Title
            "done",  # Column B: Status
            "1",  # Column C: Attempts
            "https://youtube.com/shorts/NEW_VIDEO_ID",  # Column D: YouTube URL (will be updated after publish)
            "01:03",  # Column E: Duration (1 minute 3 seconds)
            "en",  # Column F: Source Lang
            "gu",  # Column G: Target Lang
            "YouTube,Instagram,TikTok,Facebook,Twitter,Threads,Bluesky",  # Column H: Platforms
            "Will be updated after publish",  # Column I: Post IDs
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")  # Column J: Timestamp
        ]
        
        # Add row 4
        worksheet.append_row(row_4_data)
        
        print("✅ Added Row 4 with new video data:")
        print(f"  - Video Title: {youtube_title}")
        print(f"  - Duration: 01:03 (1 minute 3 seconds)")
        print(f"  - Source Lang: en")
        print(f"  - Target Lang: gu")
        print(f"  - YouTube URL: Will be updated after publish")
        print(f"  - Post IDs: Will be updated after publish")
        print("  Note: YouTube URL and Post IDs will be updated after successful publish")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    add_row_4()
