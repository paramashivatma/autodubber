import os
import yt_dlp
from .utils import log

def fetch_shorts_urls(channel_url, n=10, existing_urls=set()):
    """
    Fetch last N videos from a YouTube channel/shorts URL using yt-dlp.
    
    Args:
        channel_url: YouTube channel or shorts URL
        n: Number of videos to fetch (default: 10)
        existing_urls: Set of URLs to exclude
    
    Returns:
        List of video URLs (max N items)
    """
    log("FETCH", f"Fetching up to {n} videos from {channel_url}")
    
    try:
        # Configure yt-dlp for metadata only (no download)
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'extract_flat': True,
            'playlistend': n,
            'extract_info_json': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            # Extract channel info
            info = ydl.extract_info(channel_url, download=False)
            
            if not info:
                log("FETCH", f"  No channel info found for {channel_url}")
                return []
            
            # Get entries (videos)
            entries = info.get('entries', [])
            
            if not entries:
                log("FETCH", f"  No videos found in channel")
                return []
            
            # Filter and process entries
            urls = []
            for entry in entries[:n]:  # Limit to N videos
                # Check duration (under 60 seconds)
                duration = entry.get('duration', 0)
                if duration > 60:
                    log("FETCH", f"  Skipping {entry.get('title', 'Unknown')}: {duration}s > 60s limit")
                    continue
                
                # Check language (English only)
                language = entry.get('language', 'unknown')
                if language and language.lower() != 'en':
                    log("FETCH", f"  Skipping {entry.get('title', 'Unknown')}: non-English language ({language})")
                    continue
                
                # Get video URL
                url = entry.get('webpage_url') or entry.get('url')
                if not url:
                    log("FETCH", f"  No URL found for {entry.get('title', 'Unknown')}")
                    continue
                
                # Skip if already exists
                if url in existing_urls:
                    log("FETCH", f"  Skipping {entry.get('title', 'Unknown')}: already processed")
                    continue
                
                urls.append(url)
                log("FETCH", f"  Found: {entry.get('title', 'Unknown')} ({duration}s)")
            
            log("FETCH", f"  Retrieved {len(urls)} videos (filtered by duration <60s, English only)")
            return urls
            
    except Exception as e:
        log("FETCH", f"  ERROR: {e}")
        return []
