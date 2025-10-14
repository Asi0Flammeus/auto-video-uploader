#!/usr/bin/env python3

import os
import sys
from pathlib import Path
from typing import List

import click
from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

from src.metadata_extractor import MetadataExtractor, VideoMetadata
from src.youtube_uploader import YouTubeUploader
from src.peertube_uploader import PeerTubeUploader
from src.upload_orchestrator import UploadOrchestrator
from src.metadata_manager import MetadataManager
from src.course_yml_updater import CourseYmlUpdater

# Load environment variables
load_dotenv()

console = Console()


def display_metadata_table(metadata_list: List[VideoMetadata]):
    """Display metadata in a formatted table"""
    table = Table(title="Video Metadata Extraction Results")

    table.add_column("Filename", style="cyan", no_wrap=False)
    table.add_column("Title", style="green")
    table.add_column("Language", style="yellow")
    table.add_column("Course", style="blue")

    for metadata in metadata_list:
        table.add_row(
            metadata.filename,
            metadata.title,
            metadata.code_language,
            metadata.course_title
        )

    console.print(table)

    # Also display full details
    console.print("\n[bold]Detailed Information:[/bold]")
    for metadata in metadata_list:
        console.print(f"\n[cyan]File:[/cyan] {metadata.filename}")
        console.print(f"  [green]Title:[/green] {metadata.title}")
        console.print(f"  [yellow]Description:[/yellow] {metadata.description}")
        console.print(f"  [blue]Course:[/blue] {metadata.course_index} - {metadata.course_title}")
        console.print(f"  [magenta]Chapter:[/magenta] Part {metadata.part_index}, Chapter {metadata.chapter_index} - {metadata.chapter_title}")
        console.print(f"  [red]Language:[/red] {metadata.code_language}")
        if metadata.sha256_hash:
            console.print(f"  [dim]SHA256:[/dim] {metadata.sha256_hash}")


def display_upload_results(results):
    """Display upload results in a formatted table"""
    table = Table(title="Upload Results")

    table.add_column("Filename", style="cyan", no_wrap=False)
    table.add_column("YouTube", style="green")
    table.add_column("PeerTube", style="blue")

    for result in results:
        youtube_status = "✅" if result.youtube_success else "❌"
        peertube_status = "✅" if result.peertube_success else "❌"

        table.add_row(
            result.filename,
            youtube_status,
            peertube_status
        )

    console.print(table)

    # Display URLs for successful uploads
    console.print("\n[bold]Uploaded Videos:[/bold]")
    for result in results:
        if result.youtube_success or result.peertube_success:
            console.print(f"\n[cyan]{result.filename}[/cyan]")
            if result.youtube_success:
                console.print(f"  [green]YouTube:[/green] {result.youtube_url}")
            if result.peertube_success:
                console.print(f"  [blue]PeerTube:[/blue] {result.peertube_url}")

    # Display errors
    errors = [r for r in results if not r.youtube_success or not r.peertube_success]
    if errors:
        console.print("\n[bold red]Errors:[/bold red]")
        for result in errors:
            if not result.youtube_success:
                console.print(f"  YouTube - {result.filename}: {result.youtube_error}")
            if not result.peertube_success:
                console.print(f"  PeerTube - {result.filename}: {result.peertube_error}")


def get_subfolders(base_path: Path) -> List[str]:
    """Get list of subfolders in the inputs directory"""
    if not base_path.exists():
        return []

    subfolders = [d.name for d in base_path.iterdir() if d.is_dir()]
    return sorted(subfolders)


@click.command()
@click.option('--bec-repo', envvar='BEC_REPO', help='Path to Bitcoin Education Content repository')
@click.option('--input-dir', default='./inputs', help='Path to inputs directory containing video folders')
def main(bec_repo: str, input_dir: str):
    """
    Automatic Video Uploader - Metadata Extraction Component

    This tool extracts metadata from video filenames and prepares them for upload.
    """
    console.print("[bold blue]🎥 Automatic Video Uploader - Metadata Extraction[/bold blue]\n")

    # Check if BEC_REPO is set
    if not bec_repo:
        console.print("[red]Error: BEC_REPO environment variable is not set![/red]")
        console.print("Please set it in your .env file or pass it as --bec-repo parameter")
        sys.exit(1)

    # Check if BEC repo exists
    if not Path(bec_repo).exists():
        console.print(f"[red]Error: Bitcoin Education Content repository not found at {bec_repo}[/red]")
        sys.exit(1)

    # Check inputs directory
    input_path = Path(input_dir)
    if not input_path.exists():
        console.print(f"[yellow]Warning: Inputs directory not found at {input_path}[/yellow]")
        console.print("Creating inputs directory...")
        input_path.mkdir(parents=True, exist_ok=True)

    # Get list of subfolders
    subfolders = get_subfolders(input_path)

    if not subfolders:
        console.print(f"[yellow]No subfolders found in {input_path}[/yellow]")
        console.print("Please create a subfolder and place your video files there.")
        sys.exit(0)

    # Display available subfolders
    console.print("[bold]Available subfolders:[/bold]")
    for i, folder in enumerate(subfolders, 1):
        # Count video files in each folder
        video_count = len(list((input_path / folder).glob("*.mp4")))
        console.print(f"  {i}. {folder} ({video_count} videos)")

    # Ask user to select a subfolder
    console.print("")
    choice = Prompt.ask(
        "Select a subfolder to process",
        choices=[str(i) for i in range(1, len(subfolders) + 1)],
        default="1"
    )

    selected_folder = subfolders[int(choice) - 1]
    selected_path = input_path / selected_folder

    console.print(f"\n[green]Processing videos in: {selected_path}[/green]\n")

    # Initialize metadata extractor
    try:
        extractor = MetadataExtractor(bec_repo)
    except Exception as e:
        console.print(f"[red]Error initializing metadata extractor: {e}[/red]")
        sys.exit(1)

    # Load existing metadata from metadata.json
    metadata_manager = MetadataManager()
    existing_metadata = metadata_manager.load()

    # Process videos in selected folder
    metadata_list = extractor.process_videos_in_folder(selected_path)

    # Check for duplicate hashes and merge with existing metadata
    hash_duplicates = []
    for metadata in metadata_list:
        # First check if this hash already exists (different filename, same content)
        if metadata.sha256_hash:
            existing_by_hash = metadata_manager.find_by_hash(metadata.sha256_hash)
            if existing_by_hash and existing_by_hash.filename != metadata.filename:
                # Found duplicate content with different filename
                hash_duplicates.append({
                    'current': metadata,
                    'existing': existing_by_hash
                })
                # Copy upload IDs from the existing video with same hash
                metadata.youtube_id = existing_by_hash.youtube_id
                metadata.peertube_id = existing_by_hash.peertube_id
                continue

        # Merge with existing metadata by filename (preserve video IDs if they exist)
        existing = existing_metadata.get(metadata.filename)
        if existing:
            metadata.youtube_id = existing.youtube_id
            metadata.peertube_id = existing.peertube_id

    # Display hash duplicate warnings
    if hash_duplicates:
        console.print(f"\n[yellow]⚠️  Found {len(hash_duplicates)} videos with duplicate content (same hash):[/yellow]")
        for dup in hash_duplicates:
            console.print(f"  • {dup['current'].filename} → same as {dup['existing'].filename}")
            console.print(f"    Hash: {dup['current'].sha256_hash[:16]}...")
            if dup['existing'].youtube_id or dup['existing'].peertube_id:
                console.print(f"    [green]Already uploaded, will skip[/green]")
        console.print("")

    if metadata_list:
        console.print(f"\n[green]✅ Successfully processed {len(metadata_list)} videos[/green]\n")
        display_metadata_table(metadata_list)

        # Filter videos: only upload those whose hash is NOT in metadata.json with upload IDs
        videos_to_upload = []
        already_uploaded = []

        for metadata in metadata_list:
            if metadata.sha256_hash and metadata_manager.is_hash_uploaded(metadata.sha256_hash):
                already_uploaded.append(metadata)
            else:
                videos_to_upload.append(metadata)

        # Save metadata only for new videos (hash not already present)
        if videos_to_upload:
            for metadata in videos_to_upload:
                metadata_manager.update_metadata(metadata)

            metadata_manager.save(list(metadata_manager.metadata_dict.values()))
            console.print(f"[green]✅ Metadata saved for {len(videos_to_upload)} new videos[/green]")

        # Display upload plan
        if already_uploaded:
            console.print(f"\n[yellow]⏭️  Skipping {len(already_uploaded)} already uploaded videos (by hash):[/yellow]")
            for m in already_uploaded:
                console.print(f"  • {m.filename}")

        if not videos_to_upload:
            console.print("\n[green]✅ All videos already uploaded. Nothing to do.[/green]")
        else:
            console.print(f"\n[blue]📤 Will upload {len(videos_to_upload)} new videos:[/blue]")
            for m in videos_to_upload:
                console.print(f"  • {m.filename}")

            # Check which platforms are configured
            youtube_configured = False
            peertube_configured = False

            # Check YouTube credentials
            youtube_client_secrets = os.getenv('YOUTUBE_CLIENT_SECRETS_FILE')
            if youtube_client_secrets and Path(youtube_client_secrets).exists():
                youtube_configured = True

            # Check PeerTube credentials
            peertube_instance = os.getenv('PEERTUBE_INSTANCE')
            peertube_username = os.getenv('PEERTUBE_USERNAME')
            peertube_password = os.getenv('PEERTUBE_PASSWORD')
            if peertube_instance and peertube_username and peertube_password:
                peertube_configured = True

            if not youtube_configured and not peertube_configured:
                console.print("[red]No platform credentials configured. Cannot upload.[/red]")
                console.print("Please configure credentials in .env file.")
                sys.exit(1)

            # Ask user which platform(s) to upload to
            console.print("\n[bold]Select upload platform(s):[/bold]")
            platform_choices = []
            choice_map = {}
            choice_num = 1

            if youtube_configured and peertube_configured:
                console.print(f"  {choice_num}. Both YouTube and PeerTube")
                choice_map[str(choice_num)] = "both"
                platform_choices.append(str(choice_num))
                choice_num += 1

            if youtube_configured:
                console.print(f"  {choice_num}. YouTube only")
                choice_map[str(choice_num)] = "youtube"
                platform_choices.append(str(choice_num))
                choice_num += 1

            if peertube_configured:
                console.print(f"  {choice_num}. PeerTube only")
                choice_map[str(choice_num)] = "peertube"
                platform_choices.append(str(choice_num))
                choice_num += 1

            console.print("")
            platform_choice = Prompt.ask(
                "Select platform",
                choices=platform_choices,
                default="1"
            )

            selected_platform = choice_map[platform_choice]

            # Initialize uploaders based on selection
            youtube_uploader = None
            peertube_uploader = None
            peertube_upload_endpoint = os.getenv('PEERTUBE_UPLOAD_ENDPOINT')
            peertube_verify_ssl = os.getenv('PEERTUBE_VERIFY_SSL', 'true').lower() == 'true'

            if selected_platform in ["both", "youtube"]:
                youtube_uploader = YouTubeUploader(youtube_client_secrets)
                console.print("[green]✓ YouTube uploader initialized[/green]")

            if selected_platform in ["both", "peertube"]:
                peertube_uploader = PeerTubeUploader(
                    instance_url=peertube_instance,
                    username=peertube_username,
                    password=peertube_password,
                    upload_endpoint=peertube_upload_endpoint,
                    verify_ssl=peertube_verify_ssl
                )
                console.print("[green]✓ PeerTube uploader initialized[/green]")

            # Initialize CourseYmlUpdater
            course_yml_updater = CourseYmlUpdater(bec_repo)

            # Create orchestrator
            orchestrator = UploadOrchestrator(
                youtube_uploader=youtube_uploader,
                peertube_uploader=peertube_uploader,
                course_yml_updater=course_yml_updater
            )

            # Authenticate with platforms
            console.print("\n[bold]Authenticating with platforms...[/bold]")
            auth_status = orchestrator.authenticate_platforms()

            if not any(auth_status.values()):
                console.print("[red]Failed to authenticate with any platform.[/red]")
                sys.exit(1)

            # Upload videos
            console.print(f"\n[bold]Uploading {len(videos_to_upload)} videos...[/bold]")
            results = orchestrator.upload_batch(
                video_folder=selected_path,
                metadata_list=videos_to_upload,
                upload_to_youtube=youtube_uploader is not None,
                upload_to_peertube=peertube_uploader is not None,
                replace_decisions={}
            )

            # Display results
            console.print(f"\n")
            display_upload_results(results)

            # Summary
            youtube_success = sum(1 for r in results if r.youtube_success)
            peertube_success = sum(1 for r in results if r.peertube_success)

            console.print(f"\n[bold]Upload Summary:[/bold]")
            if youtube_uploader:
                console.print(f"  YouTube: {youtube_success}/{len(results)} successful")
            if peertube_uploader:
                console.print(f"  PeerTube: {peertube_success}/{len(results)} successful")

            # Update metadata.json with video IDs for uploaded videos
            for metadata in videos_to_upload:
                metadata_manager.update_metadata(metadata)

            metadata_manager.save(list(metadata_manager.metadata_dict.values()))
            console.print(f"[green]✅ Metadata with video IDs updated[/green]")

    else:
        console.print("[yellow]No videos were processed successfully.[/yellow]")


if __name__ == '__main__':
    main()