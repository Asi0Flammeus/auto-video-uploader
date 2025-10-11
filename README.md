# Auto Video Uploader

## Context

This project is designed to batch upload translated videos produced by [Plan B Network](https://planb.network) to the [Bitcoin Education Content repository](https://github.com/PlanB-Network/bitcoin-educational-content). Plan B Network provides Bitcoin education translated into multiple languages, and this tool automates the process of uploading these educational videos to multiple platforms while maintaining proper metadata and organization.

## Features

- 📝 **Metadata Extraction**: Automatically extracts course and chapter titles from BEC repository
- 🎬 **YouTube Upload**: Upload videos with OAuth2 authentication and unlisted privacy
- 🔵 **PeerTube Upload**: Upload videos to your own PeerTube instance
- 🚀 **Batch Processing**: Process and upload multiple videos at once
- 📊 **Progress Tracking**: See upload status and results for each platform

## Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` and configure:

```bash
# Required: Path to Bitcoin Education Content repository
BEC_REPO=/path/to/bitcoin_education_content

# YouTube OAuth2 credentials
YOUTUBE_CLIENT_SECRETS_FILE=/path/to/client_secrets.json

# PeerTube instance credentials
PEERTUBE_INSTANCE=https://your-peertube-instance.com
PEERTUBE_USERNAME=your_username
PEERTUBE_PASSWORD=your_password
```

### 3. Set Up YouTube Authentication

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable the **YouTube Data API v3**
4. Create OAuth 2.0 credentials:
   - Go to **APIs & Services** → **Credentials**
   - Click **Create Credentials** → **OAuth client ID**
   - Choose **Desktop app** as application type
   - Download the JSON file
5. Set `YOUTUBE_CLIENT_SECRETS_FILE` in `.env` to point to this JSON file

### 4. Set Up PeerTube Authentication

1. Log in to your PeerTube instance
2. Use your username and password in the `.env` file
3. Ensure your account has permission to upload videos

## Usage

### 1. Prepare Videos

Place video files in subfolders under `./inputs/`. Video filenames must follow this format:

```
{course_index}_{part}.{chapter}_{language}.mp4
```

**Example:** `btc101_1.1_FR.mp4`

### 2. Run the Tool

```bash
python main.py
```

### 3. Follow the Workflow

1. **Select Subfolder**: Choose which folder to process
2. **Review Metadata**: The tool will extract and display:
   - Video title: `[BTC 101] - 1.1 - Chapter Title`
   - Description: `BTC 101 -- Course Title`
3. **Save Metadata** (optional): Export to JSON file
4. **Upload Videos**: Choose whether to upload
   - First-time YouTube users will be prompted to authenticate via browser
   - Videos will upload to both platforms with **unlisted** privacy

### 4. Review Results

The tool will display:

- ✅ Successful uploads with video URLs
- ❌ Failed uploads with error messages
- 📊 Summary statistics for each platform

## Project Structure

```
auto-video-uploader/
├── inputs/                      # Place video subfolders here
│   └── subfolder/
│       ├── video1.mp4
│       ├── video2.mp4
│       └── metadata.json        # Generated metadata file
├── src/
│   ├── metadata_extractor.py   # Extract metadata from filenames
│   ├── youtube_uploader.py     # YouTube API integration
│   ├── peertube_uploader.py    # PeerTube API integration
│   └── upload_orchestrator.py  # Coordinate uploads
├── main.py                      # CLI interface
├── .env                         # Environment configuration
└── requirements.txt             # Python dependencies
```

## Troubleshooting

### YouTube Authentication Issues

- Ensure your OAuth2 credentials are for a **Desktop app**, not a web app
- Check that the YouTube Data API v3 is enabled in your Google Cloud project
- Delete `youtube_credentials.pickle` and re-authenticate if you encounter token errors

### PeerTube Upload Failures

- Verify your instance URL doesn't have a trailing slash
- Ensure your account has upload permissions
- Check that your instance allows the video file size and format

### Metadata Extraction Errors

- Verify `BEC_REPO` points to the correct Bitcoin Education Content repository
- Ensure video filenames follow the exact format: `{course}_{part}.{chapter}_{lang}.mp4`
- Check that the corresponding course markdown files exist in the BEC repository

## Privacy Settings

All videos are uploaded with **unlisted** privacy by default:

- **YouTube**: Unlisted (only people with the link can view)
- **PeerTube**: Unlisted (not shown in public listings)

## License

MIT License

