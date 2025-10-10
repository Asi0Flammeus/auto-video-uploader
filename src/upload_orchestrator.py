from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass

from src.metadata_extractor import VideoMetadata, MetadataExtractor
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

    def delete_existing_videos(self, metadata: VideoMetadata,
                               delete_youtube: bool = True,
                               delete_peertube: bool = True):
        """
        Delete existing videos from platforms

        Args:
            metadata: VideoMetadata with existing video IDs
            delete_youtube: Whether to delete from YouTube
            delete_peertube: Whether to delete from PeerTube
        """
        if delete_youtube and metadata.youtube_id and self.youtube_uploader:
            print(f"  Deleting existing YouTube video...")
            self.youtube_uploader.delete_video(metadata.youtube_id)

        if delete_peertube and metadata.peertube_id and self.peertube_uploader:
            print(f"  Deleting existing PeerTube video...")
            self.peertube_uploader.delete_video(metadata.peertube_id)

    def upload_video(self, video_path: Path, metadata: VideoMetadata,
                     upload_to_youtube: bool = True,
                     upload_to_peertube: bool = True,
                     replace_existing: bool = False) -> UploadResult:
        """
        Upload a single video to configured platforms

        Args:
            video_path: Path to video file
            metadata: Video metadata
            upload_to_youtube: Whether to upload to YouTube
            upload_to_peertube: Whether to upload to PeerTube
            replace_existing: If True, delete existing videos before uploading

        Returns:
            UploadResult with status for each platform
        """
        result = UploadResult(
            filename=metadata.filename,
            title=metadata.title,
            youtube_success=False,
            peertube_success=False
        )

        # If replacing, delete existing videos first
        if replace_existing:
            self.delete_existing_videos(
                metadata,
                delete_youtube=upload_to_youtube,
                delete_peertube=upload_to_peertube
            )
            # Clear the IDs since we deleted them
            metadata.youtube_id = None
            metadata.peertube_id = None

        # Append footer to description for upload
        footer = MetadataExtractor.get_description_footer()
        full_description = f"{metadata.description}{footer}"

        # Upload to YouTube
        if upload_to_youtube and self.youtube_uploader:
            print(f"  Uploading to YouTube...")
            yt_result = self.youtube_uploader.upload_video(
                video_path=video_path,
                title=metadata.title,
                description=full_description,
                privacy_status="unlisted"
            )

            result.youtube_success = yt_result.success
            result.youtube_url = yt_result.video_url
            result.youtube_error = yt_result.error

            if yt_result.success:
                print(f"  ✅ YouTube: {yt_result.video_url}")
                # Update metadata with YouTube ID
                metadata.youtube_id = yt_result.video_id

                # Add to playlist
                playlist_title = metadata.description  # Use base description as playlist name
                print(f"  Checking for playlist: {playlist_title}")

                playlist_id = self.youtube_uploader.get_playlist_by_title(playlist_title)

                if not playlist_id:
                    print(f"  Creating playlist: {playlist_title}")
                    playlist_id = self.youtube_uploader.create_playlist(
                        title=playlist_title,
                        description=f"Videos for {playlist_title}",
                        privacy="unlisted"
                    )

                if playlist_id:
                    self.youtube_uploader.add_video_to_playlist(playlist_id, yt_result.video_id)
            else:
                print(f"  ❌ YouTube: {yt_result.error}")

        # Upload to PeerTube
        if upload_to_peertube and self.peertube_uploader:
            print(f"  Uploading to PeerTube...")
            pt_result = self.peertube_uploader.upload_video(
                video_path=video_path,
                title=metadata.title,
                description=full_description,
                privacy=2  # Unlisted
            )

            result.peertube_success = pt_result.success
            result.peertube_url = pt_result.video_url
            result.peertube_error = pt_result.error

            if pt_result.success:
                print(f"  ✅ PeerTube: {pt_result.video_url}")
                # Update metadata with PeerTube ID
                metadata.peertube_id = pt_result.video_id

                # Add to playlist
                playlist_name = metadata.description  # Use base description as playlist name
                print(f"  Checking for playlist: {playlist_name}")

                playlist_id = self.peertube_uploader.get_playlist_by_name(playlist_name)

                if not playlist_id:
                    print(f"  Creating playlist: {playlist_name}")
                    playlist_id = self.peertube_uploader.create_playlist(
                        display_name=playlist_name,
                        description=f"Videos for {playlist_name}",
                        privacy=2  # Unlisted
                    )

                if playlist_id:
                    self.peertube_uploader.add_video_to_playlist(playlist_id, pt_result.video_id)
            else:
                print(f"  ❌ PeerTube: {pt_result.error}")

        return result

    def upload_batch(self, video_folder: Path, metadata_list: List[VideoMetadata],
                     upload_to_youtube: bool = True,
                     upload_to_peertube: bool = True,
                     skip_existing: bool = False,
                     replace_decisions: Dict[str, bool] = None) -> List[UploadResult]:
        """
        Upload multiple videos from a folder

        Args:
            video_folder: Folder containing video files
            metadata_list: List of video metadata
            upload_to_youtube: Whether to upload to YouTube
            upload_to_peertube: Whether to upload to PeerTube
            skip_existing: If True, skip videos already uploaded
            replace_decisions: Dict mapping filename to replace decision (True=replace, False=skip)

        Returns:
            List of UploadResult for each video
        """
        results = []

        for i, metadata in enumerate(metadata_list, 1):
            print(f"\n[{i}/{len(metadata_list)}] Processing: {metadata.filename}")
            print(f"  Title: {metadata.title}")

            # Check if we should skip this video
            if skip_existing and (metadata.youtube_id or metadata.peertube_id):
                print(f"  ⏭️  Skipping (already uploaded)")
                results.append(UploadResult(
                    filename=metadata.filename,
                    title=metadata.title,
                    youtube_success=False,
                    youtube_error="Skipped - already uploaded",
                    peertube_success=False,
                    peertube_error="Skipped - already uploaded"
                ))
                continue

            # Check if we should skip based on user decision
            if replace_decisions and metadata.filename in replace_decisions:
                if not replace_decisions[metadata.filename]:
                    print(f"  ⏭️  Skipping (user chose not to re-upload)")
                    results.append(UploadResult(
                        filename=metadata.filename,
                        title=metadata.title,
                        youtube_success=False,
                        youtube_error="Skipped by user",
                        peertube_success=False,
                        peertube_error="Skipped by user"
                    ))
                    continue

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

            # Determine if we should replace existing videos
            replace_existing = False
            if replace_decisions and metadata.filename in replace_decisions:
                replace_existing = replace_decisions[metadata.filename]

            result = self.upload_video(
                video_path=video_path,
                metadata=metadata,
                upload_to_youtube=upload_to_youtube,
                upload_to_peertube=upload_to_peertube,
                replace_existing=replace_existing
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
