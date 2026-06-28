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

    def resumable_upload(self, file_path, title, description, channel_profile, progress_callback=None):
        """
        Uploads a video file to YouTube using the channel profile's existing auth.
        Saves session to disk immediately after handshake — survives crashes and reboots.
        progress_callback(percent: float) is called each chunk if provided.
        Returns (True, video_id) or (False, error_message).
        """
        import json as _json
        import mimetypes
        import time
        import httplib2
        import requests as _requests
        from googleapiclient.http import MediaFileUpload
        from googleapiclient.errors import HttpError
        from google.auth.transport.requests import Request as GoogleRequest

        file_path = os.path.abspath(file_path)
        safe_profile = channel_profile.replace(" ", "_")
        session_file = os.path.join(self.folder_path, f"upload_session_{safe_profile}.json")

        mime_type, _ = mimetypes.guess_type(file_path)
        if not mime_type:
            mime_type = 'application/octet-stream'
        total_size = os.path.getsize(file_path)

        # ── Session helpers ────────────────────────────────────────────────────
        def save_session(upload_url):
            with open(session_file, 'w') as f:
                _json.dump({'upload_url': upload_url, 'file_path': file_path}, f)

        def load_session():
            if not os.path.exists(session_file):
                return None
            try:
                with open(session_file, 'r') as f:
                    return _json.load(f)
            except Exception:
                return None

        def clear_session():
            if os.path.exists(session_file):
                os.remove(session_file)

        def get_server_progress(upload_url):
            try:
                resp = _requests.put(
                    upload_url,
                    headers={'Content-Range': 'bytes */*', 'Content-Length': '0'},
                    allow_redirects=False
                )
                if resp.status_code == 308:
                    rng = resp.headers.get('Range', '')
                    return int(rng.split('-')[-1]) + 1 if rng else 0
                elif resp.status_code in (200, 201):
                    return -1  # already complete
            except Exception:
                pass
            return 0

        # ── Determine start state ──────────────────────────────────────────────
        start_bytes = 0
        upload_url = None
        session = load_session()

        if session and session.get('file_path') == file_path:
            start_bytes = get_server_progress(session['upload_url'])
            if start_bytes == -1:
                clear_session()
                return False, "Upload was already completed previously."
            upload_url = session['upload_url']

        # ── Get authenticated youtube service ──────────────────────────────────
        try:
            youtube = self.get_service(channel_profile)
        except Exception as e:
            return False, f"Auth failed: {e}"

        # ── Build media ────────────────────────────────────────────────────────
        media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True, chunksize=4 * 1024 * 1024)

        # ── New upload: POST handshake to get session URL before data moves ────
        if upload_url is None:
            body = {
                'snippet': {'title': title, 'description': description, 'categoryId': '22'},
                'status': {'privacyStatus': 'private'}
            }
            credentials = youtube._http.credentials
            if not credentials.valid:
                credentials.refresh(GoogleRequest())

            resp = _requests.post(
                'https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status',
                headers={
                    'Authorization': f'Bearer {credentials.token}',
                    'Content-Type': 'application/json; charset=UTF-8',
                    'X-Upload-Content-Type': mime_type,
                    'X-Upload-Content-Length': str(total_size),
                },
                data=_json.dumps(body).encode('utf-8')
            )
            if resp.status_code not in (200, 201):
                return False, f"Failed to initiate upload: HTTP {resp.status_code} — {resp.text}"
            upload_url = resp.headers['Location']
            save_session(upload_url)

        # ── Point request at session URL ───────────────────────────────────────
        request = youtube.videos().insert(part='snippet,status', body={}, media_body=media)
        request.resumable_uri = upload_url

        if start_bytes > 0:
            media._fd = open(file_path, 'rb')
            media._fd.seek(start_bytes)
            request.resumable_progress = start_bytes

        if progress_callback:
            progress_callback(start_bytes / total_size if total_size > 0 else 0.0)

        # ── Chunk loop ─────────────────────────────────────────────────────────
        response = None
        retry = 0
        max_retries = 8

        while response is None:
            try:
                status, response = request.next_chunk()
                if status:
                    sent = start_bytes + status.resumable_progress
                    if progress_callback:
                        progress_callback(min(sent / total_size, 1.0))

            except HttpError as e:
                if e.resp.status in (500, 502, 503, 504, 408):
                    retry += 1
                    if retry > max_retries:
                        return False, f"Upload failed after {max_retries} retries."
                    time.sleep(2 ** retry)
                else:
                    return False, f"HTTP error during upload: {e}"

            except (httplib2.HttpLib2Error, IOError) as e:
                return False, f"Upload interrupted — rerun to resume. ({e})"

        if progress_callback:
            progress_callback(1.0)

        clear_session()
        return True, response['id']

    def publish_now(self, video_id, channel_profile, publish_time_file=None):
        """
        Sets a video's privacy to public, optionally scheduled via publishtime.txt.
        File format: a single ISO 8601 line e.g. '2026-06-28T20:30:00Z'
        Returns (True, message) or (False, error).
        """
        from datetime import datetime
        from zoneinfo import ZoneInfo

        publish_at = None
        file_missing = False

        if publish_time_file and os.path.exists(publish_time_file):
            try:
                with open(publish_time_file, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                # Parse and normalize to UTC ISO 8601
                dt = datetime.fromisoformat(raw)
                if dt.tzinfo is None:
                    # Assume local time if no tz given
                    dt = dt.astimezone()
                publish_at = dt.astimezone(ZoneInfo("UTC")).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception as e:
                return False, f"Failed to parse publishtime.txt: {e}"
        else:
            file_missing = True

        try:
            youtube = self.get_service(channel_profile)

            if publish_at:
                status_body = {
                    "privacyStatus": "private",
                    "publishAt": publish_at
                }
                human_time = datetime.fromisoformat(publish_at).astimezone().strftime("%Y-%m-%d %I:%M %p %Z")
                message = f"✔ Scheduled to publish at {human_time}"
            else:
                status_body = {"privacyStatus": "public"}
                message = "✔ Published now (no publishtime.txt found)"

            youtube.videos().update(
                part="status",
                body={"id": video_id, "status": status_body}
            ).execute()

            return True, message

        except googleapiclient.errors.HttpError as e:
            return False, f"API error: {e.reason}"
        except Exception as e:
            return False, f"Publish failed: {e}"

    def upload_subtitle(self, video_id, srt_path, channel_profile, language="en"):
        """Uploads an SRT file as captions to a YouTube video."""
        try:
            from googleapiclient.http import MediaFileUpload
            youtube = self.get_service(channel_profile)
            media = MediaFileUpload(srt_path, mimetype="application/octet-stream", resumable=False)
            youtube.captions().insert(
                part="snippet",
                body={
                    "snippet": {
                        "videoId": video_id,
                        "language": language,
                        "name": "",
                        "isDraft": False
                    }
                },
                media_body=media
            ).execute()
            return True, f"✔ Subtitles uploaded from {os.path.basename(srt_path)}"
        except googleapiclient.errors.HttpError as e:
            return False, f"API error uploading subtitles: {e.reason}"
        except Exception as e:
            return False, f"Subtitle upload failed: {e}"

    def upload_thumbnail(self, video_id, image_path, channel_profile):
        """Uploads a thumbnail image to a YouTube video."""
        try:
            from googleapiclient.http import MediaFileUpload
            import mimetypes
            mime, _ = mimetypes.guess_type(image_path)
            if not mime:
                mime = "image/jpeg"
            youtube = self.get_service(channel_profile)
            media = MediaFileUpload(image_path, mimetype=mime, resumable=False)
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=media
            ).execute()
            return True, f"✔ Thumbnail uploaded: {os.path.basename(image_path)}"
        except googleapiclient.errors.HttpError as e:
            return False, f"API error uploading thumbnail: {e.reason}"
        except Exception as e:
            return False, f"Thumbnail upload failed: {e}"

    def fetch_video_by_id(self, video_id, channel_profile):
        """Fetches a single video's title by ID via the API. Used for autodetect probe."""
        try:
            youtube = self.get_service(channel_profile)
            response = youtube.videos().list(part="snippet", id=video_id).execute()
            if not response.get("items"):
                return False, None
            title = response["items"][0]["snippet"]["title"]
            return True, {"title": title, "id": video_id}
        except Exception as e:
            return False, str(e)

    def update_description(self, video_id, new_content, channel_profile, tags=None, title=None):
        """Replaces the description, optionally updates tags and title for a video."""
        try:
            youtube = self.get_service(channel_profile)
            request = youtube.videos().list(part="snippet", id=video_id)
            response = request.execute()

            if not response["items"]:
                return False, f"Video ID '{video_id}' not found."

            snippet = response["items"][0]["snippet"]
            snippet["description"] = new_content
            if tags is not None:
                snippet["tags"] = tags
            if title:
                snippet["title"] = title

            youtube.videos().update(
                part="snippet",
                body={"id": video_id, "snippet": snippet}
            ).execute()
            return True, "✔ YouTube title, description and tags updated successfully."
        except googleapiclient.errors.HttpError as e:
            return False, f"Google API Error: {e.reason}"
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
