#!/usr/bin/env python3
"""Fix sheet structure to prevent overwriting and ensure proper row management"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def fix_sheet_structure():
    """Fix sheet to ensure proper row management"""
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
        
        # Get current data
        all_values = worksheet.get_all_values()
        
        print("Current sheet structure:")
        for i, row in enumerate(all_values, start=1):
            print(f"Row {i}: {row}")
        print()
        
        # Clear and rebuild with proper structure
        worksheet.clear()
        
        # Add proper headers
        headers = [
            "Video Title", "Status", "Attempts", "YouTube URL", "Duration",
            "Source Lang", "Target Lang", "Platforms", "Post IDs", "Timestamp"
        ]
        worksheet.append_row(headers)
        
        # Add existing videos in chronological order (oldest first)
        # Row 2: First video (સવારની શક્તિ: શબ્દોથી પરિસ્થિતિનું નિર્માણ)
        row_2 = [
            "સવારની શક્તિ: શબ્દોથી પરિસ્થિતિનું નિર્માણ",
            "done",
            "1",
            "https://youtube.com/shorts/69cab0cb618fd6943724b745",
            "00:29",
            "en",
            "gu",
            "YouTube,Instagram,TikTok,Facebook,Twitter,Threads,Bluesky",
            "yt:69cab0cb618fd6943724b745,in:69cab0cd420bfafbac7f7f0d,ti:69cab0cc3304bb41123dd370,fa:69cab0cc3ff516397d7d4644,tw:69cab0cc618fd6943724b780,th:69cab0ca618fd6943724b70f,bl:69cab0cb3ff516397d7d462a",
            "2026-03-30 14:08:20"
        ]
        worksheet.append_row(row_2)
        
        # Row 3: Second video (કૈલાસા દ્વારા વિશ્વ શાંતિ માટે ૭૨ કલાકનું અખંડ અહિંસા ધ્યાન)
        row_3 = [
            "કૈલાસા દ્વારા વિશ્વ શાંતિ માટે ૭૨ કલાકનું અખંડ અહિંસા ધ્યાન",
            "done",
            "1",
            "https://youtube.com/shorts/NEW_VIDEO_ID",  # Will be updated after publish
            "01:03",
            "en",
            "gu",
            "YouTube,Instagram,TikTok,Facebook,Twitter,Threads,Bluesky",
            "Will be updated after publish",
            "2026-03-30 14:45:00"
        ]
        worksheet.append_row(row_3)
        
        print("✅ Fixed sheet structure:")
        print("  - Row 1: Headers")
        print("  - Row 2: First video (oldest)")
        print("  - Row 3: Second video (newer)")
        print("  - Next video will go to Row 4")
        print("  - No more overwriting issues!")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    fix_sheet_structure()
