#!/usr/bin/env python3
import os
import sys
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

# Fixed base scope variable string tracking
SCOPES = ["https://www.googleapis.com/auth/youtube"]

class YouTubeAutomation:
    def __init__(self, folder_path="~/MagicScript"):
        self.folder_path = os.path.expanduser(folder_path)
        self.credentials_path = self.find_google_credentials()

    def find_google_credentials(self):
        """Scans the directory for any JSON file containing Google OAuth client data"""
        if not os.path.exists(self.folder_path):
            raise FileNotFoundError(f"Project directory not found at: {self.folder_path}")

        for filename in os.listdir(self.folder_path):
            if filename.endswith(".json") and not filename.startswith("token"):
                full_path = os.path.join(self.folder_path, filename)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if "client_id" in content and "client_secret" in content:
                            print(f"[INFO] Automatically detected credentials file: {filename}")
                            return full_path
                except Exception:
                    continue
        return os.path.join(self.folder_path, "credentials.json")

    def get_service(self, channel_profile="Default"):
        """Authenticates a specific channel profile using its own token file"""
        credentials = None

        safe_profile_name = channel_profile.replace(" ", "_")
        token_path = os.path.join(self.folder_path, f"token_{safe_profile_name}.json")

        if os.path.exists(token_path):
            credentials = Credentials.from_authorized_user_file(token_path, SCOPES) # <-- Use SCOPES variable

        if not credentials or not credentials.valid:
            if credentials and credentials.expired and credentials.refresh_token:
                credentials.refresh(Request())
            else:
                if not os.path.exists(self.credentials_path):
                    raise FileNotFoundError(f"Missing Google credential JSON in: '{self.folder_path}'")

                # Enforce true scope parameters across the active flow installer setup
                flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                    self.credentials_path, scopes=SCOPES # <-- Use SCOPES variable
                )
                credentials = flow.run_local_server(port=0)

            with open(token_path, "w") as token:
                token.write(credentials.to_authorized_user_file())

        return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

    def fetch_recent_videos(self, channel_profile):
        """Fetches the 10 most recent videos from a specific channel profile"""
        try:
            youtube = self.get_service(channel_profile)
            channel_request = youtube.channels().list(mine=True, part="contentDetails")
            channel_response = channel_request.execute()

            if not channel_response.get("items"):
                return False, "Could not find your YouTube channel."

            uploads_playlist_id = channel_response["items"]["contentDetails"]["relatedPlaylists"]["uploads"]

            playlist_request = youtube.playlistItems().list(
                part="snippet",
                playlistId=uploads_playlist_id,
                maxResults=10
            )
            playlist_response = playlist_request.execute()

            video_list = []
            for item in playlist_response.get("items", []):
                title = item["snippet"]["title"]
                video_id = item["snippet"]["resourceId"]["videoId"]
                video_list.append({"title": title, "id": video_id})

            return True, video_list
        except Exception as e:
            return False, f"Failed to fetch videos: {str(e)}"

    def update_description(self, video_id, new_content, channel_profile):
        """Prepends new text content to the description of a specific channel profile"""
        try:
            youtube = self.get_service(channel_profile)
            request = youtube.videos().list(part="snippet", id=video_id)
            response = request.execute()

            if not response["items"]:
                return False, f"Video ID '{video_id}' not found."

            video_item = response["items"]
            snippet = video_item["snippet"]

            old_desc = snippet.get("description", "")
            snippet["description"] = f"{new_content}\n\n---\n\n{old_desc}"

            update_request = youtube.videos().update(
                part="snippet",
                body={"id": video_id, "snippet": snippet}
            )
            update_request.execute()
            return True, "YouTube description updated successfully!"
        except googleapiclient.errors.HttpError as e:
            return False, f"Google API Error: {e.reason}"
        except Exception as e:
            return False, f"Unexpected connection error: {str(e)}"
