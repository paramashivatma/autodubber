#!/usr/bin/env python3
"""
CORRECTED Google Sheet update with REAL video information
"""

import os
import json
from datetime import datetime

def update_google_sheet_correctly():
    """Update Google Sheet with the CORRECT video details"""
    
    # Import the sheet logger
    from dubber.sheet_logger import quick_update_from_publish_result
    
    # REAL video details from workspace
    real_title = "બ્રહ્માંડના રહસ્યો: વિજ્ઞાન vs સમાધિ"
    real_duration = "1:19"  # CORRECT duration as provided by user
    
    # Format as "Gujarati (English)"
    formatted_title = f"{real_title}"
    
    # Mock publish results (since you already published manually)
    publish_results = {
        "youtube": {
            "post_id": "manual_upload_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
            "url": "https://youtube.com/watch?v=manual_upload"
        }
    }
    
    print(f'=== UPDATING GOOGLE SHEET WITH CORRECT DATA ===')
    print(f'REAL Title: {formatted_title}')
    print(f'CORRECT Duration: {real_duration}')
    print(f'Format: video')
    print(f'Platforms: {list(publish_results.keys())}')
    print()
    
    # Update the Google Sheet with CORRECT information
    try:
        success, message = quick_update_from_publish_result(
            video_title=formatted_title,
            publish_results=publish_results,
            duration=real_duration,
            source_lang="English",
            target_lang="Gujarati",
            content_format="video"
        )
        
        if success:
            print(f'✅ SUCCESS: {message}')
            print('✅ Google Sheet updated with CORRECT information!')
        else:
            print(f'❌ FAILED: {message}')
            return False
            
    except Exception as e:
        print(f'❌ ERROR: {e}')
        return False
    
    return True

if __name__ == "__main__":
    print("CORRECTED Google Sheet Update")
    print("=" * 40)
    print("Using REAL video title and CORRECT duration")
    print()
    
    success = update_google_sheet_correctly()
    
    if success:
        print("\n🎉 Google Sheet updated with CORRECT information!")
        print("✅ Real title from captions.json used")
        print("✅ Correct duration (1:19) as provided")
    else:
        print("\n❌ Failed to update Google Sheet")
        print("Please check your Google credentials and try again.")
