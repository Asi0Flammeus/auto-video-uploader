from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass

from src.metadata_extractor import VideoMetadata
from src.youtube_uploader import YouTubeUploader, YouTubeUploadResult
from src.peertube_uploader import PeerTubeUploader, PeerTubeUploadResult


@dataclass
class UploadResult:
    filename: str
    title: str
    youtube_success: bool
    peertube_success: bool
    youtube_url: Optional[str] = None
    youtube_error: Optional[str] = None
    peertube_url: Optional[str] = None
    peertube_error: Optional[str] = None


class UploadOrchestrator:
    def __init__(self,
                 youtube_uploader: Optional[YouTubeUploader] = None,
                 peertube_uploader: Optional[PeerTubeUploader] = None):
        """
        Initialize upload orchestrator

        Args:
            youtube_uploader: Configured YouTube uploader instance
            peertube_uploader: Configured PeerTube uploader instance
        """
        self.youtube_uploader = youtube_uploader
        self.peertube_uploader = peertube_uploader

    def upload_video(self, video_path: Path, metadata: VideoMetadata,
                     upload_to_youtube: bool = True,
                     upload_to_peertube: bool = True) -> UploadResult:
        """
        Upload a single video to configured platforms

        Args:
            video_path: Path to video file
            metadata: Video metadata
            upload_to_youtube: Whether to upload to YouTube
            upload_to_peertube: Whether to upload to PeerTube

        Returns:
            UploadResult with status for each platform
        """
        result = UploadResult(
            filename=metadata.filename,
            title=metadata.title,
            youtube_success=False,
            peertube_success=False
        )

        # Upload to YouTube
        if upload_to_youtube and self.youtube_uploader:
            print(f"  Uploading to YouTube...")
            yt_result = self.youtube_uploader.upload_video(
                video_path=video_path,
                title=metadata.title,
                description=metadata.description,
                privacy_status="unlisted"
            )

            result.youtube_success = yt_result.success
            result.youtube_url = yt_result.video_url
            result.youtube_error = yt_result.error

            if yt_result.success:
                print(f"  ✅ YouTube: {yt_result.video_url}")
            else:
                print(f"  ❌ YouTube: {yt_result.error}")

        # Upload to PeerTube
        if upload_to_peertube and self.peertube_uploader:
            print(f"  Uploading to PeerTube...")
            pt_result = self.peertube_uploader.upload_video(
                video_path=video_path,
                title=metadata.title,
                description=metadata.description,
                privacy=2  # Unlisted
            )

            result.peertube_success = pt_result.success
            result.peertube_url = pt_result.video_url
            result.peertube_error = pt_result.error

            if pt_result.success:
                print(f"  ✅ PeerTube: {pt_result.video_url}")
            else:
                print(f"  ❌ PeerTube: {pt_result.error}")

        return result

    def upload_batch(self, video_folder: Path, metadata_list: List[VideoMetadata],
                     upload_to_youtube: bool = True,
                     upload_to_peertube: bool = True) -> List[UploadResult]:
        """
        Upload multiple videos from a folder

        Args:
            video_folder: Folder containing video files
            metadata_list: List of video metadata
            upload_to_youtube: Whether to upload to YouTube
            upload_to_peertube: Whether to upload to PeerTube

        Returns:
            List of UploadResult for each video
        """
        results = []

        for i, metadata in enumerate(metadata_list, 1):
            print(f"\n[{i}/{len(metadata_list)}] Processing: {metadata.filename}")
            print(f"  Title: {metadata.title}")

            video_path = video_folder / metadata.filename

            if not video_path.exists():
                print(f"  ❌ Video file not found: {video_path}")
                results.append(UploadResult(
                    filename=metadata.filename,
                    title=metadata.title,
                    youtube_success=False,
                    youtube_error="File not found",
                    peertube_success=False,
                    peertube_error="File not found"
                ))
                continue

            result = self.upload_video(
                video_path=video_path,
                metadata=metadata,
                upload_to_youtube=upload_to_youtube,
                upload_to_peertube=upload_to_peertube
            )

            results.append(result)

        return results

    def authenticate_platforms(self) -> Dict[str, bool]:
        """
        Authenticate with all configured platforms

        Returns:
            Dictionary with authentication status for each platform
        """
        auth_status = {}

        if self.youtube_uploader:
            print("Authenticating with YouTube...")
            try:
                auth_status['youtube'] = self.youtube_uploader.authenticate()
                if auth_status['youtube']:
                    print("✅ YouTube authentication successful")
                else:
                    print("❌ YouTube authentication failed")
            except Exception as e:
                print(f"❌ YouTube authentication error: {e}")
                auth_status['youtube'] = False

        if self.peertube_uploader:
            print("Authenticating with PeerTube...")
            try:
                auth_status['peertube'] = self.peertube_uploader.authenticate()
                if auth_status['peertube']:
                    print("✅ PeerTube authentication successful")
                else:
                    print("❌ PeerTube authentication failed")
            except Exception as e:
                print(f"❌ PeerTube authentication error: {e}")
                auth_status['peertube'] = False

        return auth_status
