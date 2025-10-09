# Auto Video Uploader

Automatic video uploader for YouTube, Rumble, and PeerTube platforms.

## Setup

1. Clone the repository
2. Copy `.env.example` to `.env` and configure:
   ```bash
   cp .env.example .env
   ```
3. Edit `.env` and set the path to your Bitcoin Education Content repository:
   ```
   BEC_REPO=/path/to/bitcoin_education_content
   ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. Place video files in subfolders under `./inputs/`
2. Video filenames must follow this format: `{course_index}_{part}.{chapter}_{language}.mp4`
   - Example: `btc101_1.1_FR.mp4`
3. Run the metadata extractor:
   ```bash
   python main.py
   ```
4. Select the subfolder to process
5. The tool will extract metadata and display:
   - Video title (e.g., "[BTC 101] - 1.1 - Chapter Title")
   - Description (e.g., "BTC 101 -- Course Title")

## Project Structure

```
auto-video-uploader/
├── inputs/              # Place video subfolders here
├── src/
│   └── metadata_extractor.py
├── main.py
├── .env
└── requirements.txt
```