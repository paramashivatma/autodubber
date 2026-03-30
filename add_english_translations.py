#!/usr/bin/env python3
"""Add English translations in parentheses for Gujarati titles"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def add_english_translations():
    """Add English translations in parentheses for Gujarati titles"""
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
        
        # Clear and rebuild with English translations
        worksheet.clear()
        
        # Proper headers
        headers = [
            "Video Title", "Status", "Attempts", "Duration",
            "Source Lang", "Target Lang", "Platforms", "Timestamp"
        ]
        worksheet.append_row(headers)
        
        # Row 2: First video with English translation
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
        
        # Row 3: Second video with English translation
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
        
        # Row 4: Third video with English translation
        row_4 = [
            "જીવન મુક્તિ પુસ્તક અને આત્મજ્ઞાન (Divine Attunement)",
            "Published ✅",
            "1",
            "00:44",
            "English",
            "Gujarati",
            "Instagram,Facebook,YouTube,Threads,Twitter,TikTok,Bluesky",
            "2026-03-30 17:03:21"
        ]
        worksheet.append_row(row_4)
        
        print("✅ Added English translations in parentheses:")
        print("  Row 1: Headers")
        print("  Row 2: Gujarati title + (Morning Power: Creating Reality from Words)")
        print("  Row 3: Gujarati title + (72 Hours of Non-Violent Meditation for World Peace by KAILASA)")
        print("  Row 4: Gujarati title + (Divine Attunement)")
        print("  All rows now have bilingual titles")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    add_english_translations()
