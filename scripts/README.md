# Scripts Directory

Utility scripts for PeerTube thumbnail management and batch processing.

## Available Scripts

### 1. `update_peertube_thumbnails.py`

Core module for thumbnail generation and upload to PeerTube.

**Features:**
- Download video segments from PeerTube (first 10 seconds)
- Extract thumbnail frames at specified timestamps (default: 4 seconds)
- Upload generated thumbnails back to PeerTube
- Automatic cleanup of temporary files

**CLI Usage:**
```bash
# Update thumbnail for a single video
python scripts/update_peertube_thumbnails.py <video_uuid>

# Example
python scripts/update_peertube_thumbnails.py x1WgaJnsdrs9ZRqwcDnjWy
```

**Programmatic Usage:**
```python
from scripts.update_peertube_thumbnails import PeerTubeThumbnailUpdater

updater = PeerTubeThumbnailUpdater(
    instance_url="https://peertube.example.com",
    username="your_username",
    password="your_password",
    verify_ssl=True
)

# Process single video (download, extract, upload)
success = updater.process_video("video_uuid", timestamp=4)

# Cleanup when done
updater.cleanup()
```

---

### 2. `batch_process_metadata_thumbnails.py`

Batch process thumbnails for all PeerTube videos listed in `metadata.json`.

**Features:**
- Loads all videos with PeerTube IDs from `../metadata.json`
- Skips videos that already have `thumbnail: true` (resumable)
- Processes each video: download → extract → upload
- Updates `metadata.json` with `thumbnail: true` after each success
- Progress bar with live statistics
- Error tracking and reporting
- Automatic cleanup of temporary files

**Usage:**
```bash
python scripts/batch_process_metadata_thumbnails.py
```

**Output:**
```
============================================================
🎬 Batch PeerTube Thumbnail Processor
============================================================
Instance: https://peertube.planb.network
Source: /home/user/auto-video-uploader/metadata.json
============================================================

📥 Loading videos from metadata.json...
ℹ️  Skipped 498 videos with existing thumbnails
✅ Found 148 videos with PeerTube IDs

🔐 Authenticating with PeerTube...
✅ Authenticated successfully

⠙ Processing: [BTC 101] - 2.3 - Chapter Title (✅ 146 | ❌ 2) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 98% (146/148) 0:00:15

============================================================
📊 Summary
============================================================
Total videos: 148
✅ Processed: 146
❌ Failed: 2

⚠️  Errors:
  - [BTC 101] - 2.3 - Some Title: Processing failed
  - [BTC 201] - 1.1 - Another Title: Network timeout

============================================================

✅ Batch processing complete!
```

**Resumability:**

The script is fully resumable. After each successful thumbnail upload, it updates `metadata.json`:

```json
{
  "filename": "btc101_2.1_en.mp4",
  "title": "[BTC 101] - 2.1 - Chapter Title",
  "peertube_id": "x1WgaJnsdrs9ZRqwcDnjWy",
  "youtube_id": "abc123xyz",
  "thumbnail": true
}
```

If interrupted (Ctrl+C, network error, etc.), simply run the script again. It will:
- Skip all videos with `thumbnail: true`
- Resume processing remaining videos
- Display how many were skipped

---

## Requirements

### System Dependencies
- **ffmpeg**: Required for video processing and thumbnail extraction
  ```bash
  # Ubuntu/Debian
  sudo apt install ffmpeg

  # macOS
  brew install ffmpeg
  ```

### Python Dependencies
All dependencies are included in the main `requirements.txt`:
- `requests`: HTTP client for PeerTube API
- `python-dotenv`: Environment variable management

### Environment Variables
Configure in `.env`:
```bash
PEERTUBE_INSTANCE=https://peertube.planb.network
PEERTUBE_USERNAME=your_username
PEERTUBE_PASSWORD=your_password
PEERTUBE_VERIFY_SSL=true  # Optional, default: true
```

---

## How It Works

### Thumbnail Generation Workflow

1. **Get Video URL**
   - Query PeerTube API: `/api/v1/videos/{uuid}`
   - Select highest quality video file
   - Extract direct video file URL

2. **Download Video Segment**
   - Use ffmpeg to download first 10 seconds only (not full video)
   - Save to temporary file
   - Includes network retry logic for reliability

3. **Extract Thumbnail Frame**
   - Use ffmpeg to extract frame at 4 seconds
   - Scale to 1280x720 (or smaller if needed)
   - Compress to stay under 4MB PeerTube limit
   - Validate JPEG format

4. **Upload to PeerTube**
   - Use PeerTube API: `PUT /api/v1/videos/{uuid}`
   - Multipart form upload
   - Update video's preview/thumbnail

5. **Cleanup**
   - Remove temporary video segment
   - Remove temporary thumbnail file

---

## PeerTubeThumbnailUpdater Class

### Methods

#### `__init__(instance_url, username, password, verify_ssl=True)`
Initialize the updater with PeerTube credentials.

#### `get_video_file_url(video_uuid) -> Optional[str]`
Get the direct video file URL from PeerTube API.

**Parameters:**
- `video_uuid`: Video UUID or shortUUID

**Returns:**
- Direct video file URL or `None` if failed

#### `download_video_segment(video_url, duration=10) -> Optional[Path]`
Download the first N seconds of a video.

**Parameters:**
- `video_url`: Direct URL to video file
- `duration`: Number of seconds to download (default: 10)

**Returns:**
- Path to downloaded video segment or `None` if failed

#### `process_video(video_uuid, timestamp=4) -> bool`
Complete workflow: download → extract → upload.

**Parameters:**
- `video_uuid`: Video UUID or shortUUID
- `timestamp`: Time in seconds to extract thumbnail (default: 4)

**Returns:**
- `True` if successful, `False` otherwise

#### `cleanup()`
Remove all temporary files created during processing.

---

## Error Handling

The scripts include comprehensive error handling:
- Network timeouts and retry logic
- Invalid video file detection
- File size validation (4MB limit)
- JPEG format validation
- Graceful cleanup on failures

Common errors and solutions:
- **"Failed to get video details"**: Check video UUID and API access
- **"ffmpeg timeout"**: Network issue, try again or increase timeout
- **"Thumbnail too large"**: Automatically reduces quality/resolution
- **"Invalid JPEG file format"**: Frame extraction failed, check video codec

---

## Performance Considerations

- **Bandwidth**: Downloads ~5-20MB per video (10 second segment)
- **Processing Time**: ~10-30 seconds per video
- **Concurrency**: Scripts run serially (one video at a time)
- **Temp Storage**: ~10-50MB per video during processing (auto-cleaned)

For large batches (>100 videos), consider:
- Running during off-peak hours
- Monitoring disk space
- Checking network bandwidth limits

---

## Examples

### Process Single Video with Custom Timestamp
```python
from scripts.update_peertube_thumbnails import PeerTubeThumbnailUpdater
import os
from dotenv import load_dotenv

load_dotenv()

updater = PeerTubeThumbnailUpdater(
    instance_url=os.getenv('PEERTUBE_INSTANCE'),
    username=os.getenv('PEERTUBE_USERNAME'),
    password=os.getenv('PEERTUBE_PASSWORD')
)

# Extract thumbnail at 6 seconds instead of default 4
success = updater.process_video("x1WgaJnsdrs9ZRqwcDnjWy", timestamp=6)
updater.cleanup()
```

### Batch Process Specific Videos
```python
from scripts.update_peertube_thumbnails import PeerTubeThumbnailUpdater
import os
from dotenv import load_dotenv

load_dotenv()

updater = PeerTubeThumbnailUpdater(
    instance_url=os.getenv('PEERTUBE_INSTANCE'),
    username=os.getenv('PEERTUBE_USERNAME'),
    password=os.getenv('PEERTUBE_PASSWORD')
)

video_uuids = [
    "x1WgaJnsdrs9ZRqwcDnjWy",
    "6fuNmLp33ERR92sJeBSaJu",
    "t4x9WLZLGA5egVomi2U9f3"
]

for uuid in video_uuids:
    print(f"Processing {uuid}...")
    success = updater.process_video(uuid)
    print(f"  {'✅ Success' if success else '❌ Failed'}")

updater.cleanup()
```

---

## Troubleshooting

### ffmpeg not found
```bash
# Install ffmpeg
sudo apt install ffmpeg  # Ubuntu/Debian
brew install ffmpeg      # macOS
```

### Authentication fails
- Check `PEERTUBE_USERNAME` and `PEERTUBE_PASSWORD` in `.env`
- Verify account has upload permissions
- Test credentials manually via PeerTube web interface

### Network timeouts
- Increase timeout values in code
- Check network connectivity to PeerTube instance
- Verify `PEERTUBE_VERIFY_SSL` setting if using self-signed certificates

### Thumbnail quality issues
- Adjust timestamp (try different seconds: 2, 4, 6, etc.)
- Check source video quality
- Manually review extracted thumbnail before upload
