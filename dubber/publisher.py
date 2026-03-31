import os, json, time, requests, asyncio
from .utils import log, PLATFORM_ACCOUNTS, PLATFORM_LIMITS

BASE_URL = "https://zernio.com/api/v1"

POST_TIMEOUT = 120  # 2 minutes per platform (reduced from 8 minutes)

# Platform-specific timeouts (in seconds)
PLATFORM_TIMEOUTS = {
    "bluesky": 180,  # 3 minutes for Bluesky (reduced from 10 minutes)
    # Other platforms use default POST_TIMEOUT (120s)
}


# ─────────────────────────── helpers ────────────────────────────

def _auth(api_key):
    return {"Authorization": f"Bearer {api_key}"}

def _json_headers(api_key):
    return {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

def _extract_str(val):
    if isinstance(val, str): return val
    if isinstance(val, dict):
        for k in ("caption","text","content"):
            v = val.get(k)
            if isinstance(v, str): return v
    return str(val) if val else ""

def _trim(text, platform):
    text  = _extract_str(text)
    limit = PLATFORM_LIMITS.get(platform, 2000)
    return text[:limit-1] + "…" if len(text) > limit else text

def _mime(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    return {
        ".jpg":"image/jpeg",".jpeg":"image/jpeg",
        ".png":"image/png", ".gif":"image/gif",
        ".webp":"image/webp",".mp4":"video/mp4",
        ".mov":"video/quicktime",".avi":"video/x-msvideo",
        ".webm":"video/webm",
    }.get(ext, "application/octet-stream")

def _media_type(file_path):
    ext = os.path.splitext(file_path)[1].lower()
    return "video" if ext in {".mp4",".mov",".avi",".webm"} else "image"


# ─────────────────────────── per-platform lock ──────────────────

def _lock_path(output_dir):
    return os.path.join(output_dir, "published.lock")

def _read_lock(output_dir):
    """Returns dict of { platform: { status, post_id, timestamp } }"""
    path = _lock_path(output_dir)
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return {}

def _write_platform_lock(output_dir, platform, status, post_id=None):
    """
    Writes a single platform entry into the lock file.
    status: 'ok' | 'timeout-unconfirmed'
    Reads existing lock, updates the one platform, writes back.
    """
    os.makedirs(output_dir, exist_ok=True)
    lock = _read_lock(output_dir)
    lock[platform] = {
        "status":    status,
        "post_id":   post_id or "unknown",
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    with open(_lock_path(output_dir), "w") as f:
        json.dump(lock, f, indent=2)
    log("PUBLISH", f"  Lock [{platform}] = {status}")


async def _post_to_single_platform(api_key, platform, captions, media_items, 
                               publish_now, scheduled_for, output_dir, 
                               progress_cb, done_count, total_count, teaser_public_urls):
    """Async function to post to a single platform"""
    try:
        entry = _build_entry(platform, captions, teaser_public_urls)
        if not entry:
            result = {"error": "no account ID configured"}
            if progress_cb:
                progress_cb(done_count + 1, total_count, platform, "error")
            return platform, result

        payload = {
            "content":    "",           # customContent per platform overrides this
            "mediaItems": media_items,
            "platforms":  [entry],
        }
        if publish_now:
            payload["publishNow"] = True
        elif scheduled_for:
            payload["scheduledFor"] = scheduled_for

        # notify UI: this platform is now being posted
        if progress_cb:
            progress_cb(done_count + 1, total_count, platform, "posting")

        # Get platform-specific timeout
        platform_timeout = PLATFORM_TIMEOUTS.get(platform, POST_TIMEOUT)
        log("PUBLISH", f"  [{done_count+1}/{total_count}] Posting to {platform} (timeout: {platform_timeout}s) ...")

        # Run the blocking request in thread pool to avoid blocking event loop
        loop = asyncio.get_event_loop()
        r = await loop.run_in_executor(
            None, 
            lambda: requests.post(
                f"{BASE_URL}/posts",
                headers=_json_headers(api_key),
                json=payload,
                timeout=platform_timeout,
            )
        )
        
        log("PUBLISH", f"  -> HTTP {r.status_code}  body: {r.text[:200]}")

        if r.ok:
            result = r.json()
            post_id = (result.get("post") or {}).get("_id") or result.get("_id", "?")
            _write_platform_lock(output_dir, platform, "ok", post_id=post_id)
            log("PUBLISH", f"  {platform} OK -> id={post_id}")
            if progress_cb:
                progress_cb(done_count + 1, total_count, platform, "ok")
            return platform, result
        else:
            err = f"HTTP {r.status_code}: {r.text[:200]}"
            result = {"error": err}
            log("PUBLISH", f"  {platform} FAILED: {err}")
            if progress_cb:
                progress_cb(done_count + 1, total_count, platform, "error")
            return platform, result

    except requests.exceptions.ReadTimeout:
        # Timeout after GCS upload succeeded.
        # Post very likely went through — lock it to prevent retry double-post.
        log("PUBLISH", f"  {platform} TIMED OUT — locking as unconfirmed. Verify on Zernio.")
        result = {"error": "timeout-unconfirmed"}
        _write_platform_lock(output_dir, platform, "timeout-unconfirmed")
        if progress_cb:
            progress_cb(done_count + 1, total_count, platform, "timeout")
        return platform, result

    except Exception as e:
        log("PUBLISH", f"  {platform} exception: {e}")
        result = {"error": str(e)}
        if progress_cb:
            progress_cb(done_count + 1, total_count, platform, "error")
        return platform, result

def _platforms_already_done(output_dir, platforms):
    """
    Returns set of platforms already locked (ok or timeout-unconfirmed).
    These are skipped to prevent double-posting on retry.
    """
    lock = _read_lock(output_dir)
    done = set()
    for p in platforms:
        entry = lock.get(p)
        if entry and entry.get("status") in ("ok", "timeout-unconfirmed"):
            done.add(p)
            log("PUBLISH", f"  SKIP {p} — already locked as "
                           f"'{entry['status']}' at {entry.get('timestamp','?')} "
                           f"(id={entry.get('post_id','?')})")
    return done


# ─────────────────────────── media upload ───────────────────────

def upload_media(api_key, file_path):
    filename = os.path.basename(file_path)
    mime     = _mime(file_path)
    size_mb  = os.path.getsize(file_path) / (1024*1024)
    log("PUBLISH", f"Presign: {filename} [{mime}] {size_mb:.1f}MB")

    r = requests.post(
        f"{BASE_URL}/media/presign",
        headers=_json_headers(api_key),
        json={"filename": filename, "contentType": mime},
        timeout=30,
    )
    if not r.ok:
        raise RuntimeError(f"Presign failed [{r.status_code}]: {r.text[:400]}")

    data       = r.json()
    upload_url = data.get("uploadUrl")
    public_url = data.get("publicUrl")
    if not upload_url or not public_url:
        raise RuntimeError(f"Presign missing uploadUrl/publicUrl: {data}")

    log("PUBLISH", f"  Starting upload to GCS (timeout: 180s)...")
    start_time = time.time()
    with open(file_path, "rb") as f:
        put_r = requests.put(
            upload_url,
            headers={"Content-Type": mime},
            data=f,
            timeout=180,  # Reduced from 600s to 180s (3 minutes)
        )
    upload_time = time.time() - start_time
    
    if not put_r.ok:
        raise RuntimeError(f"GCS upload failed [{put_r.status_code}]: {put_r.text[:200]}")
    
    log("PUBLISH", f"  Upload completed in {upload_time:.1f}s -> {public_url[:72]}...")
    return public_url


# ─────────────────────────── account validation ─────────────────

def validate_accounts(api_key):
    try:
        r = requests.get(f"{BASE_URL}/accounts", headers=_auth(api_key), timeout=15)
        if not r.ok:
            log("PUBLISH", f"  Account validation skipped: {r.status_code}")
            return
        response_data = r.json()
        accounts = response_data if isinstance(response_data, list) else response_data.get("accounts", [])
        live_ids = {a.get("_id") or a.get("id") for a in accounts}
        for platform, acc_id in PLATFORM_ACCOUNTS.items():
            if acc_id not in live_ids:
                log("PUBLISH", f"  WARNING: account ID for {platform} ({acc_id}) not found in Zernio")
            else:
                log("PUBLISH", f"  OK: {platform} account verified")
    except Exception as e:
        log("PUBLISH", f"  Account validation error: {e}")


# ─────────────────────────── build single platform entry ────────

def _build_entry(platform, captions, teaser_public_urls=None):
    acc = PLATFORM_ACCOUNTS.get(platform)
    if not acc:
        log("PUBLISH", f"  No account ID for '{platform}' — skipping")
        return None

    pdata          = captions.get(platform, {})
    custom_content = _trim(
        pdata.get("caption", "") if isinstance(pdata, dict) else pdata, platform
    )

    entry = {
        "platform":      platform,
        "accountId":     acc,
        "customContent": custom_content,
    }

    if platform == "youtube":
        title = _extract_str(pdata.get("title", "")) if isinstance(pdata, dict) else ""
        if title: entry["title"] = title
        entry["visibility"] = "public"

    if platform == "tiktok":
        entry["privacyLevel"] = "PUBLIC_TO_EVERYONE"

    t_url = (teaser_public_urls or {}).get(platform)
    if t_url:
        entry["customMedia"] = [{"url": t_url, "type": "video"}]
        log("PUBLISH", f"  [{platform}] customMedia teaser attached")

    log("PUBLISH", f"  [{platform}] customContent={len(custom_content)}c")
    return entry


# ─────────────────────────── main publish ───────────────────────

async def _publish_to_platforms_async(api_key, video_path, captions, platforms, pending, already_done,
                                   scheduled_for=None, publish_now=True,
                                   teaser_path=None, teaser_paths=None,
                                   teaser_captions=None, image_paths=None,
                                   output_dir="workspace",
                                   progress_cb=None):
    """Async version of publish_to_platforms for parallel execution"""
    
    # ── upload primary video once (shared across all platforms) ──
    primary_url = upload_media(api_key, video_path)
    media_items = [{"url": primary_url, "type": _media_type(video_path)}]
    print(f"DEBUG: Primary media uploaded: {media_items[0]}")

    # ── upload extra images ──
    for img in (image_paths or []):
        if img and os.path.exists(img):
            try:
                url = upload_media(api_key, img)
                media_items.append({"url": url, "type": "image"})
                print(f"DEBUG: Extra image uploaded: {url}")
            except Exception as e:
                log("PUBLISH", f"  Extra image upload failed: {e}")
    
    print(f"DEBUG: Total media_items: {len(media_items)}")
    for i, item in enumerate(media_items):
        print(f"  Media {i+1}: {item}")

    # ── upload per-platform teasers ──
    teaser_public_urls = {}
    if teaser_paths:
        for p, t_path in teaser_paths.items():
            if t_path and os.path.exists(t_path):
                try:
                    teaser_public_urls[p] = upload_media(api_key, t_path)
                except Exception as e:
                    log("PUBLISH", f"  Teaser upload failed for {p}: {e}")

    # Create async tasks for all platforms
    tasks = []
    for i, platform in enumerate(pending):
        task = _post_to_single_platform(
            api_key, platform, captions, media_items,
            publish_now, scheduled_for, output_dir,
            progress_cb, len(already_done) + i, len(platforms), teaser_public_urls
        )
        tasks.append(task)

    # Wait for all platforms to complete concurrently
    results_list = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Convert results list back to dict format
    results = {}
    for result in results_list:
        if isinstance(result, Exception):
            log("PUBLISH", f"  Unexpected error: {result}")
            continue
        platform, platform_result = result
        results[platform] = platform_result

    return results


def publish_to_platforms(api_key, video_path, captions, platforms,
                          scheduled_for=None, publish_now=True,
                          teaser_path=None, teaser_paths=None,
                          teaser_captions=None, image_paths=None,
                          output_dir="workspace",
                          progress_cb=None):
    """
    Posts to all platforms in parallel using asyncio.

    progress_cb(done, total, platform, status)
        done     = number completed so far
        total    = total platforms requested (including skipped)
        platform = current platform name
        status   = 'posting' | 'ok' | 'timeout' | 'error' | 'skipped'
    """
    if not api_key:
        raise RuntimeError("No Zernio API key.")
    if not platforms:
        raise RuntimeError("No platforms selected.")
    if not video_path or not os.path.exists(video_path):
        raise RuntimeError(f"Primary media not found: {video_path}")

    validate_accounts(api_key)

    # ── duplicate guard: skip platforms already successfully posted ──
    already_done = _platforms_already_done(output_dir, platforms)
    pending      = [p for p in platforms if p not in already_done]

    # report skipped platforms to UI immediately
    if progress_cb:
        for p in already_done:
            progress_cb(0, len(platforms), p, "skipped")

    if not pending:
        log("PUBLISH", "All platforms already published — nothing to do.")
        return {"skipped": True, "reason": "all_already_published"}

    # Run async version and return results
    return asyncio.run(_publish_to_platforms_async(
        api_key, video_path, captions, platforms, pending, already_done,
        scheduled_for, publish_now, teaser_path, teaser_paths,
        teaser_captions, image_paths, output_dir, progress_cb
    ))