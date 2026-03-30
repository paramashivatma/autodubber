#!/usr/bin/env python3
"""Update Row 2 with full language names and English translation of title"""

import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    import gspread
    from google.oauth2.service_account import Credentials
except ImportError:
    print("gspread not installed")
    sys.exit(1)

def update_row_2_details():
    """Update Row 2 with full language names and English translation"""
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
        
        # Update Row 2 with enhanced details
        # Video title with English translation in parentheses
        video_title_with_translation = "કૈલાસા દ્વારા વિશ્વ શાંતિ માટે ૭૨ કલાકનું અખંડ અહિંસા ધ્યાન (72 Hours of Non-Violent Meditation for World Peace by KAILASA)"
        
        # Full language names instead of abbreviations
        source_lang_full = "English"
        target_lang_full = "Gujarati"
        
        # Update Row 2, Column A (Video Title)
        worksheet.update("A2", [[video_title_with_translation]])
        
        # Update Row 2, Column F (Source Lang)
        worksheet.update("F2", [[source_lang_full]])
        
        # Update Row 2, Column G (Target Lang)
        worksheet.update("G2", [[target_lang_full]])
        
        print("✅ Updated Row 2 with enhanced details:")
        print(f"  - Video Title: {video_title_with_translation}")
        print(f"  - Source Language: {source_lang_full}")
        print(f"  - Target Language: {target_lang_full}")
        print("  - All other fields remain unchanged")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    update_row_2_details()
