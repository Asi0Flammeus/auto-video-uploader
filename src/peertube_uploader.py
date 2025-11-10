import requests
import urllib3
from pathlib import Path
from typing import Optional
from dataclasses import dataclass
import logging
from .thumbnail_generator import ThumbnailGenerator

# Disable SSL warnings when SSL verification is disabled
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)


@dataclass
class PeerTubeUploadResult:
    success: bool
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None


class PeerTubeUploader:
    def __init__(self, instance_url: str, username: str, password: str, upload_endpoint: Optional[str] = None, verify_ssl: bool = True):
        """
        Initialize PeerTube uploader

        Args:
            instance_url: PeerTube instance URL (e.g., https://peertube.example.com)
            username: PeerTube username
            password: PeerTube password
            upload_endpoint: Optional upload endpoint URL (e.g., https://upload.peertube.example.com)
                           If not provided, uses instance_url for uploads
            verify_ssl: Whether to verify SSL certificates (default: True)
        """
        self.instance_url = instance_url.rstrip('/')
        self.upload_endpoint = upload_endpoint.rstrip('/') if upload_endpoint else self.instance_url
        self.username = username
        self.password = password
        self.verify_ssl = verify_ssl
        self.access_token = None
        self.client_id = None
        self.client_secret = None

    def authenticate(self) -> bool:
        """Authenticate with PeerTube instance"""
        try:
            # Get client credentials
            client_response = requests.get(f"{self.instance_url}/api/v1/oauth-clients/local")

            if client_response.status_code != 200:
                raise Exception(f"Failed to get client credentials: {client_response.text}")

            client_data = client_response.json()
            self.client_id = client_data['client_id']
            self.client_secret = client_data['client_secret']

            # Get access token
            token_data = {
                'client_id': self.client_id,
                'client_secret': self.client_secret,
                'grant_type': 'password',
                'response_type': 'code',
                'username': self.username,
                'password': self.password
            }

            token_response = requests.post(
                f"{self.instance_url}/api/v1/users/token",
                data=token_data
            )

            if token_response.status_code != 200:
                raise Exception(f"Authentication failed: {token_response.text}")

            token_json = token_response.json()
            self.access_token = token_json['access_token']

            return True

        except Exception as e:
            print(f"PeerTube authentication error: {str(e)}")
            return False

    def get_playlist_by_name(self, display_name: str) -> Optional[str]:
        """
        Find a playlist by display name

        Args:
            display_name: Playlist display name to search for

        Returns:
            Playlist ID if found, None otherwise
        """
        if not self.access_token:
            return None

        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }

            # Get account name
            account_response = requests.get(
                f"{self.instance_url}/api/v1/accounts/{self.username}",
                headers=headers
            )

            if account_response.status_code != 200:
                return None

            # Get playlists for this account
            playlists_response = requests.get(
                f"{self.instance_url}/api/v1/accounts/{self.username}/video-playlists",
                headers=headers
            )

            if playlists_response.status_code != 200:
                return None

            playlists = playlists_response.json().get('data', [])
            for playlist in playlists:
                if playlist.get('displayName') == display_name:
                    return str(playlist.get('id'))

            return None

        except Exception as e:
            print(f"  Warning: Failed to search playlists: {str(e)}")
            return None

    def create_playlist(self, display_name: str, description: str = "", privacy: int = 2) -> Optional[str]:
        """
        Create a new playlist

        Args:
            display_name: Playlist display name
            description: Playlist description
            privacy: Privacy level (1=public, 2=unlisted, 3=private)

        Returns:
            Playlist ID if created successfully, None otherwise
        """
        if not self.access_token:
            return None

        try:
            # Get default channel
            channel_response = requests.get(
                f"{self.instance_url}/api/v1/video-channels/{self.username}_channel",
                headers={'Authorization': f'Bearer {self.access_token}'}
            )

            if channel_response.status_code != 200:
                # Fallback: get user's channels
                channels_response = requests.get(
                    f"{self.instance_url}/api/v1/accounts/{self.username}/video-channels",
                    headers={'Authorization': f'Bearer {self.access_token}'}
                )
                if channels_response.status_code == 200:
                    channels = channels_response.json()['data']
                    if channels:
                        video_channel_id = channels[0]['id']
                    else:
                        return None
                else:
                    return None
            else:
                video_channel_id = channel_response.json()['id']

            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            body = {
                "displayName": display_name,
                "description": description,
                "privacy": privacy,
                "videoChannelId": video_channel_id
            }

            response = requests.post(
                f"{self.instance_url}/api/v1/video-playlists",
                headers=headers,
                json=body
            )

            if response.status_code in [200, 201]:
                playlist_data = response.json()
                playlist_id = str(playlist_data['videoPlaylist']['id'])
                print(f"  ✅ PeerTube: Created playlist '{display_name}' ({playlist_id})")
                return playlist_id
            else:
                print(f"  ❌ PeerTube: Failed to create playlist: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            print(f"  ❌ PeerTube: Failed to create playlist: {str(e)}")
            return None

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        Add a video to a playlist

        Args:
            playlist_id: Playlist ID
            video_id: Video ID (UUID or shortUUID) to add

        Returns:
            True if added successfully, False otherwise
        """
        if not self.access_token:
            return False

        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}',
                'Content-Type': 'application/json'
            }

            body = {
                "videoId": video_id
            }

            response = requests.post(
                f"{self.instance_url}/api/v1/video-playlists/{playlist_id}/videos",
                headers=headers,
                json=body
            )

            if response.status_code in [200, 201]:
                print(f"  ✅ PeerTube: Added video to playlist")
                return True
            else:
                print(f"  ❌ PeerTube: Failed to add video to playlist: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"  ❌ PeerTube: Failed to add video to playlist: {str(e)}")
            return False

    def delete_video(self, video_id: str) -> bool:
        """
        Delete a video from PeerTube

        Args:
            video_id: PeerTube video ID (UUID or shortUUID) to delete

        Returns:
            True if deletion successful, False otherwise
        """
        if not self.access_token:
            print("  Not authenticated. Call authenticate() first.")
            return False

        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }

            response = requests.delete(
                f"{self.instance_url}/api/v1/videos/{video_id}",
                headers=headers
            )

            if response.status_code == 204:
                print(f"  ✅ PeerTube: Deleted video {video_id}")
                return True
            else:
                print(f"  ❌ PeerTube: Failed to delete video {video_id}: {response.status_code} - {response.text}")
                return False

        except Exception as e:
            print(f"  ❌ PeerTube: Failed to delete video {video_id}: {str(e)}")
            return False

    def upload_thumbnail(self, video_uuid: str, thumbnail_path: Path) -> bool:
        """
        Upload a thumbnail image for a video using the PUT /api/v1/videos/{id} endpoint.
        
        This uses the main video update endpoint as per PeerTube API documentation.
        The thumbnail is sent as 'thumbnailfile' in multipart/form-data.
        
        Args:
            video_uuid: Video UUID or shortUUID
            thumbnail_path: Path to thumbnail image file
            
        Returns:
            True if upload successful, False otherwise
        """
        if not self.access_token:
            logger.error("Not authenticated. Call authenticate() first.")
            return False
        
        if not thumbnail_path.exists():
            logger.error(f"Thumbnail file not found: {thumbnail_path}")
            return False
        
        # Check file size (PeerTube limit is 4MB for thumbnails)
        file_size = thumbnail_path.stat().st_size
        if file_size > 4 * 1024 * 1024:
            logger.error(f"Thumbnail file too large: {file_size} bytes (max 4MB)")
            return False
        
        try:
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }
            
            # Open and prepare the thumbnail file
            with open(thumbnail_path, 'rb') as f:
                # Use multipart/form-data with thumbnailfile field
                # According to PeerTube OpenAPI spec:
                # - Field name: thumbnailfile
                # - Type: string, format: binary
                # - Content type: image/jpeg
                files = {
                    'thumbnailfile': (
                        'thumbnail.jpg',  # filename
                        f,                # file object
                        'image/jpeg'      # MIME type
                    )
                }
                
                logger.debug(f"Uploading thumbnail: size={file_size} bytes, video_uuid={video_uuid}")
                
                # Use PUT /api/v1/videos/{id} endpoint
                # This is the correct endpoint for updating video metadata including thumbnail
                url = f"{self.instance_url}/api/v1/videos/{video_uuid}"
                
                logger.debug(f"Using PUT endpoint: {url}")
                
                response = requests.put(
                    url,
                    headers=headers,
                    files=files,
                    verify=self.verify_ssl
                )
            
            # Check response
            if response.status_code in [200, 201, 204]:
                logger.info(f"  ✅ PeerTube: Thumbnail uploaded successfully")
                return True
            elif response.status_code == 404:
                logger.error(f"  ❌ PeerTube: Video not found (404): {video_uuid}")
                # Try with upload endpoint if configured and different
                if self.upload_endpoint != self.instance_url:
                    logger.debug("Trying with upload endpoint...")
                    with open(thumbnail_path, 'rb') as f:
                        files = {
                            'thumbnailfile': ('thumbnail.jpg', f, 'image/jpeg')
                        }
                        response = requests.put(
                            f"{self.upload_endpoint}/api/v1/videos/{video_uuid}",
                            headers=headers,
                            files=files,
                            verify=self.verify_ssl
                        )
                        if response.status_code in [200, 201, 204]:
                            logger.info(f"  ✅ PeerTube: Thumbnail uploaded successfully via upload endpoint")
                            return True
                return False
            elif response.status_code == 403:
                logger.error(f"  ❌ PeerTube: Permission denied (403) - you don't have rights to update this video")
                return False
            elif response.status_code == 413:
                logger.error(f"  ❌ PeerTube: File too large (413) - {file_size} bytes")
                return False
            elif response.status_code == 415:
                logger.error(f"  ❌ PeerTube: Unsupported media type (415)")
                logger.error(f"     Ensure the file is a valid JPEG/PNG image")
                return False
            elif response.status_code == 400:
                # Parse error message
                error_msg = "Bad request"
                try:
                    error_data = response.json()
                    if isinstance(error_data, dict):
                        if 'error' in error_data:
                            error_msg = error_data['error']
                        elif 'message' in error_data:
                            error_msg = error_data['message']
                        elif 'errors' in error_data:
                            # Handle validation errors
                            errors = error_data['errors']
                            if isinstance(errors, dict) and 'thumbnailfile' in errors:
                                thumb_errors = errors['thumbnailfile']
                                if isinstance(thumb_errors, list) and thumb_errors:
                                    error_msg = f"thumbnailfile: {thumb_errors[0].get('msg', thumb_errors[0])}"
                            elif isinstance(errors, list) and errors:
                                error_msg = errors[0].get('msg', str(errors[0]))
                except:
                    error_msg = response.text[:500] if response.text else "No error details"
                
                logger.error(f"  ❌ PeerTube: Bad request (400) - {error_msg}")
                
                # Additional debugging info
                if "not supported" in error_msg.lower() or "too large" in error_msg.lower():
                    logger.error(f"     File info: size={file_size} bytes, path={thumbnail_path}")
                    logger.error(f"     Ensure file is <4MB and is a valid image format")
                
                return False
            else:
                logger.error(f"  ❌ PeerTube: Unexpected response ({response.status_code})")
                if response.text:
                    logger.error(f"     Response: {response.text[:200]}")
                return False
                
        except requests.exceptions.SSLError:
            logger.error(f"  ❌ PeerTube: SSL error - try setting PEERTUBE_VERIFY_SSL=false in .env")
            return False
        except requests.exceptions.ConnectionError as e:
            logger.error(f"  ❌ PeerTube: Connection error - {str(e)}")
            return False
        except Exception as e:
            logger.error(f"  ❌ PeerTube: Exception during upload: {str(e)}")
            import traceback
            logger.debug(traceback.format_exc())
            return False
    
    def set_video_thumbnail_at_timestamp(self, video_path: Path, video_uuid: str, 
                                        timestamp: int = 4) -> bool:
        """
        Extract a frame from video and set it as thumbnail.
        
        Args:
            video_path: Path to local video file
            video_uuid: Video UUID or shortUUID
            timestamp: Time in seconds to extract frame (default: 4)
            
        Returns:
            True if thumbnail was set successfully, False otherwise
        """
        try:
            with ThumbnailGenerator(thumbnail_time=timestamp) as generator:
                # Extract thumbnail frame
                thumbnail_path = generator.extract_frame(video_path, timestamp=timestamp)
                
                if not thumbnail_path:
                    logger.warning(f"Failed to extract thumbnail from {video_path}")
                    return False
                
                # Upload thumbnail
                success = self.upload_thumbnail(video_uuid, thumbnail_path)
                
                # Cleanup is handled by context manager
                return success
                
        except Exception as e:
            logger.error(f"Failed to set video thumbnail: {str(e)}")
            return False

    def upload_video(self, video_path: Path, title: str, description: str,
                     channel_id: Optional[int] = None,
                     privacy: int = 2,  # 1=Public, 2=Unlisted, 3=Private
                     category: int = 15,  # 15=Science & Technology
                     language: str = "en",
                     auto_thumbnail: bool = True) -> PeerTubeUploadResult:
        """
        Upload video to PeerTube

        Args:
            video_path: Path to video file
            title: Video title
            description: Video description
            channel_id: Channel ID (if None, uses default channel)
            privacy: Privacy setting (2 = unlisted)
            category: Category ID (15 = Science & Technology)
            language: Video language code
            auto_thumbnail: Automatically set thumbnail at 4 seconds (default: True)

        Returns:
            PeerTubeUploadResult with upload status and video info
        """
        if not self.access_token:
            return PeerTubeUploadResult(
                success=False,
                error="Not authenticated. Call authenticate() first."
            )

        if not video_path.exists():
            return PeerTubeUploadResult(
                success=False,
                error=f"Video file not found: {video_path}"
            )

        try:
            # Get default channel if channel_id not provided
            if channel_id is None:
                channel_response = requests.get(
                    f"{self.instance_url}/api/v1/video-channels/{self.username}_channel",
                    headers={'Authorization': f'Bearer {self.access_token}'}
                )

                if channel_response.status_code == 200:
                    channel_id = channel_response.json()['id']
                else:
                    # Fallback: get user's channels
                    channels_response = requests.get(
                        f"{self.instance_url}/api/v1/accounts/{self.username}/video-channels",
                        headers={'Authorization': f'Bearer {self.access_token}'}
                    )
                    if channels_response.status_code == 200:
                        channels = channels_response.json()['data']
                        if channels:
                            channel_id = channels[0]['id']
                        else:
                            return PeerTubeUploadResult(
                                success=False,
                                error="No channels found for this account"
                            )

            # Prepare video metadata
            metadata = {
                'name': title,
                'description': description,
                'channelId': str(channel_id),
                'privacy': str(privacy),
                'category': str(category),
                'language': language,
                'nsfw': 'false',
                'waitTranscoding': 'true'
            }

            # Extract thumbnail before upload if auto_thumbnail is enabled
            thumbnail_path = None
            if auto_thumbnail:
                print(f"  PeerTube: Extracting thumbnail at 4s...")
                try:
                    with ThumbnailGenerator(thumbnail_time=4) as generator:
                        thumbnail_path = generator.extract_frame(video_path, timestamp=4)
                        if thumbnail_path:
                            print(f"  PeerTube: Thumbnail extracted successfully")
                        else:
                            print(f"  PeerTube: Warning - thumbnail extraction failed, uploading without thumbnail")
                except Exception as e:
                    logger.warning(f"Failed to extract thumbnail: {e}")
                    thumbnail_path = None

            # Prepare file upload
            files = {
                'videofile': (video_path.name, open(video_path, 'rb'), 'video/mp4')
            }
            
            # Add thumbnail to upload if available
            if thumbnail_path and thumbnail_path.exists():
                files['thumbnailfile'] = ('thumbnail.jpg', open(thumbnail_path, 'rb'), 'image/jpeg')
                print(f"  PeerTube: Including thumbnail in upload")

            # Upload video
            headers = {
                'Authorization': f'Bearer {self.access_token}'
            }

            print(f"  PeerTube upload: Starting upload to {self.upload_endpoint}...")

            response = requests.post(
                f"{self.upload_endpoint}/api/v1/videos/upload",
                headers=headers,
                data=metadata,
                files=files,
                verify=self.verify_ssl
            )

            # Close the files
            files['videofile'][1].close()
            if 'thumbnailfile' in files:
                files['thumbnailfile'][1].close()
            
            # Clean up thumbnail temp file if it was created
            if thumbnail_path and thumbnail_path.exists():
                try:
                    thumbnail_path.unlink()
                except Exception as e:
                    logger.debug(f"Failed to cleanup temp thumbnail: {e}")

            if response.status_code not in [200, 201]:
                return PeerTubeUploadResult(
                    success=False,
                    error=f"Upload failed with status {response.status_code}: {response.text}"
                )

            video_data = response.json()
            video_uuid = video_data['video']['uuid']
            # Try to get shortUUID if available, otherwise use full UUID
            video_short_uuid = video_data['video'].get('shortUUID', video_uuid)
            video_url = f"{self.instance_url}/w/{video_short_uuid}"

            print(f"  PeerTube upload: Complete")
            
            # Thumbnail was already included in upload if auto_thumbnail was enabled
            if auto_thumbnail and thumbnail_path:
                print(f"  ✅ PeerTube: Video uploaded with thumbnail at 4s")

            return PeerTubeUploadResult(
                success=True,
                video_id=video_short_uuid,
                video_url=video_url
            )

        except Exception as e:
            # Clean up thumbnail temp file on error
            if thumbnail_path and thumbnail_path.exists():
                try:
                    thumbnail_path.unlink()
                except:
                    pass
            
            return PeerTubeUploadResult(
                success=False,
                error=f"Upload failed: {str(e)}"
            )
