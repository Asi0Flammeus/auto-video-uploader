import json
from pathlib import Path
from typing import Dict, List, Optional
from src.metadata_extractor import VideoMetadata


class MetadataManager:
    """Manages metadata.json file as persistent storage for upload history"""

    def __init__(self, metadata_file: Path = Path("metadata.json")):
        """
        Initialize metadata manager

        Args:
            metadata_file: Path to metadata.json file (default: project root)
        """
        self.metadata_file = metadata_file
        self.metadata_dict: Dict[str, VideoMetadata] = {}

    def load(self) -> Dict[str, VideoMetadata]:
        """
        Load existing metadata from metadata.json

        Returns:
            Dictionary mapping filename to VideoMetadata
        """
        if not self.metadata_file.exists():
            return {}

        try:
            with open(self.metadata_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for item in data:
                metadata = VideoMetadata(
                    filename=item['filename'],
                    course_index=item['course_index'],
                    part_index=item['part_index'],
                    chapter_index=item['chapter_index'],
                    code_language=item['code_language'],
                    title=item['title'],
                    description=item['description'],
                    chapter_title=item['chapter_title'],
                    course_title=item['course_title'],
                    video_id=item.get('video_id') or item.get('chapter_uuid'),  # Support old field name
                    youtube_id=item.get('youtube_id'),
                    peertube_id=item.get('peertube_id'),
                    sha256_hash=item.get('sha256_hash')
                )
                self.metadata_dict[item['filename']] = metadata

            return self.metadata_dict

        except Exception as e:
            print(f"Warning: Could not load metadata.json: {e}")
            return {}

    def save(self, metadata_list: List[VideoMetadata]):
        """
        Save metadata list to metadata.json

        Args:
            metadata_list: List of VideoMetadata objects to save
        """
        metadata_dict = []
        for metadata in metadata_list:
            metadata_dict.append({
                'filename': metadata.filename,
                'course_index': metadata.course_index,
                'part_index': metadata.part_index,
                'chapter_index': metadata.chapter_index,
                'code_language': metadata.code_language,
                'title': metadata.title,
                'description': metadata.description,
                'chapter_title': metadata.chapter_title,
                'course_title': metadata.course_title,
                'video_id': metadata.video_id,
                'youtube_id': metadata.youtube_id,
                'peertube_id': metadata.peertube_id,
                'sha256_hash': metadata.sha256_hash
            })

        with open(self.metadata_file, 'w', encoding='utf-8') as f:
            json.dump(metadata_dict, f, indent=2, ensure_ascii=False)

    def get_existing_metadata(self, filename: str) -> Optional[VideoMetadata]:
        """
        Get existing metadata for a filename

        Args:
            filename: Video filename to check

        Returns:
            VideoMetadata if exists, None otherwise
        """
        return self.metadata_dict.get(filename)

    def is_uploaded(self, filename: str) -> bool:
        """
        Check if a video has been uploaded to at least one platform

        Args:
            filename: Video filename to check

        Returns:
            True if video has youtube_id or peertube_id
        """
        existing = self.metadata_dict.get(filename)
        if not existing:
            return False

        return existing.youtube_id is not None or existing.peertube_id is not None

    def find_by_hash(self, sha256_hash: str) -> Optional[VideoMetadata]:
        """
        Find metadata by SHA256 hash
        
        Args:
            sha256_hash: SHA256 hash to search for
            
        Returns:
            VideoMetadata if found, None otherwise
        """
        for metadata in self.metadata_dict.values():
            if metadata.sha256_hash == sha256_hash:
                return metadata
        return None

    def is_hash_uploaded(self, sha256_hash: str) -> bool:
        """
        Check if a video with this hash has been uploaded to at least one platform
        
        Args:
            sha256_hash: SHA256 hash to check
            
        Returns:
            True if video with this hash has youtube_id or peertube_id
        """
        existing = self.find_by_hash(sha256_hash)
        if not existing:
            return False
        
        return existing.youtube_id is not None or existing.peertube_id is not None

    def update_metadata(self, metadata: VideoMetadata):
        """
        Update or add metadata for a video

        Args:
            metadata: VideoMetadata to update
        """
        self.metadata_dict[metadata.filename] = metadata
