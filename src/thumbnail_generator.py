import subprocess
import tempfile
import os
from pathlib import Path
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ThumbnailGenerator:
    """
    Utility class for extracting thumbnail frames from videos using ffmpeg.
    Default extraction time is 4 seconds into the video.
    """
    
    THUMBNAIL_TIME = 4  # Default time in seconds
    DEFAULT_WIDTH = 1280
    DEFAULT_HEIGHT = 720
    MAX_FILE_SIZE = 4 * 1024 * 1024  # 4MB limit for PeerTube
    
    def __init__(self, thumbnail_time: int = THUMBNAIL_TIME):
        """
        Initialize thumbnail generator.
        
        Args:
            thumbnail_time: Time in seconds to extract frame (default: 4)
        """
        self.thumbnail_time = thumbnail_time
        self.temp_files = []
        
    def _get_video_duration(self, video_path: str) -> Optional[float]:
        """
        Get video duration in seconds using ffprobe.
        
        Args:
            video_path: Path to video file or URL
            
        Returns:
            Duration in seconds or None if error
        """
        try:
            cmd = [
                'ffprobe',
                '-v', 'error',
                '-show_entries', 'format=duration',
                '-of', 'default=noprint_wrappers=1:nokey=1',
                video_path
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout:
                return float(result.stdout.strip())
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, ValueError) as e:
            logger.warning(f"Failed to get video duration: {e}")
        
        return None
    
    def _calculate_extraction_time(self, video_path: str) -> float:
        """
        Calculate the best time to extract thumbnail.
        Uses 4 seconds if video is long enough, otherwise 50% of duration.
        
        Args:
            video_path: Path to video file or URL
            
        Returns:
            Time in seconds to extract frame
        """
        duration = self._get_video_duration(video_path)
        
        if duration is None:
            # Fallback to default if can't get duration
            return self.thumbnail_time
        
        if duration >= self.thumbnail_time:
            return self.thumbnail_time
        else:
            # Use 50% of video duration for short videos
            return duration * 0.5
    
    def extract_frame(self, video_path: Path, timestamp: Optional[float] = None,
                     output_path: Optional[Path] = None) -> Optional[Path]:
        """
        Extract a frame from a local video file at specified timestamp.
        
        Args:
            video_path: Path to local video file
            timestamp: Time in seconds to extract frame (default: 4 seconds)
            output_path: Optional output path for thumbnail (default: temp file)
            
        Returns:
            Path to extracted thumbnail image or None if failed
        """
        if not video_path.exists():
            logger.error(f"Video file not found: {video_path}")
            return None
        
        video_path_str = str(video_path)
        
        # Calculate extraction time if not provided
        if timestamp is None:
            timestamp = self._calculate_extraction_time(video_path_str)
        
        # Create output path if not provided
        if output_path is None:
            temp_fd, temp_path = tempfile.mkstemp(suffix='.jpg', prefix='thumb_')
            os.close(temp_fd)
            output_path = Path(temp_path)
            self.temp_files.append(output_path)
        
        try:
            # First attempt with lower quality for smaller file size
            cmd = [
                'ffmpeg',
                '-ss', str(timestamp),  # Seek to timestamp
                '-i', video_path_str,   # Input file
                '-vf', f'scale={self.DEFAULT_WIDTH}:{self.DEFAULT_HEIGHT}:force_original_aspect_ratio=decrease,pad={self.DEFAULT_WIDTH}:{self.DEFAULT_HEIGHT}:(ow-iw)/2:(oh-ih)/2',  # Scale and pad to maintain aspect ratio
                '-vframes', '1',        # Extract 1 frame
                '-q:v', '5',           # JPEG quality (5 is good quality, smaller file)
                '-f', 'image2',        # Force image format
                str(output_path),      # Output file
                '-y'                   # Overwrite if exists
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            
            if result.returncode == 0 and output_path.exists():
                # Check file size and reduce quality if needed
                file_size = output_path.stat().st_size
                quality = 5
                
                while file_size > self.MAX_FILE_SIZE and quality <= 20:
                    logger.debug(f"Thumbnail too large ({file_size} bytes), reducing quality to {quality}")
                    quality += 3
                    cmd[cmd.index('-q:v') + 1] = str(quality)
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    if result.returncode == 0:
                        file_size = output_path.stat().st_size
                    else:
                        break
                
                if file_size > self.MAX_FILE_SIZE:
                    # Last resort: reduce resolution
                    logger.warning(f"Thumbnail still too large, reducing resolution")
                    cmd[cmd.index('-vf') + 1] = f'scale=854:480:force_original_aspect_ratio=decrease,pad=854:480:(ow-iw)/2:(oh-ih)/2'
                    cmd[cmd.index('-q:v') + 1] = '10'
                    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
                    file_size = output_path.stat().st_size
                
                if result.returncode == 0 and output_path.exists() and file_size <= self.MAX_FILE_SIZE:
                    logger.info(f"Extracted thumbnail at {timestamp}s: {output_path} (size: {file_size} bytes)")
                    return output_path
                else:
                    logger.error(f"ffmpeg failed or file too large: {result.stderr if result.returncode != 0 else f'Size: {file_size}'}")
                    if output_path.exists():
                        output_path.unlink()
                    return None
            else:
                logger.error(f"ffmpeg failed: {result.stderr}")
                if output_path.exists():
                    output_path.unlink()
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg timeout extracting frame from {video_path}")
            if output_path.exists():
                output_path.unlink()
            return None
        except Exception as e:
            logger.error(f"Error extracting frame: {e}")
            if output_path.exists():
                output_path.unlink()
            return None
    
    def extract_frame_from_url(self, video_url: str, timestamp: Optional[float] = None,
                              output_path: Optional[Path] = None) -> Optional[Path]:
        """
        Extract a frame from a video URL (streaming) at specified timestamp.
        
        Args:
            video_url: URL to video file
            timestamp: Time in seconds to extract frame (default: 4 seconds)
            output_path: Optional output path for thumbnail (default: temp file)
            
        Returns:
            Path to extracted thumbnail image or None if failed
        """
        # Calculate extraction time if not provided
        if timestamp is None:
            timestamp = self._calculate_extraction_time(video_url)
        
        # Create output path if not provided
        if output_path is None:
            temp_fd, temp_path = tempfile.mkstemp(suffix='.jpg', prefix='thumb_')
            os.close(temp_fd)
            output_path = Path(temp_path)
            self.temp_files.append(output_path)
        
        try:
            # Use more reliable settings for URL streaming
            # Adding timeout and reconnect flags for better stability
            cmd = [
                'ffmpeg',
                '-reconnect', '1',                # Enable reconnection
                '-reconnect_at_eof', '1',        # Reconnect at EOF
                '-reconnect_streamed', '1',      # Reconnect for streamed protocols
                '-reconnect_delay_max', '5',     # Max reconnect delay
                '-timeout', '10000000',          # 10 second timeout (microseconds)
                '-ss', str(timestamp),           # Seek before input (faster for remote)
                '-i', video_url,                 # Input URL
                '-vf', f'scale=640:360:force_original_aspect_ratio=decrease,pad=640:360:(ow-iw)/2:(oh-ih)/2',  # Smaller size for reliability
                '-vframes', '1',                 # Extract 1 frame
                '-q:v', '5',                     # Good quality
                '-f', 'mjpeg',                   # Force MJPEG format (more reliable than image2)
                str(output_path),                # Output file
                '-y'                             # Overwrite if exists
            ]
            
            # Longer timeout for network operations
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
            
            if result.returncode == 0 and output_path.exists():
                file_size = output_path.stat().st_size
                
                # Validate minimum size
                if file_size < 100:
                    logger.error(f"Thumbnail too small ({file_size} bytes), likely corrupted")
                    output_path.unlink()
                    return None
                
                # Check if file is within size limit
                if file_size > self.MAX_FILE_SIZE:
                    logger.warning(f"Thumbnail too large ({file_size} bytes), retrying with lower quality")
                    # Retry with lower quality and smaller resolution
                    cmd_retry = [
                        'ffmpeg', '-reconnect', '1', '-reconnect_at_eof', '1',
                        '-reconnect_streamed', '1', '-reconnect_delay_max', '5',
                        '-timeout', '10000000', '-ss', str(timestamp), '-i', video_url,
                        '-vf', 'scale=480:270:force_original_aspect_ratio=decrease,pad=480:270:(ow-iw)/2:(oh-ih)/2',
                        '-vframes', '1', '-q:v', '10', '-f', 'mjpeg',
                        str(output_path), '-y'
                    ]
                    result = subprocess.run(cmd_retry, capture_output=True, text=True, timeout=90)
                    if result.returncode == 0 and output_path.exists():
                        file_size = output_path.stat().st_size
                
                # Validate JPEG file
                if file_size > 100 and file_size <= self.MAX_FILE_SIZE:
                    try:
                        with open(output_path, 'rb') as f:
                            header = f.read(3)
                            # Check for JPEG SOI marker (0xFFD8) and first byte of next marker
                            if not (header[0] == 0xFF and header[1] == 0xD8 and header[2] == 0xFF):
                                logger.error("Invalid JPEG file format")
                                output_path.unlink()
                                return None
                    except Exception as e:
                        logger.error(f"Failed to validate JPEG: {e}")
                        output_path.unlink()
                        return None
                    
                    logger.info(f"Extracted thumbnail from URL at {timestamp}s (size: {file_size} bytes)")
                    return output_path
                else:
                    logger.error(f"Invalid thumbnail: size={file_size} bytes")
                    if output_path.exists():
                        output_path.unlink()
                    return None
            else:
                logger.error(f"ffmpeg failed for URL: {result.stderr}")
                if output_path.exists():
                    output_path.unlink()
                return None
                
        except subprocess.TimeoutExpired:
            logger.error(f"ffmpeg timeout extracting frame from URL")
            if output_path.exists():
                output_path.unlink()
            return None
        except Exception as e:
            logger.error(f"Error extracting frame from URL: {e}")
            if output_path.exists():
                output_path.unlink()
            return None
    
    def cleanup_temp_files(self):
        """Remove all temporary files created by this instance."""
        for temp_file in self.temp_files:
            if temp_file.exists():
                try:
                    temp_file.unlink()
                    logger.debug(f"Cleaned up temp file: {temp_file}")
                except Exception as e:
                    logger.warning(f"Failed to cleanup {temp_file}: {e}")
        self.temp_files.clear()
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup temp files."""
        self.cleanup_temp_files()