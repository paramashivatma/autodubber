"""
Simple Zernio SDK Publisher
Replaces complex custom publishing with official SDK
"""

import os
from zernio import Zernio, ZernioAPIError, ZernioAuthenticationError, ZernioConnectionError, ZernioRateLimitError, ZernioTimeoutError
from dubber.utils import log, PLATFORM_ACCOUNTS

def upload_large_file(client, file_path):
    """Upload large file - currently limited by Vercel function payload size"""
    
    # Check file size
    file_size = os.path.getsize(file_path)
    log("PUBLISH", f"  📏 File size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")
    
    # Current limit based on testing: ~8MB due to Vercel FUNCTION_PAYLOAD_TOO_LARGE
    if file_size > 8 * 1024 * 1024:  # 8MB limit
        error_msg = f"""File too large for current upload method ({file_size/1024/1024:.1f} MB).

Current upload limit: ~8MB (Vercel function payload limit)

SOLUTIONS for {file_size/1024/1024:.1f} MB files:

1. 🌐 Host externally and use media_items with external URL:
   - Upload to YouTube, Vimeo, or your own CDN
   - Use: media_items=[{{"type": "video", "url": "https://external-url/video.mp4"}}]

2. 📏 Compress video to under 8MB:
   - Reduce resolution or quality
   - Use video compression tools

3. 📞 Contact Zernio support for large file upload API:
   - Request direct-to-storage upload URLs
   - Ask about multipart/resumable upload support

TEMPORARY: Upload smaller files or use external hosting."""
        
        log("PUBLISH", f"  ❌ {error_msg}")
        raise Exception(error_msg)
    
    # Try regular upload for small files
    try:
        log("PUBLISH", f"  � Trying regular upload (file under 8MB)...")
        result = client.media.upload(file_path)
        media_url = result["publicUrl"]
        log("PUBLISH", f"  ✅ Regular upload worked: {media_url[:50]}...")
        return media_url
    except Exception as e:
        log("PUBLISH", f"  ❌ Regular upload failed: {e}")
        raise e

def publish_with_sdk(api_key, captions, platforms, upload_results=None, 
                    scheduled_for=None, publish_now=True, teaser_captions=None, 
                    output_dir="workspace", progress_cb=None, fallback_files=None):
    """
    Publish to all platforms using official Zernio SDK
    """
    log("PUBLISH", f"🎯 STARTING publish_with_sdk")
    log("PUBLISH", f"  🔑 API Key: {api_key[:10]}..." if api_key else "❌ No API key")
    log("PUBLISH", f"  📱 Platforms: {platforms}")
    log("PUBLISH", f"  📄 Upload results: {list(upload_results.keys()) if upload_results else None}")
    log("PUBLISH", f"  📄 Fallback files: {list(fallback_files.keys()) if fallback_files else None}")
    
    try:
        # Initialize Zernio client with timeout
        log("PUBLISH", f"  🔧 Initializing Zernio client with timeout...")
        client = Zernio(api_key=api_key, timeout=120.0)  # 2 min timeout for large uploads
        log("PUBLISH", "✅ Zernio SDK initialized")
        
        if progress_cb:
            progress_cb(0, len(platforms), "sdk", "initializing")
        
        # Prepare media URLs - upload video if needed
        media_urls = []
        if upload_results:
            # Add main video
            main_video_url = upload_results.get("main_video")
            if main_video_url:
                media_urls.append(main_video_url)
                log("PUBLISH", f"  ✅ Main video: {main_video_url[:50]}...")
            
            # Add teaser videos
            for platform, teaser_url in upload_results.items():
                if platform.startswith("teaser_") and teaser_url:
                    media_urls.append(teaser_url)
                    log("PUBLISH", f"  ✅ Teaser {platform}: {teaser_url[:50]}...")
        
        # If no media URLs, we need to upload the video or images
        if not media_urls and fallback_files:
            log("PUBLISH", "🔄 No media URLs found, need to upload files...")
            log("PUBLISH", f"  📄 Fallback files available: {list(fallback_files.keys())}")
            
            # Check if files exist
            for key, path in fallback_files.items():
                exists = os.path.exists(path) if path else False
                size = os.path.getsize(path) if exists and path else 0
                log("PUBLISH", f"  📁 {key}: {path} - {'✅' if exists else '❌'} ({size:,} bytes)")
            
            log("PUBLISH", "🔄 Starting media file upload process...")
            
            # Try video first
            main_video_path = fallback_files.get("main_video")
            if main_video_path and os.path.exists(main_video_path):
                try:
                    # Check file size
                    file_size = os.path.getsize(main_video_path)
                    log("PUBLISH", f"  📏 Video file size: {file_size:,} bytes ({file_size/1024/1024:.1f} MB)")
                    
                    if file_size > 4 * 1024 * 1024:  # 4MB limit - use presigned upload
                        log("PUBLISH", f"  📤 File too large for direct upload, using presigned URL...")
                        video_url = upload_large_file(client, main_video_path)
                    else:
                        result = client.media.upload(main_video_path)
                        video_url = result["publicUrl"]
                    
                    media_urls.append(video_url)  # Add single URL to list
                    log("PUBLISH", f"  ✅ Main video uploaded: {video_url[:50]}...")
                except Exception as e:
                    log("PUBLISH", f"  ❌ Upload failed: {e}")
                    return {"error": f"Media upload failed: {e}"}
            
            # Try images if no video
            elif not main_video_path:
                # Support multiple images
                main_image_path = fallback_files.get("main_image")
                if main_image_path and os.path.exists(main_image_path):
                    try:
                        # Check file size
                        file_size = os.path.getsize(main_image_path)
                        log("PUBLISH", f"  📏 Main image file size: {file_size:,} bytes")
                        
                        if file_size > 4 * 1024 * 1024:  # 4MB limit
                            log("PUBLISH", f"  📤 Main image too large, using upload_large...")
                            img_url = upload_large_file(client, main_image_path)
                        else:
                            result = client.media.upload(main_image_path)
                            img_url = result["publicUrl"]
                        
                        media_urls.append(img_url)
                        log("PUBLISH", f"  ✅ Main image uploaded: {img_url[:50]}...")
                    except Exception as e:
                        log("PUBLISH", f"  ❌ Upload failed: {e}")
                        return {"error": f"Media upload failed: {e}"}
                
                # Additional images
                additional_images = fallback_files.get("additional_images", [])
                for i, img_path in enumerate(additional_images):
                    if img_path and os.path.exists(img_path):
                        try:
                            # Check file size
                            file_size = os.path.getsize(img_path)
                            log("PUBLISH", f"  📏 Image {i+1} file size: {file_size:,} bytes")
                            
                            if file_size > 4 * 1024 * 1024:  # 4MB limit
                                log("PUBLISH", f"  📤 Image {i+1} too large, using upload_large...")
                                img_url = upload_large_file(client, img_path)
                            else:
                                result = client.media.upload(img_path)
                                img_url = result["publicUrl"]
                            
                            media_urls.append(img_url)
                            log("PUBLISH", f"  ✅ Uploaded additional image {i+1}: {img_url[:50]}...")
                        except Exception as e:
                            log("PUBLISH", f"  ❌ Additional image {i+1} upload failed: {e}")
                            # Continue with other images instead of failing completely
        
        # Get default content (use first available caption as fallback)
        default_content = ""
        platform_specific_contents = {}
        
        for platform, platform_data in captions.items():
            if isinstance(platform_data, dict) and platform_data.get("caption"):
                caption_text = platform_data["caption"]
                if not default_content:
                    default_content = caption_text  # First one becomes default
                # Store platform-specific content (will be used if different from default)
                platform_specific_contents[platform] = caption_text
            elif isinstance(platform_data, str):
                if not default_content:
                    default_content = platform_data  # First one becomes default
                platform_specific_contents[platform] = platform_data
        
        if not default_content:
            default_content = "Published via AutoDubber"
        
        # Prepare platform list
        platform_list = []
        for platform in platforms:
            account_id = PLATFORM_ACCOUNTS.get(platform)
            if account_id:
                platform_entry = {
                    "platform": platform,
                    "accountId": account_id
                }
                
                # Add platform-specific content if different from default
                platform_content = platform_specific_contents.get(platform, "")
                if platform_content and platform_content != default_content:
                    platform_entry["platformSpecificContent"] = platform_content
                
                # Add YouTube-specific fields
                if platform == "youtube":
                    yt_data = captions.get("youtube", {})
                    if isinstance(yt_data, dict) and yt_data.get("title"):
                        platform_entry["youtubeTitle"] = yt_data["title"]
                
                platform_list.append(platform_entry)
                log("PUBLISH", f"  ✅ {platform}: {account_id}")
            else:
                log("PUBLISH", f"  ❌ {platform}: No account ID configured")
        
        if not platform_list:
            error_msg = "No valid platform accounts configured"
            log("PUBLISH", f"❌ {error_msg}")
            return {"error": error_msg}
        
        if progress_cb:
            progress_cb(1, len(platforms), "sdk", "uploading_media")
        
        if progress_cb:
            progress_cb(2, len(platforms), "sdk", "creating_post")
        
        log("PUBLISH", f"🚀 Creating post for {len(platform_list)} platforms...")
        log("PUBLISH", f"  Content: {default_content[:100]}...")
        log("PUBLISH", f"  Media: {len(media_urls)} files")
        log("PUBLISH", f"  Platforms: {[p['platform'] for p in platform_list]}")
        log("PUBLISH", f"  Publish Now: {publish_now}")
        
        # Debug: Print the exact SDK call
        if media_urls:
            log("PUBLISH", f"  SDK Call: client.posts.create(media_urls={len(media_urls)} files, content={len(default_content)} chars, platforms={len(platform_list)} platforms)")
        else:
            log("PUBLISH", f"  SDK Call: client.posts.create(content={len(default_content)} chars, platforms={len(platform_list)} platforms)")
        
        # Create the post - handle media requirements per platform
        try:
            if media_urls:
                # All platforms can post with media
                log("PUBLISH", f"🚀 Starting SDK call...")
                log("PUBLISH", f"  📱 Platforms: {[p['platform'] for p in platform_list]}")
                log("PUBLISH", f"  🎬 Media URLs: {len(media_urls)} items")
                log("PUBLISH", f"  📄 Media URLs: {media_urls}")
                log("PUBLISH", f"  ⏰ Publish now: {publish_now}")
                log("PUBLISH", f"  📞 Calling client.posts.create()...")
                
                post_result = client.posts.create(
                    content=default_content,
                    media_urls=media_urls,  # Use list format: [public_url]
                    platforms=platform_list,
                    publish_now=publish_now
                )
                
                log("PUBLISH", f"  ✅ SDK call returned: {type(post_result)}")
            else:
                # Filter platforms that don't require media
                # Instagram, Facebook, Threads, Twitter, Bluesky support images
                # YouTube and Tiktok require video
                video_required_platforms = ["youtube", "tiktok"]
                platforms_without_media = [
                    p for p in platform_list 
                    if p["platform"] not in video_required_platforms
                ]
                
                if not platforms_without_media:
                    error_msg = "No media uploaded but all selected platforms require video (youtube, tiktok)"
                    log("PUBLISH", f"❌ {error_msg}")
                    return {"error": error_msg}
                
                log("PUBLISH", f"⚠️ No media - posting only to image/text platforms: {[p['platform'] for p in platforms_without_media]}")
                log("PUBLISH", f"⚠️ Skipped video-required platforms: {[p for p in video_required_platforms if any(p2['platform'] == p for p2 in platform_list)]}")
                
                post_result = client.posts.create(
                    content=default_content,
                    platforms=platforms_without_media,
                    publish_now=publish_now
                )
            
            # Add scheduling if needed (separate from main call)
            if scheduled_for and hasattr(post_result, 'post'):
                # For scheduled posts, we might need to create differently
                log("PUBLISH", f"⚠️ Scheduling not fully implemented - using immediate publish")
                
            log("PUBLISH", f"  ✅ SDK call successful: {type(post_result)}")
            
        except ZernioAuthenticationError as e:
            log("PUBLISH", f"  ❌ Authentication failed: Invalid API key - {e}")
            raise ZernioAuthenticationError("Invalid Zernio API key. Please check your API key in the settings.")
        except ZernioRateLimitError as e:
            log("PUBLISH", f"  ❌ Rate limit exceeded: {e}")
            raise ZernioRateLimitError("Rate limit exceeded. Please wait before trying again.")
        except ZernioTimeoutError as e:
            log("PUBLISH", f"  ❌ Request timeout: {e}")
            raise ZernioTimeoutError("Request timed out. Please check your connection and try again.")
        except ZernioConnectionError as e:
            log("PUBLISH", f"  ❌ Connection error: {e}")
            raise ZernioConnectionError("Failed to connect to Zernio. Please check your internet connection.")
        except ZernioAPIError as e:
            log("PUBLISH", f"  ❌ API error: {e}")
            raise ZernioAPIError(f"Zernio API error: {e}")
        except Exception as sdk_error:
            log("PUBLISH", f"  ❌ Unexpected SDK error: {sdk_error}")
            raise sdk_error
        
        if progress_cb:
            progress_cb(len(platforms), len(platforms), "sdk", "completed")
        
        # Extract results - handle actual SDK response format
        try:
            log("PUBLISH", f"🔍 Starting response parsing...")
            log("PUBLISH", f"  📊 Response type: {type(post_result)}")
            log("PUBLISH", f"  📄 Response content: {str(post_result)[:200]}...")
            
            # The SDK returns PostCreateResponse objects with complex structure
            published_platforms = []
            
            if hasattr(post_result, 'post'):
                log("PUBLISH", f"  🔗 Found post object")
                post_obj = post_result.post
                if hasattr(post_obj, 'platforms'):
                    published_platforms = post_obj.platforms
                    log("PUBLISH", f"  📊 Got platforms from post.platforms: {len(published_platforms)}")
                    log("PUBLISH", f"  📋 Platform objects: {published_platforms}")
                else:
                    log("PUBLISH", f"  ❌ No platforms attribute on post object")
                    log("PUBLISH", f"  🔍 Post object attributes: {[attr for attr in dir(post_obj) if not attr.startswith('_')]}")
            elif isinstance(post_result, dict):
                log("PUBLISH", f"  📦 Response is dict")
                post = post_result.get('post', {})
                published_platforms = post.get('platforms', [])
                log("PUBLISH", f"  📊 Got platforms from dict: {len(published_platforms)}")
                log("PUBLISH", f"  📋 Dict keys: {list(post_result.keys())}")
            else:
                log("PUBLISH", f"  ❌ Unknown response format: {type(post_result)}")
                log("PUBLISH", f"  🔍 Available attributes: {[attr for attr in dir(post_result) if not attr.startswith('_')]}")
                
            log("PUBLISH", f"  📊 Response type: {type(post_result)}")
            log("PUBLISH", f"  📊 Platforms in response: {len(published_platforms)}")
            
        except Exception as e:
            log("PUBLISH", f"  ❌ Error parsing response: {e}")
            import traceback
            traceback.print_exc()
            published_platforms = []
        
        results = {}
        for i, platform_info in enumerate(published_platforms):
            try:
                # Handle SDK PlatformTarget objects
                if hasattr(platform_info, 'platform'):
                    platform_name = platform_info.platform
                    post_id = getattr(platform_info, 'platformPostId', 'unknown')
                    status = getattr(platform_info, 'status', 'unknown')
                elif isinstance(platform_info, dict):
                    platform_name = platform_info.get("platform", "unknown")
                    post_id = platform_info.get("platformPostId", platform_info.get("id", platform_info.get("_id", "unknown")))
                    status = platform_info.get("status", "unknown")
                else:
                    platform_name = "unknown"
                    post_id = "unknown"
                    status = "error"
                
                # Update progress for this platform
                if progress_cb:
                    log("PUBLISH", f"  📱 Updating progress: {platform_name} -> {status}")
                    if status == 'published':
                        progress_cb(i+1, len(published_platforms), platform_name, "ok")
                    elif status == 'error' or status == 'failed':
                        progress_cb(i+1, len(published_platforms), platform_name, "error")
                    else:
                        progress_cb(i+1, len(published_platforms), platform_name, "posting")
                
                success = status == 'published' or (post_id and post_id != "unknown")
                
                results[platform_name] = {
                    "status": "ok" if success else "error",
                    "post_id": post_id,
                    "platform": platform_name
                }
                
                log("PUBLISH", f"  ✅ {platform_name}: {'ok' if success else 'error'} (ID: {post_id})")
                
            except Exception as e:
                log("PUBLISH", f"  ❌ Error processing platform {platform_info}: {e}")
        
        log("PUBLISH", f"🎉 SDK publishing completed! {len(results)} platforms")
        return results
        
    except Exception as e:
        error_msg = f"SDK publishing failed: {str(e)}"
        log("PUBLISH", f"❌ {error_msg}")
        if progress_cb:
            progress_cb(len(platforms), len(platforms), "sdk", "error")
        return {"error": error_msg}

# Simple wrapper function for app.py
def publish_to_platforms_sdk(api_key, video_path, captions, platforms,
                            scheduled_for=None, publish_now=True,
                            teaser_path=None, teaser_paths=None,
                            teaser_captions=None, image_paths=None,
                            output_dir="workspace", progress_cb=None, fallback_files=None):
    """
    Simplified publishing using Zernio SDK
    """
    log("PUBLISH", f"🚀 STARTING publish_to_platforms_sdk")
    log("PUBLISH", f"  📹 Video path: {video_path}")
    log("PUBLISH", f"  📱 Platforms: {platforms}")
    log("PUBLISH", f"  📄 Fallback files: {list(fallback_files.keys()) if fallback_files else None}")
    
    try:
        # For now, we'll use upload_results if available, otherwise fallback to direct upload
        result = publish_with_sdk(
            api_key=api_key,
            captions=captions,
            platforms=platforms,
            scheduled_for=scheduled_for,
            publish_now=publish_now,
            output_dir=output_dir,
            progress_cb=progress_cb,
            fallback_files=fallback_files  # Pass through fallback files
        )
        log("PUBLISH", f"✅ publish_to_platforms_sdk COMPLETED")
        return result
    except Exception as e:
        log("PUBLISH", f"❌ publish_to_platforms_sdk FAILED: {e}")
        import traceback
        traceback.print_exc()
        raise e
