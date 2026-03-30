#!/usr/bin/env python3
"""Fix all sheet issues: proper title, duration, languages, remove extra columns"""

import os
import sys
import json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def fix_sheet_completely():
    """Fix all sheet issues"""
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        print("No GOOGLE_SHEET_ID found")
        return
    
    creds_path = os.path.join(os.path.dirname(__file__), "credentials.json")
    if not os.path.exists(creds_path):
        print(f"Credentials not found: {creds_path}")
        return
    
    # Get actual video info from workspace
    captions_path = os.path.join(os.path.dirname(__file__), "workspace", "captions.json")
    try:
        with open(captions_path, 'r', encoding='utf-8') as f:
            captions = json.load(f)
        
        video_title = captions.get("youtube", {}).get("title", "")
        if not video_title:
            print("No YouTube title found in captions.json")
            return
            
        print(f"Found actual video title: {video_title}")
        
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
        
        # Clear and rebuild sheet properly
        worksheet.clear()
        
        # Proper simplified headers (no extra columns)
        proper_headers = [
            "Video Title", "Status", "Attempts", "Duration",
            "Source Lang", "Target Lang", "Platforms", "Timestamp"
        ]
        worksheet.append_row(proper_headers)
        
        # Row 2: First video (preserve existing)
        row_2 = [
            "સવારની શક્તિ: શબ્દોથી પરિસ્થિતિનું નિર્માણ (Morning Power: Creating Reality from Words)",
            "done",
            "1",
            "00:29",
            "English",
            "Gujarati",
            "YouTube,Instagram,TikTok,Facebook,Twitter,Threads,Bluesky",
            "2026-03-30 14:08:20"
        ]
        worksheet.append_row(row_2)
        
        # Row 3: Second video (preserve existing)
        row_3 = [
            "કૈલાસા દ્વારા વિશ્વ શાંતિ માટે ૭૨ કલાકનું અખંડ અહિંસા ધ્યાન (72 Hours of Non-Violent Meditation for World Peace by KAILASA)",
            "done",
            "1",
            "01:03",
            "English",
            "Gujarati",
            "YouTube,Instagram,TikTok,Facebook,Twitter,Threads,Bluesky",
            "2026-03-30 14:45:00"
        ]
        worksheet.append_row(row_3)
        
        # Row 4: New video (latest one)
        row_4 = [
            video_title,  # Use actual title from captions.json
            "Published ✅",
            "1",
            "00:44",  # Duration from logs
            "English",
            "Gujarati",
            "Instagram,Facebook,YouTube,Threads,Twitter,TikTok,Bluesky",
            "2026-03-30 17:03:21"
        ]
        worksheet.append_row(row_4)
        
        print("✅ Fixed all sheet issues:")
        print("  - Proper headers (no extra columns)")
        print("  - Row 2: First video with proper title")
        print("  - Row 3: Second video with proper title")
        print(f"  - Row 4: New video with actual title: {video_title}")
        print("  - All durations filled")
        print("  - All languages filled")
        print("  - No more 'output.mp4' titles")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fix_sheet_completely()
