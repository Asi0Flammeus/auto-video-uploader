#!/usr/bin/env python3
"""
Batch process thumbnails for all PeerTube videos in metadata.json.
Uses the same proven logic as test_single_video.py.
"""

import sys
import os
import json
import logging
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
from dotenv import load_dotenv
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console
from src.peertube_uploader import PeerTubeUploader
from scripts.update_peertube_thumbnails import PeerTubeThumbnailUpdater

load_dotenv()

console = Console()

# Get metadata.json path relative to this script (one directory up)
METADATA_FILE = Path(__file__).parent.parent / "metadata.json"


def load_peertube_videos(metadata_file: Path = METADATA_FILE):
    """
    Load all videos with PeerTube IDs from metadata.json.
    Skips videos that already have thumbnail=true.

    Returns:
        List of tuples (peertube_id, title)
    """
    if not metadata_file.exists():
        console.print(f"[red]❌ Error: {metadata_file} not found[/red]")
        return []

    try:
        with open(metadata_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        videos = []
        skipped = 0
        for item in data:
            peertube_id = item.get('peertube_id')
            # Skip if no peertube_id or if thumbnail already processed
            if peertube_id:
                if item.get('thumbnail', False):
                    skipped += 1
                    continue
                title = item.get('title', 'Unknown')
                videos.append((peertube_id, title))

        if skipped > 0:
            console.print(f"[yellow]ℹ️  Skipped {skipped} videos with existing thumbnails[/yellow]")

        return videos

    except Exception as e:
        console.print(f"[red]❌ Error loading metadata.json: {e}[/red]")
        return []


def update_thumbnail_status(peertube_id: str, metadata_file: Path = METADATA_FILE) -> bool:
    """
    Update metadata.json to mark thumbnail as completed for the given video.

    Args:
        peertube_id: PeerTube video UUID
        metadata_file: Path to metadata.json

    Returns:
        True if update successful, False otherwise
    """
    try:
        # Read current data
        with open(metadata_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Find and update the video entry
        updated = False
        for item in data:
            if item.get('peertube_id') == peertube_id:
                item['thumbnail'] = True
                updated = True
                break

        if not updated:
            return False

        # Write back to file
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        return True

    except Exception as e:
        console.print(f"[red]⚠️  Failed to update metadata for {peertube_id}: {e}[/red]")
        return False


def process_single_video(updater, video_uuid: str, video_title: str) -> bool:
    """
    Process thumbnail for a single video using proven workflow.

    Args:
        updater: PeerTubeThumbnailUpdater instance
        video_uuid: Video UUID or shortUUID
        video_title: Video title for display

    Returns:
        True if successful, False otherwise
    """
    # Step 1: Get video URL
    video_url = updater.get_video_file_url(video_uuid)
    if not video_url:
        return False

    # Step 2: Download video segment (first 10 seconds)
    video_segment = updater.download_video_segment(video_url, duration=10)
    if not video_segment:
        return False

    # Step 3: Extract thumbnail at 4 seconds
    thumbnail_path = updater.thumbnail_generator.extract_frame(
        video_path=video_segment,
        timestamp=4
    )

    # Cleanup video segment
    try:
        video_segment.unlink()
    except:
        pass

    if not thumbnail_path:
        return False

    # Step 4: Upload thumbnail to PeerTube
    success = updater.uploader.upload_thumbnail(video_uuid, thumbnail_path)

    # Cleanup thumbnail
    try:
        thumbnail_path.unlink()
    except:
        pass

    return success


def main():
    instance_url = os.getenv('PEERTUBE_INSTANCE', '').rstrip('/')
    username = os.getenv('PEERTUBE_USERNAME')
    password = os.getenv('PEERTUBE_PASSWORD')
    verify_ssl = os.getenv('PEERTUBE_VERIFY_SSL', 'true').lower() != 'false'

    if not all([instance_url, username, password]):
        console.print("[red]❌ Missing environment variables[/red]")
        return 1

    console.print("\n" + "="*60)
    console.print("[bold blue]🎬 Batch PeerTube Thumbnail Processor[/bold blue]")
    console.print("="*60)
    console.print(f"Instance: {instance_url}")
    console.print(f"Source: {METADATA_FILE}")
    console.print("="*60 + "\n")

    # Load videos from metadata.json
    console.print(f"📥 Loading videos from {METADATA_FILE.name}...")
    videos = load_peertube_videos()

    if not videos:
        console.print(f"[red]❌ No videos with PeerTube IDs found in {METADATA_FILE.name}[/red]")
        return 1

    console.print(f"[green]✅ Found {len(videos)} videos with PeerTube IDs[/green]\n")

    # Create uploader and authenticate
    console.print("🔐 Authenticating with PeerTube...")
    uploader = PeerTubeUploader(
        instance_url=instance_url,
        username=username,
        password=password,
        verify_ssl=verify_ssl
    )

    if not uploader.authenticate():
        console.print("[red]❌ Authentication failed![/red]")
        return 1

    console.print("[green]✅ Authenticated successfully[/green]\n")

    # Create updater
    updater = PeerTubeThumbnailUpdater(
        instance_url=instance_url,
        username=username,
        password=password,
        verify_ssl=verify_ssl
    )
    updater.uploader = uploader

    # Suppress logging during progress to keep output clean
    logging.getLogger('scripts.update_peertube_thumbnails').setLevel(logging.WARNING)
    logging.getLogger('src.thumbnail_generator').setLevel(logging.WARNING)
    logging.getLogger('src.peertube_uploader').setLevel(logging.WARNING)

    # Process videos with clean progress bar
    stats = {
        'total': len(videos),
        'processed': 0,
        'failed': 0,
        'errors': []
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TextColumn("({task.completed}/{task.total})"),
        TimeRemainingColumn(),
        console=console,
        transient=False
    ) as progress:
        task = progress.add_task(
            f"[cyan]Processing thumbnails (✅ {stats['processed']} | ❌ {stats['failed']})",
            total=len(videos)
        )

        for video_uuid, video_title in videos:
            # Truncate title for display
            display_title = video_title[:50] + "..." if len(video_title) > 50 else video_title

            # Update progress description
            progress.update(
                task,
                description=f"[cyan]Processing: {display_title} (✅ {stats['processed']} | ❌ {stats['failed']})"
            )

            # Process video
            try:
                success = process_single_video(updater, video_uuid, video_title)

                if success:
                    stats['processed'] += 1
                    # Update metadata.json to mark thumbnail as completed
                    update_thumbnail_status(video_uuid)
                else:
                    stats['failed'] += 1
                    stats['errors'].append({
                        'uuid': video_uuid,
                        'title': video_title[:50],
                        'error': 'Processing failed'
                    })

            except Exception as e:
                stats['failed'] += 1
                stats['errors'].append({
                    'uuid': video_uuid,
                    'title': video_title[:50],
                    'error': str(e)
                })

            # Advance progress
            progress.advance(task)

        # Update final description
        progress.update(
            task,
            description=f"[green]✅ Complete! (Processed: {stats['processed']} | Failed: {stats['failed']})"
        )

    # Print summary
    console.print("\n" + "="*60)
    console.print("[bold]📊 Summary[/bold]")
    console.print("="*60)
    console.print(f"Total videos: {stats['total']}")
    console.print(f"[green]✅ Processed: {stats['processed']}[/green]")
    console.print(f"[red]❌ Failed: {stats['failed']}[/red]")

    if stats['errors']:
        console.print("\n[bold red]⚠️  Errors:[/bold red]")
        for error in stats['errors'][:10]:  # Show first 10 errors
            console.print(f"  - {error['title']}: {error['error']}")
        if len(stats['errors']) > 10:
            console.print(f"  ... and {len(stats['errors']) - 10} more errors")

    console.print("="*60)
    console.print(f"\n[green]✅ Batch processing complete![/green]")

    return 0 if stats['failed'] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
