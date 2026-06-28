#!/usr/bin/env python3
import sys
import os
import re
from PySide6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
                                QPushButton, QLabel, QComboBox, QProgressBar,
                                QFileDialog, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal

from resolve_backend import ResolveAutomation
from youtube_backend import YouTubeAutomation

class UploadWorker(QThread):
    progress = Signal(float)
    finished = Signal(bool, str)

    def __init__(self, youtube_api, file_path, title, description, channel_profile):
        super().__init__()
        self.youtube_api = youtube_api
        self.file_path = file_path
        self.title = title
        self.description = description
        self.channel_profile = channel_profile

    def run(self):
        success, result = self.youtube_api.resumable_upload(
            file_path=self.file_path,
            title=self.title,
            description=self.description,
            channel_profile=self.channel_profile,
            progress_callback=lambda p: self.progress.emit(p)
        )
        self.finished.emit(success, result)


class PipelineControlPanel(QWidget):
    def __init__(self):
        super().__init__()
        self.resolve_api = ResolveAutomation()
        self.youtube_api = YouTubeAutomation()
        self.video_mapping = {}
        self.init_ui()
        # Populate dropdown from cache on startup without hitting the API
        self._load_videos_from_cache(self.channel_dropdown.currentText())

    def init_ui(self):
        self.setWindowTitle("Studio Production Pipeline")
        self.resize(460, 520)
        layout = QVBoxLayout()

        # Workspace Connectivity Tracker
        proj_title = self.resolve_api.get_current_project_name()
        self.status = QLabel(f"Project Link: {proj_title}")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status.setStyleSheet("font-weight: bold; font-size: 13px; color: #666; margin-bottom: 8px;")
        layout.addWidget(self.status)

        # Standard Pipeline Command Triggers
        self.btn_color_qc = QPushButton("Color to Quality Control")
        self.btn_color_qc.setFixedHeight(38)
        self.btn_color_qc.setStyleSheet("background-color: #2e1a2e; color: #cc88ff; font-weight: bold;")
        self.btn_color_qc.clicked.connect(self.handle_color_qc)
        layout.addWidget(self.btn_color_qc)

        self.btn_edl = QPushButton("Export Active Timeline to EDL")
        self.btn_edl.setFixedHeight(38)
        self.btn_edl.clicked.connect(self.handle_edl)
        layout.addWidget(self.btn_edl)

        self.btn_thumbnail = QPushButton("Export Frame as Thumbnail")
        self.btn_thumbnail.setFixedHeight(38)
        self.btn_thumbnail.clicked.connect(self.handle_thumbnail)
        layout.addWidget(self.btn_thumbnail)

        self.btn_srt = QPushButton("Export Plain SRT Subtitles")
        self.btn_srt.setFixedHeight(38)
        self.btn_srt.clicked.connect(self.handle_srt)
        layout.addWidget(self.btn_srt)

        self.btn_chapters = QPushButton("Generate YouTube Helper Files")
        self.btn_chapters.setFixedHeight(38)
        self.btn_chapters.clicked.connect(self.handle_local_chapters)
        layout.addWidget(self.btn_chapters)

        # YouTube Integration Section
        yt_section = QVBoxLayout()
        yt_label = QLabel("YouTube Multi-Channel Options:")
        yt_label.setStyleSheet("font-weight: bold; margin-top: 15px; color: #cc0000;")
        yt_section.addWidget(yt_label)

        # NEW: Channel Switcher Dropdown Profile Configuration
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Active Channel Profile:"))
        self.channel_dropdown = QComboBox()
        # Add your channel nicknames here to easily switch between profiles
        self.channel_dropdown.addItems(["RoadSurfer", "Chaotic Good", "Chaotic Neutral", "Chaotic Evil"])
        self.channel_dropdown.currentIndexChanged.connect(self.clear_video_dropdown_on_switch)
        channel_layout.addWidget(self.channel_dropdown, stretch=2)
        self.btn_autodetect = QPushButton("Autodetect")
        self.btn_autodetect.setFixedWidth(90)
        self.btn_autodetect.clicked.connect(self.handle_autodetect)
        channel_layout.addWidget(self.btn_autodetect)
        yt_section.addLayout(channel_layout)

        # Video Picker Dropdown Row
        picker_layout = QHBoxLayout()
        picker_layout.addWidget(QLabel("Select Video:"))
        self.video_dropdown = QComboBox()
        picker_layout.addWidget(self.video_dropdown, stretch=2)

        self.btn_refresh_yt = QPushButton("Refresh List")
        self.btn_refresh_yt.clicked.connect(self.populate_video_dropdown)
        picker_layout.addWidget(self.btn_refresh_yt)
        yt_section.addLayout(picker_layout)

        # Upload Button
        self.btn_upload = QPushButton("⬆  Upload Video to YouTube")
        self.btn_upload.setFixedHeight(38)
        self.btn_upload.setStyleSheet("background-color: #1a2e1a; color: #00ff88; font-weight: bold;")
        self.btn_upload.clicked.connect(self.handle_upload)
        yt_section.addWidget(self.btn_upload)

        # Upload Progress Bar
        self.upload_progress = QProgressBar()
        self.upload_progress.setRange(0, 100)
        self.upload_progress.setValue(0)
        self.upload_progress.setFixedHeight(16)
        self.upload_progress.setTextVisible(True)
        self.upload_progress.setStyleSheet("""
            QProgressBar { border: 1px solid #333; border-radius: 3px; background: #111; color: white; font-size: 10px; }
            QProgressBar::chunk { background: #00ff88; border-radius: 2px; }
        """)
        self.upload_progress.setVisible(False)
        yt_section.addWidget(self.upload_progress)

        # HDR Status Check
        self.btn_hdr_check = QPushButton("Check HDR Status")
        self.btn_hdr_check.setFixedHeight(38)
        self.btn_hdr_check.setStyleSheet("background-color: #1a1a2e; color: #00ccff; font-weight: bold;")
        self.btn_hdr_check.clicked.connect(self.handle_hdr_check)
        yt_section.addWidget(self.btn_hdr_check)

        # Direct Push Button
        self.btn_push_yt = QPushButton("Publish YouTube Helper Files")
        self.btn_push_yt.setFixedHeight(42)
        self.btn_push_yt.setStyleSheet("background-color: #cc0000; color: white; font-weight: bold;")
        self.btn_push_yt.clicked.connect(self.handle_youtube_push)
        yt_section.addWidget(self.btn_push_yt)

        # Publish Subtitles
        self.btn_publish_srt = QPushButton("Publish Subtitles")
        self.btn_publish_srt.setFixedHeight(38)
        self.btn_publish_srt.setStyleSheet("background-color: #1a1a1a; color: #aaaaff; font-weight: bold;")
        self.btn_publish_srt.clicked.connect(self.handle_publish_srt)
        yt_section.addWidget(self.btn_publish_srt)

        # Upload Thumbnail
        self.btn_upload_thumb = QPushButton("Upload Thumbnail")
        self.btn_upload_thumb.setFixedHeight(38)
        self.btn_upload_thumb.setStyleSheet("background-color: #1a1a1a; color: #ffaa44; font-weight: bold;")
        self.btn_upload_thumb.clicked.connect(self.handle_upload_thumbnail)
        yt_section.addWidget(self.btn_upload_thumb)

        # Publish Now Button
        self.btn_publish_now = QPushButton("🚀  Publish Now")
        self.btn_publish_now.setFixedHeight(42)
        self.btn_publish_now.setStyleSheet("background-color: #7700cc; color: white; font-weight: bold; font-size: 13px;")
        self.btn_publish_now.clicked.connect(self.handle_publish_now)
        yt_section.addWidget(self.btn_publish_now)

        layout.addLayout(yt_section)
        self.setLayout(layout)

    def handle_thumbnail(self):
        success, result = self.resolve_api.export_thumbnail()
        if success:
            self.status.setText(f"Thumbnail saved: {os.path.basename(result)}")
        else:
            self.status.setText(f"Thumbnail failed: {result}")

    def handle_color_qc(self):
        success, message = self.resolve_api.color_to_qc()
        self.status.setText(message)

    def handle_publish_now(self):
        current_selection = self.video_dropdown.currentText()
        video_id = self.video_mapping.get(current_selection)
        if not video_id:
            self.status.setText("Error: Refresh and select a video first.")
            return

        publish_file = os.path.join(self._youtube_dir(), "publishtime.txt")
        if not os.path.exists(publish_file):
            reply = QMessageBox.question(
                self,
                "publishtime.txt Missing",
                "publishtime.txt not found — this will publish the video PUBLIC immediately.\n\nContinue?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                self.status.setText("Publish cancelled.")
                return
            publish_file = None

        current_profile = self.channel_dropdown.currentText()
        self.status.setText("Publishing...")
        success, message = self.youtube_api.publish_now(video_id, current_profile, publish_file)
        self.status.setText(message)

    def handle_edl(self):
        success, info = self.resolve_api.export_edl()
        self.status.setText(f"EDL Output: {os.path.basename(info)}" if success else f"Fail: {info}")

    def handle_srt(self):
        success, info = self.resolve_api.export_srt_plaintext()
        self.status.setText(f"SRT Output: {os.path.basename(info)}" if success else f"Fail: {info}")

    def handle_local_chapters(self):
        from datetime import datetime, timedelta
        youtube_dir = self._youtube_dir()
        os.makedirs(youtube_dir, exist_ok=True)

        # Create stub helper files if missing
        for fname in ["DescriptionHead.txt", "DescriptionFoot.txt", "Tags.txt"]:
            fpath = os.path.join(youtube_dir, fname)
            if not os.path.exists(fpath):
                open(fpath, "w", encoding="utf-8").close()

        # Write YouTubeID.txt from selected video if not already present
        video_id = self._get_selected_video_id()
        if video_id:
            self._write_youtube_id_file(video_id, self.channel_dropdown.currentText(), overwrite=False)

        # Always write publishtime.txt with 3-day forward offset
        publish_time = datetime.now().astimezone() + timedelta(days=3)
        publish_path = os.path.join(youtube_dir, "publishtime.txt")
        with open(publish_path, "w", encoding="utf-8") as f:
            f.write(publish_time.strftime("%Y-%m-%dT%H:%M:%S%z") + "\n")

        # Only update chapters file if Resolve is responsive
        text, name = self.resolve_api.generate_youtube_chapters_text()
        if not text:
            self.status.setText("Resolve unresponsive, Chapters not updated/created.")
            return

        chapters_path = os.path.join(youtube_dir, f"{name}_YouTube_Chapters.txt")
        with open(chapters_path, "w", encoding="utf-8") as f:
            f.write(text)
        self.status.setText(f"YouTube helper files ready — {name}_YouTube_Chapters.txt updated.")


    def handle_youtube_push(self):
        current_profile = self.channel_dropdown.currentText()
        current_selection = self.video_dropdown.currentText()
        video_id = self.video_mapping.get(current_selection)

        if not video_id:
            self.status.setText("Error: Refresh and select a real video from the list.")
            return

        youtube_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "YouTube")

        # Find chapters file — pick the most recently modified _YouTube_Chapters.txt
        chapter_files = [
            f for f in os.listdir(youtube_dir)
            if f.endswith("_YouTube_Chapters.txt")
        ] if os.path.exists(youtube_dir) else []

        if not chapter_files:
            self.status.setText("No _YouTube_Chapters.txt found — run Generate YouTube Helper Files first.")
            return

        chapter_files.sort(key=lambda f: os.path.getmtime(os.path.join(youtube_dir, f)), reverse=True)
        chapters_path = os.path.join(youtube_dir, chapter_files[0])

        def read_file(fname):
            path = os.path.join(youtube_dir, fname)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            return ""

        head = read_file("DescriptionHead.txt")
        chapters = open(chapters_path, "r", encoding="utf-8").read().strip()
        foot = read_file("DescriptionFoot.txt")
        tags_raw = read_file("Tags.txt")

        # Concatenate description parts, skipping empty sections
        parts = [p for p in [head, chapters, foot] if p]
        description = "\n\n".join(parts)

        # Parse tags — comma or newline separated
        tags = [t.strip() for t in re.split(r"[,\n]", tags_raw) if t.strip()] if tags_raw else []

        self.status.setText(f"Updating {current_profile} description and tags...")
        success, message = self.youtube_api.update_description(video_id, description, current_profile, tags)
        self.status.setText(message)

    def clear_video_dropdown_on_switch(self):
        """On profile switch, load from disk cache if available, otherwise show placeholder"""
        self.video_dropdown.clear()
        self.video_mapping.clear()
        current_profile = self.channel_dropdown.currentText()
        self._load_videos_from_cache(current_profile)

    def _load_videos_from_cache(self, profile):
        """Populate dropdown from disk cache without hitting the API"""
        success, data = self.youtube_api.fetch_recent_videos(profile, force_refresh=False)
        if success:
            for video in data:
                display_text = f"{video['title']} [{video['id']}]"
                self.video_dropdown.addItem(display_text)
                self.video_mapping[display_text] = video["id"]
            self.status.setText(f"Loaded {profile} from cache.")
        else:
            self.video_dropdown.addItem("Click Refresh to load videos...")
            self.status.setText(f"Switched profile to: {profile}")

    def populate_video_dropdown(self):
        """Fetches video list specific to the chosen active profile"""
        current_profile = self.channel_dropdown.currentText()
        self.status.setText(f"Connecting to {current_profile}...")

        success, data = self.youtube_api.fetch_recent_videos(current_profile, force_refresh=True)

        if not success:
            self.status.setText(f"Error: {data}")
            return

        self.video_dropdown.clear()
        self.video_mapping.clear()

        for video in data:
            display_text = f"{video['title']} [{video['id']}]"
            self.video_dropdown.addItem(display_text)
            self.video_mapping[display_text] = video["id"]

        self.status.setText(f"Loaded {current_profile} uploads successfully!")

    def handle_upload(self):
        # Check for output_joined.mkv in script directory first
        default_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output_joined.mkv")
        if os.path.exists(default_path):
            reply = QMessageBox.question(
                self,
                "Found output_joined.mkv",
                f"Found output_joined.mkv in script directory.\n\nUpload this file?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                file_path = default_path
            else:
                file_path, _ = QFileDialog.getOpenFileName(
                    self, "Select Video File", os.path.expanduser("~"),
                    "Video Files (*.mp4 *.mkv *.mov *.avi *.webm);;All Files (*)"
                )
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                self, "Select Video File", os.path.expanduser("~"),
                "Video Files (*.mp4 *.mkv *.mov *.avi *.webm);;All Files (*)"
            )

        if not file_path:
            return

        title = os.path.splitext(os.path.basename(file_path))[0]
        channel_profile = self.channel_dropdown.currentText()

        self.btn_upload.setEnabled(False)
        self.upload_progress.setValue(0)
        self.upload_progress.setVisible(True)
        self.status.setText(f"Starting upload to {channel_profile}...")

        self._upload_worker = UploadWorker(
            youtube_api=self.youtube_api,
            file_path=file_path,
            title=title,
            description="",
            channel_profile=channel_profile
        )
        self._upload_worker.progress.connect(self._on_upload_progress)
        self._upload_worker.finished.connect(self._on_upload_finished)
        self._upload_worker.start()

    def _on_upload_progress(self, percent):
        self.upload_progress.setValue(int(percent * 100))
        self.status.setText(f"Uploading... {int(percent * 100)}%")

    def _on_upload_finished(self, success, result):
        self.btn_upload.setEnabled(True)
        self.upload_progress.setVisible(False)
        if success:
            self.status.setText(f"✔ Upload complete! Video ID: {result}")
            # Write YouTubeID.txt on successful upload
            self._write_youtube_id_file(result, self.channel_dropdown.currentText())
        else:
            self.status.setText(f"✖ Upload failed: {result}")

    def _youtube_dir(self):
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), "YouTube")

    def _youtube_id_path(self):
        return os.path.join(self._youtube_dir(), "YouTubeID.txt")

    def _write_youtube_id_file(self, video_id, channel_profile, overwrite=True):
        youtube_dir = self._youtube_dir()
        os.makedirs(youtube_dir, exist_ok=True)
        path = self._youtube_id_path()
        if not overwrite and os.path.exists(path):
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"{video_id}\n{channel_profile}\n")

    def _read_youtube_id_file(self):
        """Returns (video_id, channel_profile) or (None, None)."""
        path = self._youtube_id_path()
        if not os.path.exists(path):
            return None, None
        try:
            lines = open(path, encoding="utf-8").read().strip().splitlines()
            if len(lines) >= 2:
                return lines[0].strip(), lines[1].strip()
        except Exception:
            pass
        return None, None

    def _get_selected_video_id(self):
        return self.video_mapping.get(self.video_dropdown.currentText())

    def handle_publish_srt(self):
        video_id = self._get_selected_video_id()
        if not video_id:
            self.status.setText("Error: Select a video first.")
            return
        youtube_dir = self._youtube_dir()
        # Find most recently modified .srt in YouTube folder
        srt_files = sorted(
            [f for f in os.listdir(youtube_dir) if f.endswith(".srt")],
            key=lambda f: os.path.getmtime(os.path.join(youtube_dir, f)),
            reverse=True
        ) if os.path.exists(youtube_dir) else []
        if not srt_files:
            self.status.setText("No .srt file found in YouTube folder — export subtitles first.")
            return
        srt_path = os.path.join(youtube_dir, srt_files[0])
        self.status.setText(f"Uploading subtitles: {srt_files[0]}...")
        success, message = self.youtube_api.upload_subtitle(
            video_id, srt_path, self.channel_dropdown.currentText()
        )
        self.status.setText(message)

    def handle_upload_thumbnail(self):
        video_id = self._get_selected_video_id()
        if not video_id:
            self.status.setText("Error: Select a video first.")
            return
        thumb_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Thumbnails")
        # Find most recently modified image in Thumbnails folder
        img_files = sorted(
            [f for f in os.listdir(thumb_dir) if f.lower().endswith((".jpg", ".jpeg", ".png"))],
            key=lambda f: os.path.getmtime(os.path.join(thumb_dir, f)),
            reverse=True
        ) if os.path.exists(thumb_dir) else []
        if not img_files:
            self.status.setText("No thumbnail found in Thumbnails folder — export a frame first.")
            return
        img_path = os.path.join(thumb_dir, img_files[0])
        self.status.setText(f"Uploading thumbnail: {img_files[0]}...")
        success, message = self.youtube_api.upload_thumbnail(
            video_id, img_path, self.channel_dropdown.currentText()
        )
        self.status.setText(message)

    def handle_autodetect(self):
        """Match YouTubeID.txt against current video list; probe API if not found."""
        video_id, channel_profile = self._read_youtube_id_file()
        if not video_id:
            self.status.setText("No YouTubeID.txt found — upload a video or generate helper files first.")
            return

        # Search current dropdown
        for display_text, vid in self.video_mapping.items():
            if vid == video_id:
                self.video_dropdown.setCurrentText(display_text)
                self.status.setText(f"✔ Autodetect matched: {display_text}")
                return

        # Not in list — ask to probe
        reply = QMessageBox.question(
            self,
            "Video Not in List",
            f"Video ID '{video_id}' not found in current list.\n\nProbe YouTube API for this video?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            self.status.setText("Autodetect cancelled.")
            return

        self.status.setText(f"Probing API for {video_id}...")
        current_profile = self.channel_dropdown.currentText()
        success, video = self.youtube_api.fetch_video_by_id(video_id, current_profile)
        if not success or not video:
            self.status.setText(f"✖ Video ID '{video_id}' not found on {current_profile}.")
            return

        # Add to dropdown and select it
        display_text = f"{video['title']} [{video['id']}]"
        self.video_dropdown.addItem(display_text)
        self.video_mapping[display_text] = video_id
        self.video_dropdown.setCurrentText(display_text)
        self.status.setText(f"✔ Found and added: {display_text}")

    def handle_hdr_check(self):
        current_selection = self.video_dropdown.currentText()
        video_id = self.video_mapping.get(current_selection)

        if not video_id:
            self.status.setText("Error: Refresh and select a video first.")
            return

        self.status.setText(f"Checking HDR status for {video_id}...")
        result = self.youtube_api.check_hdr_status(video_id)

        if result["status"] == "error":
            self.status.setText(f"HDR check error: {result['message']}")
        elif result["hdr_active"]:
            self.status.setText(f"✔ HDR confirmed: {result['profile']} — safe to publish.")
        else:
            self.status.setText("✖ No HDR streams found yet — still processing or SDR source.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    panel = PipelineControlPanel()
    panel.show()
    sys.exit(app.exec())
