from ruamel.yaml import YAML
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.metadata_extractor import VideoMetadata


class CourseYmlUpdater:
    """Updates course.yml files in BEC repository with uploaded video IDs"""

    def __init__(self, bec_repo_path: str):
        """
        Initialize CourseYmlUpdater

        Args:
            bec_repo_path: Path to Bitcoin Education Content repository
        """
        self.bec_repo = Path(bec_repo_path)
        self.courses_dir = self.bec_repo / "courses"

        # Initialize ruamel.yaml with formatting preservation
        self.yaml = YAML()
        self.yaml.preserve_quotes = True
        self.yaml.default_flow_style = False
        self.yaml.width = 4096  # Prevent line wrapping
        # BEC repo uses: list items at 2 spaces, content at 4 spaces, nested lists at 6 spaces
        self.yaml.indent(mapping=4, sequence=4, offset=2)

        if not self.courses_dir.exists():
            raise ValueError(f"Courses directory not found at {self.courses_dir}")

    def update_video_ids(self, metadata: VideoMetadata) -> bool:
        """
        Update course.yml with video IDs from uploaded video

        Args:
            metadata: VideoMetadata with video_id and platform IDs

        Returns:
            True if update successful, False otherwise
        """
        if not metadata.video_id:
            print(f"⚠️  Warning: No video_id for {metadata.filename}, skipping course.yml update")
            return False

        if not metadata.youtube_id and not metadata.peertube_id:
            print(f"⚠️  Warning: No video IDs to update for {metadata.filename}")
            return False

        course_yml_path = self.courses_dir / metadata.course_index / "course.yml"

        if not course_yml_path.exists():
            print(f"❌ Error: course.yml not found at {course_yml_path}")
            return False

        try:
            # Load existing course.yml with ruamel.yaml (preserves formatting)
            with open(course_yml_path, 'r', encoding='utf-8') as f:
                course_data = self.yaml.load(f)

            if 'videos' not in course_data:
                course_data['videos'] = []

            # Find or create video entry for this video_id
            video_entry = self._find_or_create_video_entry(
                course_data['videos'],
                metadata.video_id
            )

            # Update YouTube ID if present
            if metadata.youtube_id:
                self._update_platform_id(
                    video_entry,
                    'youtube',
                    metadata.code_language,
                    metadata.youtube_id
                )
                print(f"✓ Updated YouTube ID for {metadata.code_language}: {metadata.youtube_id}")

            # Update PeerTube ID if present
            if metadata.peertube_id:
                self._update_platform_id(
                    video_entry,
                    'peertube',
                    metadata.code_language,
                    metadata.peertube_id
                )
                print(f"✓ Updated PeerTube ID for {metadata.code_language}: {metadata.peertube_id}")

            # Write back to course.yml (preserves original formatting)
            with open(course_yml_path, 'w', encoding='utf-8') as f:
                self.yaml.dump(course_data, f)

            print(f"✅ Successfully updated {course_yml_path}")
            return True

        except Exception as e:
            print(f"❌ Error updating course.yml: {e}")
            return False

    def _find_or_create_video_entry(self, videos: List[Dict[str, Any]], video_id: str) -> Dict[str, Any]:
        """
        Find existing video entry by video_id or create new one

        Args:
            videos: List of video entries from course.yml
            video_id: UUID from :::video id=...::: tag

        Returns:
            Video entry dictionary
        """
        # Search for existing entry
        for video in videos:
            if video.get('id') == video_id:
                return video

        # Create new entry if not found
        new_entry = {
            'id': video_id,
            'youtube': [],
            'peertube': []
        }
        videos.append(new_entry)
        return new_entry

    def _update_platform_id(self, video_entry: Dict[str, Any], platform: str,
                           language: str, video_id: str):
        """
        Update or add platform-specific video ID for a language

        Args:
            video_entry: Video entry dictionary
            platform: 'youtube' or 'peertube'
            language: Language code (e.g., 'en', 'fr')
            video_id: Platform-specific video ID
        """
        if platform not in video_entry:
            video_entry[platform] = []

        platform_list = video_entry[platform]

        # Check if language entry exists
        for entry in platform_list:
            if isinstance(entry, dict) and language in entry:
                # Update existing entry
                entry[language] = video_id
                return

        # Add new language entry
        platform_list.append({language: video_id})

    def batch_update(self, metadata_list: List[VideoMetadata]) -> Dict[str, bool]:
        """
        Batch update course.yml files for multiple videos

        Args:
            metadata_list: List of VideoMetadata objects

        Returns:
            Dictionary mapping filenames to update success status
        """
        results = {}
        for metadata in metadata_list:
            if metadata.youtube_id or metadata.peertube_id:
                success = self.update_video_ids(metadata)
                results[metadata.filename] = success
        return results
