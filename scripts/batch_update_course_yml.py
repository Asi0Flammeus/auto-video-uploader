#!/usr/bin/env python3
"""
Batch update all course.yml files with PeerTube IDs from metadata.json
"""

import json
import sys
from pathlib import Path

# Add parent directory to path to import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.course_yml_updater import CourseYmlUpdater
from src.metadata_extractor import VideoMetadata
from dotenv import load_dotenv
import os

# Load environment variables
load_dotenv()


def load_metadata_entries():
    """Load all entries from metadata.json"""
    metadata_file = Path(__file__).parent.parent / "metadata.json"

    if not metadata_file.exists():
        print(f"❌ Error: metadata.json not found at {metadata_file}")
        sys.exit(1)

    with open(metadata_file, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # metadata.json is a list of video objects
    return data if isinstance(data, list) else data.get('videos', [])


def convert_to_metadata_objects(entries):
    """Convert JSON entries to VideoMetadata objects"""
    metadata_list = []

    for entry in entries:
        # Skip entries without peertube_id
        if not entry.get('peertube_id'):
            continue

        # Skip entries without video_id (can't update course.yml)
        if not entry.get('video_id'):
            print(f"⚠️  Warning: Entry {entry.get('filename')} has peertube_id but no video_id, skipping")
            continue

        # Create VideoMetadata object with correct field names
        metadata = VideoMetadata(
            filename=entry['filename'],
            course_index=entry['course_index'],
            part_index=entry['part_index'],
            chapter_index=entry['chapter_index'],
            code_language=entry['code_language'],
            title=entry.get('title', ''),
            description=entry.get('description', ''),
            chapter_title=entry.get('chapter_title', ''),
            course_title=entry.get('course_title', ''),
            video_id=entry.get('video_id'),
            youtube_id=entry.get('youtube_id'),
            peertube_id=entry.get('peertube_id'),
            sha256_hash=entry.get('sha256_hash')
        )

        metadata_list.append(metadata)

    return metadata_list


def group_by_course(metadata_list):
    """Group metadata entries by course for organized updates"""
    courses = {}

    for metadata in metadata_list:
        course_key = metadata.course_index
        if course_key not in courses:
            courses[course_key] = []
        courses[course_key].append(metadata)

    return courses


def main():
    print("🚀 Starting batch course.yml update with PeerTube IDs\n")

    # Get BEC repository path
    bec_repo = os.getenv('BEC_REPO')
    if not bec_repo:
        print("❌ Error: BEC_REPO not set in .env")
        sys.exit(1)

    print(f"📂 BEC Repository: {bec_repo}\n")

    # Load metadata entries
    print("📖 Loading metadata.json...")
    entries = load_metadata_entries()
    print(f"✓ Found {len(entries)} total entries\n")

    # Convert to VideoMetadata objects (filter for PeerTube IDs)
    print("🔍 Filtering entries with PeerTube IDs...")
    metadata_list = convert_to_metadata_objects(entries)
    print(f"✓ Found {len(metadata_list)} entries with PeerTube IDs\n")

    if not metadata_list:
        print("ℹ️  No entries with PeerTube IDs to update")
        return

    # Group by course
    courses = group_by_course(metadata_list)
    print(f"📚 Updating {len(courses)} course(s):\n")

    # Initialize updater
    try:
        updater = CourseYmlUpdater(bec_repo)
    except ValueError as e:
        print(f"❌ Error initializing CourseYmlUpdater: {e}")
        sys.exit(1)

    # Update each course
    total_success = 0
    total_failed = 0

    for course_index, course_metadata in sorted(courses.items()):
        print(f"\n{'='*60}")
        print(f"📖 Course: {course_index}")
        print(f"{'='*60}")
        print(f"Videos to update: {len(course_metadata)}\n")

        for metadata in course_metadata:
            print(f"Processing: {metadata.filename}")
            print(f"  Language: {metadata.code_language}")
            print(f"  Video ID: {metadata.video_id}")
            print(f"  PeerTube ID: {metadata.peertube_id}")

            success = updater.update_video_ids(metadata)

            if success:
                total_success += 1
            else:
                total_failed += 1

            print()  # Blank line for readability

    # Final summary
    print(f"\n{'='*60}")
    print(f"📊 BATCH UPDATE SUMMARY")
    print(f"{'='*60}")
    print(f"✅ Successful updates: {total_success}")
    print(f"❌ Failed updates: {total_failed}")
    print(f"📝 Total processed: {total_success + total_failed}")
    print(f"{'='*60}\n")

    if total_failed > 0:
        print("⚠️  Some updates failed. Check the output above for details.")
        sys.exit(1)
    else:
        print("🎉 All course.yml files updated successfully!")


if __name__ == '__main__':
    main()
