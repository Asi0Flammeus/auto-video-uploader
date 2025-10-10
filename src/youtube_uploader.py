import os
import pickle
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError


SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']


@dataclass
class YouTubeUploadResult:
    success: bool
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None


class YouTubeUploader:
    def __init__(self, client_secrets_file: str, credentials_file: str = 'youtube_credentials.pickle'):
        """
        Initialize YouTube uploader

        Args:
            client_secrets_file: Path to OAuth2 client secrets JSON file
            credentials_file: Path to store credentials pickle file
        """
        self.client_secrets_file = client_secrets_file
        self.credentials_file = credentials_file
        self.youtube = None

    def authenticate(self):
        """Authenticate with YouTube API using OAuth2"""
        creds = None

        # Load existing credentials
        if os.path.exists(self.credentials_file):
            with open(self.credentials_file, 'rb') as token:
                creds = pickle.load(token)

        # If credentials don't exist or are invalid, get new ones
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets_file, SCOPES)
                creds = flow.run_local_server(port=0)

            # Save credentials for future use
            with open(self.credentials_file, 'wb') as token:
                pickle.dump(creds, token)

        self.youtube = build('youtube', 'v3', credentials=creds)
        return True

    def get_playlist_by_title(self, title: str) -> Optional[str]:
        """
        Find a playlist by title

        Args:
            title: Playlist title to search for

        Returns:
            Playlist ID if found, None otherwise
        """
        if not self.youtube:
            return None

        try:
            request = self.youtube.playlists().list(
                part="snippet",
                mine=True,
                maxResults=50
            )

            while request:
                response = request.execute()

                for playlist in response.get('items', []):
                    if playlist['snippet']['title'] == title:
                        return playlist['id']

                request = self.youtube.playlists().list_next(request, response)

            return None

        except Exception as e:
            print(f"  Warning: Failed to search playlists: {str(e)}")
            return None

    def create_playlist(self, title: str, description: str = "", privacy: str = "unlisted") -> Optional[str]:
        """
        Create a new playlist

        Args:
            title: Playlist title
            description: Playlist description
            privacy: Privacy status (public, unlisted, private)

        Returns:
            Playlist ID if created successfully, None otherwise
        """
        if not self.youtube:
            return None

        try:
            request = self.youtube.playlists().insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": title,
                        "description": description
                    },
                    "status": {
                        "privacyStatus": privacy
                    }
                }
            )

            response = request.execute()
            playlist_id = response['id']
            print(f"  ✅ YouTube: Created playlist '{title}' ({playlist_id})")
            return playlist_id

        except Exception as e:
            print(f"  ❌ YouTube: Failed to create playlist: {str(e)}")
            return None

    def add_video_to_playlist(self, playlist_id: str, video_id: str) -> bool:
        """
        Add a video to a playlist

        Args:
            playlist_id: Playlist ID
            video_id: Video ID to add

        Returns:
            True if added successfully, False otherwise
        """
        if not self.youtube:
            return False

        try:
            request = self.youtube.playlistItems().insert(
                part="snippet",
                body={
                    "snippet": {
                        "playlistId": playlist_id,
                        "resourceId": {
                            "kind": "youtube#video",
                            "videoId": video_id
                        }
                    }
                }
            )

            request.execute()
            print(f"  ✅ YouTube: Added video to playlist")
            return True

        except Exception as e:
            print(f"  ❌ YouTube: Failed to add video to playlist: {str(e)}")
            return False

    def delete_video(self, video_id: str) -> bool:
        """
        Delete a video from YouTube

        Args:
            video_id: YouTube video ID to delete

        Returns:
            True if deletion successful, False otherwise
        """
        if not self.youtube:
            print("  Not authenticated. Call authenticate() first.")
            return False

        try:
            self.youtube.videos().delete(id=video_id).execute()
            print(f"  ✅ YouTube: Deleted video {video_id}")
            return True
        except HttpError as e:
            print(f"  ❌ YouTube: Failed to delete video {video_id}: {e}")
            return False
        except Exception as e:
            print(f"  ❌ YouTube: Failed to delete video {video_id}: {str(e)}")
            return False

    def upload_video(self, video_path: Path, title: str, description: str,
                     category_id: str = "27", privacy_status: str = "unlisted") -> YouTubeUploadResult:
        """
        Upload video to YouTube

        Args:
            video_path: Path to video file
            title: Video title
            description: Video description
            category_id: YouTube category ID (default: 27 = Education)
            privacy_status: Privacy setting (default: unlisted)

        Returns:
            YouTubeUploadResult with upload status and video info
        """
        if not self.youtube:
            return YouTubeUploadResult(
                success=False,
                error="Not authenticated. Call authenticate() first."
            )

        if not video_path.exists():
            return YouTubeUploadResult(
                success=False,
                error=f"Video file not found: {video_path}"
            )

        try:
            # Prepare video metadata
            body = {
                'snippet': {
                    'title': title,
                    'description': description,
                    'categoryId': category_id
                },
                'status': {
                    'privacyStatus': privacy_status,
                    'selfDeclaredMadeForKids': False
                }
            }

            # Create media upload object
            media = MediaFileUpload(
                str(video_path),
                chunksize=-1,
                resumable=True,
                mimetype='video/mp4'
            )

            # Execute upload
            request = self.youtube.videos().insert(
                part='snippet,status',
                body=body,
                media_body=media
            )

            response = None
            while response is None:
                status, response = request.next_chunk()
                if status:
                    progress = int(status.progress() * 100)
                    print(f"  YouTube upload: {progress}% complete")

            video_id = response['id']
            video_url = f"https://www.youtube.com/watch?v={video_id}"

            return YouTubeUploadResult(
                success=True,
                video_id=video_id,
                video_url=video_url
            )

        except HttpError as e:
            return YouTubeUploadResult(
                success=False,
                error=f"HTTP error: {e.resp.status} - {e.content.decode()}"
            )
        except Exception as e:
            return YouTubeUploadResult(
                success=False,
                error=f"Upload failed: {str(e)}"
            )
