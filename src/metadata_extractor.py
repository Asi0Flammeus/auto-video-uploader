import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.console import Console


@dataclass
class VideoMetadata:
    filename: str
    course_index: str
    part_index: int
    chapter_index: int
    code_language: str
    title: str
    description: str
    chapter_title: str
    course_title: str
    video_id: Optional[str] = None  # UUID from :::video id=...::: tag, maps to course.yml
    youtube_id: Optional[str] = None
    peertube_id: Optional[str] = None
    sha256_hash: Optional[str] = None


class MetadataExtractor:
    def __init__(self, bec_repo_path: str):
        self.bec_repo = Path(bec_repo_path)
        self.courses_dir = self.bec_repo / "courses"

        if not self.courses_dir.exists():
            raise ValueError(f"Courses directory not found at {self.courses_dir}")

    @staticmethod
    def calculate_file_hash(file_path: Path) -> str:
        """
        Calculate SHA256 hash of a video file
        
        Args:
            file_path: Path to the video file
            
        Returns:
            SHA256 hash as hexadecimal string
        """
        import hashlib
        
        sha256_hash = hashlib.sha256()
        
        # Read file in chunks to handle large video files efficiently
        with open(file_path, 'rb') as f:
            for byte_block in iter(lambda: f.read(4096 * 1024), b""):  # 4MB chunks
                sha256_hash.update(byte_block)
        
        return sha256_hash.hexdigest()

    def parse_filename(self, filename: str) -> Tuple[str, int, int, str]:
        """
        Parse video filename following the pattern:
        {course_index}_{part_index}.{chapter_index}_{code_language}.mp4

        Returns: (course_index, part_index, chapter_index, code_language)
        """
        # Remove .mp4 extension
        if filename.endswith('.mp4'):
            filename = filename[:-4]

        # Pattern: courseindex_partindex.chapterindex_codelanguage
        pattern = r'^([^_]+)_(\d+)\.(\d+)_([^_]+)$'
        match = re.match(pattern, filename)

        if not match:
            raise ValueError(f"Filename '{filename}' doesn't match expected pattern")

        course_index = match.group(1)
        part_index = int(match.group(2))
        chapter_index = int(match.group(3))
        code_language = match.group(4)

        return course_index, part_index, chapter_index, code_language

    def get_course_title(self, course_index: str, code_language: str) -> str:
        """
        Extract course title from the markdown file header
        """
        md_file = self.courses_dir / course_index / f"{code_language}.md"

        if not md_file.exists():
            raise FileNotFoundError(f"Course file not found: {md_file}")

        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # Extract name from YAML front matter
        lines = content.split('\n')
        in_frontmatter = False
        for line in lines:
            if line.strip() == '---':
                if not in_frontmatter:
                    in_frontmatter = True
                    continue
                else:
                    break

            if in_frontmatter and line.startswith('name:'):
                return line.replace('name:', '').strip().strip('"').strip("'")

        return f"Course {course_index.upper()}"

    def get_chapter_title(self, course_index: str, part_index: int,
                         chapter_index: int, code_language: str) -> Tuple[str, Optional[str]]:
        """
        Extract chapter title and video ID based on part and chapter indices

        Returns: (chapter_title, video_id)
        Note: video_id is extracted from :::video id=UUID::: tag, which maps to course.yml
        """
        md_file = self.courses_dir / course_index / f"{code_language}.md"

        if not md_file.exists():
            raise FileNotFoundError(f"Course file not found: {md_file}")

        with open(md_file, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        current_part = 0
        current_chapter = 0
        in_frontmatter = False
        frontmatter_ended = False  # Track if we've finished processing frontmatter

        # Helper function to check if partId/chapterId exists within next few lines
        def has_tag_nearby(lines_list, start_idx, tag_name, max_distance=5):
            """Check if a tag exists within max_distance lines after start_idx"""
            for j in range(start_idx + 1, min(start_idx + 1 + max_distance, len(lines_list))):
                if tag_name.lower() in lines_list[j].lower():
                    return True
            return False

        for i, line in enumerate(lines):
            # Skip frontmatter (only at the beginning of the file)
            if line.strip() == '---' and not frontmatter_ended:
                in_frontmatter = not in_frontmatter
                # If we're exiting frontmatter, mark it as ended
                if not in_frontmatter:
                    frontmatter_ended = True
                continue
            if in_frontmatter:
                continue

            # Check for part header (single #)
            if line.startswith('# ') and not line.startswith('## '):
                # Look for partId tag within next few lines
                if has_tag_nearby(lines, i, '<partId'):
                    current_part += 1
                    current_chapter = 0

            # Check for chapter header (double ##)
            elif line.startswith('## ') and not line.startswith('### '):
                # Look for chapterId tag within next few lines
                if has_tag_nearby(lines, i, '<chapterId'):
                    current_chapter += 1

                    # Check if this is the chapter we're looking for
                    if current_part == part_index and current_chapter == chapter_index:
                        # Found the target chapter - extract the title text
                        chapter_title = line[2:].strip()  # Remove '##' and whitespace
                        # Remove any markdown formatting
                        chapter_title = chapter_title.replace('**', '').replace('*', '')
                        chapter_title = chapter_title.replace('__', '').replace('_', '')

                        # Extract video ID from :::video id=UUID::: tag in next few lines
                        video_id = None
                        for j in range(i + 1, min(i + 10, len(lines))):
                            if ':::video id=' in lines[j]:
                                # Extract UUID from :::video id=UUID:::
                                video_match = re.search(r':::video id=([^:]+):::', lines[j])
                                if video_match:
                                    video_id = video_match.group(1)
                                break

                        return chapter_title, video_id

        # Fallback if chapter not found
        return f"Chapter {part_index}.{chapter_index}", None

    def generate_video_title(self, course_index: str, part_index: int,
                            chapter_index: int, chapter_title: str) -> str:
        """
        Generate video title following the template:
        [BTC 101] - 2.2 - Chapter Title
        """
        # Convert course index to display format (btc101 -> BTC 101)
        course_display = course_index.upper()
        if course_display.startswith('BTC') and len(course_display) > 3:
            course_display = f"{course_display[:3]} {course_display[3:]}"

        return f"[{course_display}] - {part_index}.{chapter_index} - {chapter_title}"

    def generate_video_description(self, course_index: str, course_title: str) -> str:
        """
        Generate video description following the template:
        {course index upper case with space} - {course title in code_language}

        Note: This returns ONLY the base description without footer.
        Footer should be appended during upload.
        """
        course_display = course_index.upper()
        if course_display.startswith('BTC') and len(course_display) > 3:
            course_display = f"{course_display[:3]} {course_display[3:]}"

        return f"{course_display} - {course_title}"

    @staticmethod
    def get_description_footer() -> str:
        """
        Get the standard footer to be appended to video descriptions during upload
        """
        return """
—
Plan ₿ Network  — Scaling Bitcoin Adoption

Level up your Bitcoin knowledge and Explore all our free, open‑source courses on the platform:
https://planb.network

Follow us on social:
Twitter: @planb_network

⚠️ Disclaimer & Risk Warning

Cryptocurrencies are risky. All content is for educational and informational purposes only and does not constitute financial advice. Consult a licensed financial adviser before making any significant financial decisions. Bitcoin is highly volatile and speculative; investing can lead to losses. Never invest more than you can afford to lose. Past performance is not indicative of future results.

The crypto industry contains scams—verify sources and do your own research. Do not trust anyone blindly, including us. We do not partner with any altcoin projects. Our content is free and open source under the CC BY-SA license. We are independent and have no obligations or contracts with any cryptocurrency or ICO.

We will never ask for your private information (seed phrase, private keys, name, address, KYC). We are not responsible for losses due to scams, key mismanagement, or poor investments.

More info:

💻 https://planb.network/about

📬 contact@planb.network

—"""

    def extract_metadata(self, video_filename: str, video_file_path: Optional[Path] = None) -> VideoMetadata:
        """
        Extract all metadata from a video filename
        
        Args:
            video_filename: Name of the video file
            video_file_path: Optional full path to calculate SHA256 hash
        """
        try:
            # Parse filename
            course_index, part_index, chapter_index, code_language = self.parse_filename(video_filename)

            # Get course and chapter titles
            course_title = self.get_course_title(course_index, code_language)
            chapter_title, video_id = self.get_chapter_title(course_index, part_index,
                                                             chapter_index, code_language)

            # Generate video title and description
            video_title = self.generate_video_title(course_index, part_index,
                                                   chapter_index, chapter_title)
            video_description = self.generate_video_description(course_index, course_title)

            # Calculate SHA256 hash if file path provided
            sha256_hash = None
            if video_file_path and video_file_path.exists():
                sha256_hash = self.calculate_file_hash(video_file_path)

            return VideoMetadata(
                filename=video_filename,
                course_index=course_index,
                part_index=part_index,
                chapter_index=chapter_index,
                code_language=code_language,
                title=video_title,
                description=video_description,
                chapter_title=chapter_title,
                course_title=course_title,
                video_id=video_id,
                sha256_hash=sha256_hash
            )
        except Exception as e:
            raise Exception(f"Error processing {video_filename}: {str(e)}")

    def process_videos_in_folder(self, folder_path: Path) -> List[VideoMetadata]:
        """
        Process all video files in a given folder
        """
        metadata_list = []
        errors = []
        console = Console()

        # Find all .mp4 files in the folder and sort alphabetically
        video_files = sorted(folder_path.glob("*.mp4"), key=lambda x: x.name)

        if not video_files:
            console.print(f"[yellow]No video files found in {folder_path}[/yellow]")
            return metadata_list

        console.print(f"\n[bold cyan]Processing {len(video_files)} videos...[/bold cyan]")

        # Process videos with progress bar
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
            task = progress.add_task("[cyan]Calculating hashes and extracting metadata...", total=len(video_files))

            for video_file in video_files:
                try:
                    # Update progress description with current file
                    progress.update(task, description=f"[cyan]Processing: {video_file.name[:50]}...")

                    metadata = self.extract_metadata(video_file.name, video_file)
                    metadata_list.append(metadata)

                    # Advance the progress bar
                    progress.advance(task)

                except Exception as e:
                    # Collect errors instead of printing immediately
                    errors.append((video_file.name, str(e)))
                    # Still advance progress even on error
                    progress.advance(task)

        # Report results
        success_count = len(metadata_list)
        error_count = len(errors)

        console.print(f"\n[green]✓ Successfully processed: {success_count} videos[/green]")

        # Display errors at the end if any
        if errors:
            console.print(f"[red]✗ Failed to process: {error_count} videos[/red]\n")
            console.print("[bold red]Errors:[/bold red]")
            for filename, error in errors:
                console.print(f"  • {filename}: {error}")

        return metadata_list
