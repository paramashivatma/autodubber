#!/usr/bin/env python3
"""
Manual Google Sheet update for the published video
"""

import os
import json
from datetime import datetime

def update_google_sheet_manually():
    """Update Google Sheet with the published video details"""
    
    # Import the sheet logger
    from dubber.sheet_logger import quick_update_from_publish_result
    
    # Get video details from workspace
    workspace_dir = 'workspace'
    video_title = "બ્રહ્માંડના રહસ્યો: વિજ્ઞાન vs સમાધિ"
    english_title = "Brahmanda's Secrets: Science vs Meditation"
    
    # Format as "Gujarati (English)"
    formatted_title = f"{video_title} ({english_title})"
    
    # Mock publish results (since you already published manually)
    publish_results = {
        "youtube": {
            "post_id": "manual_upload_" + datetime.now().strftime("%Y%m%d_%H%M%S"),
            "url": "https://youtube.com/watch?v=manual_upload"
        }
    }
    
    # Get video duration
    duration = "Unknown"  # We'll update this if we can find it
    
    # Try to get duration from video file
    try:
        import subprocess
        video_file = os.path.join(workspace_dir, 'source.mp4')
        if os.path.exists(video_file):
            # Use ffprobe to get duration
            result = subprocess.run([
                'ffprobe', '-v', 'quiet', '-show_entries', 'format=duration',
                '-of', 'csv=p=0', video_file
            ], capture_output=True, text=True, timeout=10)
            
            if result.returncode == 0:
                duration_sec = float(result.stdout.strip())
                minutes = int(duration_sec // 60)
                seconds = int(duration_sec % 60)
                duration = f"{minutes}:{seconds:02d}"
                print(f"✅ Video duration: {duration}")
    except Exception as e:
        print(f"⚠️  Could not get video duration: {e}")
        duration = "Unknown"
    
    print(f'=== UPDATING GOOGLE SHEET ===')
    print(f'Title: {formatted_title}')
    print(f'Duration: {duration}')
    print(f'Format: video')
    print(f'Platforms: {list(publish_results.keys())}')
    print()
    
    # Update the Google Sheet
    try:
        success, message = quick_update_from_publish_result(
            video_title=formatted_title,
            publish_results=publish_results,
            duration=duration,
            source_lang="English",
            target_lang="Gujarati",
            content_format="video"
        )
        
        if success:
            print(f'✅ SUCCESS: {message}')
            print('✅ Google Sheet updated successfully!')
        else:
            print(f'❌ FAILED: {message}')
            return False
            
    except Exception as e:
        print(f'❌ ERROR: {e}')
        return False
    
    return True

if __name__ == "__main__":
    print("Manual Google Sheet Update")
    print("=" * 40)
    
    success = update_google_sheet_manually()
    
    if success:
        print("\n🎉 Google Sheet updated successfully!")
    else:
        print("\n❌ Failed to update Google Sheet")
        print("Please check your Google credentials and try again.")
