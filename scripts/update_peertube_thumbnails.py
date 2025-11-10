#!/usr/bin/env python3
"""
PeerTube Thumbnail Updater - Download video segments and generate thumbnails.

This module provides utilities to:
1. Get video file URLs from PeerTube
2. Download video segments (first N seconds)
3. Generate thumbnails from video segments
4. Upload thumbnails back to PeerTube
"""

import sys
import os
import requests
import tempfile
from pathlib import Path
from typing import Optional
import logging

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.thumbnail_generator import ThumbnailGenerator
from src.peertube_uploader import PeerTubeUploader

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PeerTubeThumbnailUpdater:
    """
    Handles thumbnail generation for PeerTube videos by downloading video segments
    and extracting frames.
    """

    def __init__(self, instance_url: str, username: str, password: str,
                 verify_ssl: bool = True):
        """
        Initialize PeerTube thumbnail updater.

        Args:
            instance_url: PeerTube instance URL (without trailing slash)
            username: PeerTube account username
            password: PeerTube account password
            verify_ssl: Whether to verify SSL certificates
        """
        self.instance_url = instance_url.rstrip('/')
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl

        # Initialize components
        self.thumbnail_generator = ThumbnailGenerator()
        self.uploader = None  # Can be set externally or created on demand

    def _ensure_uploader(self) -> bool:
        """
        Ensure uploader is initialized and authenticated.

        Returns:
            True if uploader is ready, False otherwise
        """
        if self.uploader is None:
            self.uploader = PeerTubeUploader(
                instance_url=self.instance_url,
                username=self.username,
                password=self.password,
                verify_ssl=self.verify_ssl
            )

        if not hasattr(self.uploader, 'access_token') or not self.uploader.access_token:
            return self.uploader.authenticate()

        return True

    def get_video_file_url(self, video_uuid: str) -> Optional[str]:
        """
        Get the direct video file URL from PeerTube API.

        Args:
            video_uuid: Video UUID or shortUUID

        Returns:
            Direct video file URL or None if failed
        """
        try:
            # Get video details from API
            api_url = f"{self.instance_url}/api/v1/videos/{video_uuid}"

            response = requests.get(
                api_url,
                verify=self.verify_ssl,
                timeout=30
            )

            if response.status_code != 200:
                logger.error(f"Failed to get video details: {response.status_code}")
                return None

            video_data = response.json()

            # Try to get video URL from files array (WebTorrent)
            files = video_data.get('files', [])
            if files:
                # Sort by resolution (highest first) and get the first one
                files_sorted = sorted(
                    files,
                    key=lambda x: x.get('resolution', {}).get('id', 0),
                    reverse=True
                )
                video_url = files_sorted[0].get('fileUrl')
                if video_url:
                    logger.info(f"Found video URL from files: {video_url}")
                    return video_url

            # Fallback to streaming playlists (HLS)
            streaming_playlists = video_data.get('streamingPlaylists', [])
            if streaming_playlists:
                # Get the first HLS playlist
                playlist = streaming_playlists[0]
                playlist_files = playlist.get('files', [])

                if playlist_files:
                    # Sort by resolution (highest first)
                    playlist_sorted = sorted(
                        playlist_files,
                        key=lambda x: x.get('resolution', {}).get('id', 0),
                        reverse=True
                    )
                    video_url = playlist_sorted[0].get('fileUrl')
                    if video_url:
                        logger.info(f"Found video URL from streaming playlist: {video_url}")
                        return video_url

                # If no files in playlist, try to use the playlist URL itself
                playlist_url = playlist.get('playlistUrl')
                if playlist_url:
                    logger.info(f"Found HLS playlist URL: {playlist_url}")
                    return playlist_url

            logger.error("No video files or streaming playlists found")
            return None

        except Exception as e:
            logger.error(f"Error getting video file URL: {e}")
            return None

    def download_video_segment(self, video_url: str, duration: int = 10) -> Optional[Path]:
        """
        Download the first N seconds of a video from URL.

        Uses ffmpeg to download only the required segment, avoiding full download.

        Args:
            video_url: Direct URL to video file
            duration: Number of seconds to download (default: 10)

        Returns:
            Path to downloaded video segment or None if failed
        """
        import subprocess

        try:
            # Create temp file for video segment
            temp_fd, temp_path = tempfile.mkstemp(suffix='.mp4', prefix='video_segment_')
            os.close(temp_fd)
            segment_path = Path(temp_path)

            logger.info(f"Downloading first {duration} seconds from {video_url[:50]}...")

            # Use ffmpeg to download only the first N seconds
            cmd = [
                'ffmpeg',
                '-y',                           # Overwrite output
                '-reconnect', '1',              # Enable reconnection
                '-reconnect_at_eof', '1',       # Reconnect at EOF
                '-reconnect_streamed', '1',     # Reconnect for streamed protocols
                '-reconnect_delay_max', '5',    # Max reconnect delay
                '-timeout', '10000000',         # 10 second timeout (microseconds)
                '-i', video_url,                # Input URL
                '-t', str(duration),            # Duration to download
                '-c', 'copy',                   # Copy streams (no re-encoding)
                '-movflags', 'faststart',       # Enable progressive download
                str(segment_path)               # Output file
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120  # 2 minute timeout
            )

            if result.returncode != 0:
                logger.error(f"ffmpeg failed: {result.stderr}")
                if segment_path.exists():
                    segment_path.unlink()
                return None

            if not segment_path.exists():
                logger.error("Video segment file was not created")
                return None

            file_size = segment_path.stat().st_size
            if file_size < 1000:  # Less than 1KB is suspicious
                logger.error(f"Downloaded segment too small: {file_size} bytes")
                segment_path.unlink()
                return None

            logger.info(f"Downloaded {file_size / 1024 / 1024:.2f}MB video segment to {segment_path}")
            return segment_path

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout downloading video segment")
            if segment_path.exists():
                segment_path.unlink()
            return None
        except Exception as e:
            logger.error(f"Error downloading video segment: {e}")
            if 'segment_path' in locals() and segment_path.exists():
                segment_path.unlink()
            return None

    def process_video(self, video_uuid: str, timestamp: float = 4) -> bool:
        """
        Complete workflow: Download video segment, extract thumbnail, upload to PeerTube.

        Args:
            video_uuid: Video UUID or shortUUID
            timestamp: Time in seconds to extract thumbnail (default: 4)

        Returns:
            True if successful, False otherwise
        """
        # Ensure uploader is ready
        if not self._ensure_uploader():
            logger.error("Failed to authenticate with PeerTube")
            return False

        # Step 1: Get video URL
        logger.info(f"Step 1/4: Getting video file URL for {video_uuid}")
        video_url = self.get_video_file_url(video_uuid)
        if not video_url:
            return False

        # Step 2: Download video segment
        logger.info(f"Step 2/4: Downloading video segment")
        video_segment = self.download_video_segment(video_url, duration=10)
        if not video_segment:
            return False

        try:
            # Step 3: Extract thumbnail
            logger.info(f"Step 3/4: Extracting thumbnail at {timestamp}s")
            thumbnail_path = self.thumbnail_generator.extract_frame(
                video_path=video_segment,
                timestamp=timestamp
            )

            if not thumbnail_path:
                logger.error("Failed to extract thumbnail")
                return False

            try:
                # Step 4: Upload thumbnail
                logger.info(f"Step 4/4: Uploading thumbnail to PeerTube")
                success = self.uploader.upload_thumbnail(video_uuid, thumbnail_path)

                if success:
                    logger.info(f"✅ Successfully updated thumbnail for {video_uuid}")
                else:
                    logger.error(f"❌ Failed to upload thumbnail for {video_uuid}")

                return success

            finally:
                # Cleanup thumbnail
                if thumbnail_path.exists():
                    thumbnail_path.unlink()

        finally:
            # Cleanup video segment
            if video_segment.exists():
                video_segment.unlink()

    def cleanup(self):
        """Cleanup temporary files."""
        self.thumbnail_generator.cleanup_temp_files()


if __name__ == "__main__":
    """
    CLI for testing single video thumbnail updates.
    Usage: python update_peertube_thumbnails.py <video_uuid>
    """
    from dotenv import load_dotenv

    load_dotenv()

    if len(sys.argv) < 2:
        print("Usage: python update_peertube_thumbnails.py <video_uuid>")
        sys.exit(1)

    video_uuid = sys.argv[1]

    instance_url = os.getenv('PEERTUBE_INSTANCE', '').rstrip('/')
    username = os.getenv('PEERTUBE_USERNAME')
    password = os.getenv('PEERTUBE_PASSWORD')
    verify_ssl = os.getenv('PEERTUBE_VERIFY_SSL', 'true').lower() != 'false'

    if not all([instance_url, username, password]):
        print("❌ Missing environment variables")
        print("Required: PEERTUBE_INSTANCE, PEERTUBE_USERNAME, PEERTUBE_PASSWORD")
        sys.exit(1)

    print(f"🎬 Updating thumbnail for video: {video_uuid}")
    print(f"Instance: {instance_url}\n")

    updater = PeerTubeThumbnailUpdater(
        instance_url=instance_url,
        username=username,
        password=password,
        verify_ssl=verify_ssl
    )

    success = updater.process_video(video_uuid)

    updater.cleanup()

    if success:
        print("\n✅ Thumbnail updated successfully!")
        sys.exit(0)
    else:
        print("\n❌ Failed to update thumbnail")
        sys.exit(1)
