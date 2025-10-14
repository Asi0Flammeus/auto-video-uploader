from pathlib import Path
from typing import List, Optional, Dict
from dataclasses import dataclass

from src.metadata_extractor import VideoMetadata, MetadataExtractor
from src.youtube_uploader import YouTubeUploader, YouTubeUploadResult
from src.peertube_uploader import PeerTubeUploader, PeerTubeUploadResult
from src.course_yml_updater import CourseYmlUpdater


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
                 peertube_uploader: Optional[PeerTubeUploader] = None,
                 course_yml_updater: Optional[CourseYmlUpdater] = None):
        """
        Initialize upload orchestrator

        Args:
            youtube_uploader: Configured YouTube uploader instance
            peertube_uploader: Configured PeerTube uploader instance
            course_yml_updater: CourseYmlUpdater instance for updating BEC repo
        """
        self.youtube_uploader = youtube_uploader
        self.peertube_uploader = peertube_uploader
        self.course_yml_updater = course_yml_updater

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
                     metadata_manager,
                     upload_to_youtube: bool = True,
                     upload_to_peertube: bool = True,
                     peertube_only_mode: bool = False) -> List[UploadResult]:
        """
        Upload multiple videos from a folder with automatic replacement detection

        Args:
            video_folder: Folder containing video files
            metadata_list: List of video metadata for new videos
            metadata_manager: MetadataManager instance for checking existing uploads
            upload_to_youtube: Whether to upload to YouTube
            upload_to_peertube: Whether to upload to PeerTube
            peertube_only_mode: If True, only consider PeerTube for all decisions (ignore YouTube entirely)

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

            # Priority 1: Check for content replacement (same course+part+chapter+language but different hash)
            existing_entry = metadata_manager.find_by_course_part_chapter_language(
                metadata.course_index,
                metadata.part_index,
                metadata.chapter_index,
                metadata.code_language
            )

            if existing_entry and existing_entry.sha256_hash != metadata.sha256_hash:
                # Found existing video with same course+part+chapter+language but different content
                print(f"  🔄 Replacing existing video (content changed)")
                print(f"    Old: {existing_entry.filename} (hash: {existing_entry.sha256_hash[:16]}...)")
                print(f"    New: {metadata.filename} (hash: {metadata.sha256_hash[:16]}...)")

                # Copy existing IDs before replacing (so we can delete them)
                old_youtube_id = existing_entry.youtube_id
                old_peertube_id = existing_entry.peertube_id

                # Delete old videos from platforms (respect peertube_only_mode)
                if not peertube_only_mode and old_youtube_id and upload_to_youtube and self.youtube_uploader:
                    print(f"  Deleting old YouTube video...")
                    self.youtube_uploader.delete_video(old_youtube_id)

                if old_peertube_id and upload_to_peertube and self.peertube_uploader:
                    print(f"  Deleting old PeerTube video...")
                    self.peertube_uploader.delete_video(old_peertube_id)

                # Upload new video to configured platforms
                result = self.upload_video(
                    video_path=video_path,
                    metadata=metadata,
                    upload_to_youtube=upload_to_youtube and not peertube_only_mode,
                    upload_to_peertube=upload_to_peertube,
                    replace_existing=False  # Already deleted manually
                )

            # Priority 2: Check if hash exists in metadata.json
            elif metadata.sha256_hash:
                existing_by_hash = metadata_manager.find_by_hash(metadata.sha256_hash)

                if not existing_by_hash:
                    # New video (hash not found)
                    print(f"  📤 New video (hash not found in metadata.json)")
                    result = self.upload_video(
                        video_path=video_path,
                        metadata=metadata,
                        upload_to_youtube=upload_to_youtube and not peertube_only_mode,
                        upload_to_peertube=upload_to_peertube,
                        replace_existing=False
                    )

                else:
                    # Priority 3: Hash exists - check which platforms need upload
                    if peertube_only_mode:
                        # In PeerTube-only mode, only check PeerTube status
                        need_youtube = False
                        need_peertube = upload_to_peertube and not existing_by_hash.peertube_id
                    else:
                        # Normal mode: check both platforms
                        need_youtube = upload_to_youtube and not existing_by_hash.youtube_id
                        need_peertube = upload_to_peertube and not existing_by_hash.peertube_id

                    if need_youtube or need_peertube:
                        print(f"  📤 Duplicate content (same hash as {existing_by_hash.filename})")

                        # Copy existing IDs to preserve already uploaded platforms
                        metadata.youtube_id = existing_by_hash.youtube_id
                        metadata.peertube_id = existing_by_hash.peertube_id

                        if peertube_only_mode:
                            print(f"    Uploading to PeerTube only (PeerTube-only mode)")
                        elif need_youtube and not need_peertube:
                            print(f"    Uploading to YouTube only (PeerTube already has it)")
                        elif need_peertube and not need_youtube:
                            print(f"    Uploading to PeerTube only (YouTube already has it)")
                        else:
                            print(f"    Uploading to both platforms")

                        result = self.upload_video(
                            video_path=video_path,
                            metadata=metadata,
                            upload_to_youtube=need_youtube,
                            upload_to_peertube=need_peertube,
                            replace_existing=False
                        )
                    else:
                        # Check skip message based on mode
                        if peertube_only_mode:
                            skip_msg = "already uploaded to PeerTube"
                        else:
                            skip_msg = "already uploaded to both platforms"

                        print(f"  ⏭️  Skipping ({skip_msg})")
                        print(f"    Same content as: {existing_by_hash.filename}")

                        # Copy existing IDs
                        metadata.youtube_id = existing_by_hash.youtube_id
                        metadata.peertube_id = existing_by_hash.peertube_id

                        results.append(UploadResult(
                            filename=metadata.filename,
                            title=metadata.title,
                            youtube_success=False,
                            youtube_error="Already uploaded" if not peertube_only_mode else "PeerTube-only mode",
                            peertube_success=False,
                            peertube_error="Already uploaded"
                        ))
                        continue

            else:
                # No hash available (shouldn't happen in normal flow)
                print(f"  ⚠️  No hash available, uploading anyway")
                result = self.upload_video(
                    video_path=video_path,
                    metadata=metadata,
                    upload_to_youtube=upload_to_youtube and not peertube_only_mode,
                    upload_to_peertube=upload_to_peertube,
                    replace_existing=False
                )

            results.append(result)

            # Update metadata.json after each successful upload
            if result.youtube_success or result.peertube_success:
                metadata_manager.update_metadata(metadata)
                metadata_manager.save(list(metadata_manager.metadata_dict.values()))

                # Update course.yml if updater is configured
                if self.course_yml_updater:
                    print(f"  Updating course.yml...")
                    self.course_yml_updater.update_video_ids(metadata)

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
