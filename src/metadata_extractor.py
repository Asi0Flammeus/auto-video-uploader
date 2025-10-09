import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


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
    youtube_id: Optional[str] = None
    peertube_id: Optional[str] = None


class MetadataExtractor:
    def __init__(self, bec_repo_path: str):
        self.bec_repo = Path(bec_repo_path)
        self.courses_dir = self.bec_repo / "courses"

        if not self.courses_dir.exists():
            raise ValueError(f"Courses directory not found at {self.courses_dir}")

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
                         chapter_index: int, code_language: str) -> str:
        """
        Extract chapter title based on part and chapter indices
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

        # Helper function to check if partId/chapterId exists within next few lines
        def has_tag_nearby(lines_list, start_idx, tag_name, max_distance=5):
            """Check if a tag exists within max_distance lines after start_idx"""
            for j in range(start_idx + 1, min(start_idx + 1 + max_distance, len(lines_list))):
                if tag_name.lower() in lines_list[j].lower():
                    return True
            return False

        for i, line in enumerate(lines):
            # Skip frontmatter
            if line.strip() == '---':
                in_frontmatter = not in_frontmatter
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
                        return chapter_title

        # Fallback if chapter not found
        return f"Chapter {part_index}.{chapter_index}"

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
        {course index upper case with space} -- {course title in code_language}

        Note: This returns ONLY the base description without footer.
        Footer should be appended during upload.
        """
        course_display = course_index.upper()
        if course_display.startswith('BTC') and len(course_display) > 3:
            course_display = f"{course_display[:3]} {course_display[3:]}"

        return f"{course_display} -- {course_title}"

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

    def extract_metadata(self, video_filename: str) -> VideoMetadata:
        """
        Extract all metadata from a video filename
        """
        try:
            # Parse filename
            course_index, part_index, chapter_index, code_language = self.parse_filename(video_filename)

            # Get course and chapter titles
            course_title = self.get_course_title(course_index, code_language)
            chapter_title = self.get_chapter_title(course_index, part_index,
                                                  chapter_index, code_language)

            # Generate video title and description
            video_title = self.generate_video_title(course_index, part_index,
                                                   chapter_index, chapter_title)
            video_description = self.generate_video_description(course_index, course_title)

            return VideoMetadata(
                filename=video_filename,
                course_index=course_index,
                part_index=part_index,
                chapter_index=chapter_index,
                code_language=code_language,
                title=video_title,
                description=video_description,
                chapter_title=chapter_title,
                course_title=course_title
            )
        except Exception as e:
            raise Exception(f"Error processing {video_filename}: {str(e)}")

    def process_videos_in_folder(self, folder_path: Path) -> List[VideoMetadata]:
        """
        Process all video files in a given folder
        """
        metadata_list = []

        # Find all .mp4 files in the folder
        video_files = list(folder_path.glob("*.mp4"))

        if not video_files:
            print(f"No video files found in {folder_path}")
            return metadata_list

        for video_file in video_files:
            try:
                metadata = self.extract_metadata(video_file.name)
                metadata_list.append(metadata)
                print(f"✓ Processed: {video_file.name}")
            except Exception as e:
                print(f"✗ Error processing {video_file.name}: {e}")

        return metadata_list