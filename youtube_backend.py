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
                token.write(credentials.to_json())

        return googleapiclient.discovery.build("youtube", "v3", credentials=credentials)

    def _cache_path(self, channel_profile):
        safe = channel_profile.replace(" ", "_")
        return os.path.join(self.folder_path, f"cache_{safe}.json")

    def _load_cache(self, channel_profile):
        import json, time
        path = self._cache_path(channel_profile)
        if not os.path.exists(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if time.time() - data.get("timestamp", 0) > 86400:  # 24hr TTL
                return None
            return data["videos"]
        except Exception:
            return None

    def _save_cache(self, channel_profile, video_list):
        import json, time
        path = self._cache_path(channel_profile)
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"timestamp": time.time(), "videos": video_list}, f)
        except Exception:
            pass  # cache write failure is non-fatal

    def fetch_recent_videos(self, channel_profile, force_refresh=False):
        """Fetches the 10 most recent videos from a specific channel profile.
        Results are cached to disk per profile with a 24hr TTL.
        Pass force_refresh=True (Refresh List button) to bypass the cache."""
        if not force_refresh:
            cached = self._load_cache(channel_profile)
            if cached is not None:
                return True, cached
        try:
            youtube = self.get_service(channel_profile)
            channel_request = youtube.channels().list(mine=True, part="contentDetails")
            channel_response = channel_request.execute()

            if not channel_response.get("items"):
                return False, "Could not find your YouTube channel."

            uploads_playlist_id = channel_response["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

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

            self._save_cache(channel_profile, video_list)
            return True, video_list
        except Exception as e:
            import traceback
            return False, f"Failed to fetch videos: {traceback.format_exc()}"

    def check_hdr_status(self, video_id):
        """
        Uses yt-dlp to check whether HDR streams are present for a video.
        Passes --cookies-from-browser firefox to handle private/unlisted videos.
        Returns a dict: {status, hdr_active, profile, message}
        """
        import subprocess, json

        url = f"https://www.youtube.com/watch?v={video_id}"
        cmd = [
            "yt-dlp",
            "--dump-json",
            "--skip-download",
            "--no-playlist",
            "--quiet",
            "--js-runtimes", "node",
            "--remote-components", "ejs:github",
            "--cookies-from-browser", "firefox",
            "--no-update",
            url
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            # Private or unavailable video
            if "Private video" in result.stderr or "Sign in" in result.stderr:
                return {"status": "error", "hdr_active": False, "profile": None,
                        "message": "Private/unlisted video — authentication may have failed"}

            if not result.stdout.strip():
                err = result.stderr.strip().splitlines()[-1] if result.stderr.strip() else "No output from yt-dlp"
                return {"status": "error", "hdr_active": False, "profile": None,
                        "message": err}

            data = json.loads(result.stdout)
            dynamic_ranges = [
                f.get("dynamic_range", "")
                for f in data.get("formats", [])
                if f.get("dynamic_range")
            ]

            hdr_profiles = [r for r in dynamic_ranges if r not in ("SDR", "")]
            if hdr_profiles:
                profile = hdr_profiles[0]  # e.g. 'HDR10', 'HLG'
                return {"status": "success", "hdr_active": True, "profile": profile,
                        "message": None}

            return {"status": "success", "hdr_active": False, "profile": "SDR",
                    "message": None}

        except subprocess.TimeoutExpired:
            return {"status": "error", "hdr_active": False, "profile": None,
                    "message": "yt-dlp timed out after 30s"}
        except Exception as e:
            import traceback
            return {"status": "error", "hdr_active": False, "profile": None,
                    "message": traceback.format_exc()}

    def update_description(self, video_id, new_content, channel_profile):
        """Prepends new text content to the description of a specific channel profile"""
        try:
            youtube = self.get_service(channel_profile)
            request = youtube.videos().list(part="snippet", id=video_id)
            response = request.execute()

            if not response["items"]:
                return False, f"Video ID '{video_id}' not found."

            video_item = response["items"][0]
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
