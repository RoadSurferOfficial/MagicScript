#!/usr/bin/env python3
import sys
import os
from PySide6.QtWidgets import QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QComboBox
from PySide6.QtCore import Qt

from resolve_backend import ResolveAutomation
from youtube_backend import YouTubeAutomation

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
        self.btn_edl = QPushButton("Export Active Timeline to EDL")
        self.btn_edl.setFixedHeight(38)
        self.btn_edl.clicked.connect(self.handle_edl)
        layout.addWidget(self.btn_edl)

        self.btn_srt = QPushButton("Export Plain SRT Subtitles")
        self.btn_srt.setFixedHeight(38)
        self.btn_srt.clicked.connect(self.handle_srt)
        layout.addWidget(self.btn_srt)

        self.btn_chapters = QPushButton("Save Chapter File Local (~/Documents)")
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

        # HDR Status Check
        self.btn_hdr_check = QPushButton("Check HDR Status")
        self.btn_hdr_check.setFixedHeight(38)
        self.btn_hdr_check.setStyleSheet("background-color: #1a1a2e; color: #00ccff; font-weight: bold;")
        self.btn_hdr_check.clicked.connect(self.handle_hdr_check)
        yt_section.addWidget(self.btn_hdr_check)

        # Direct Push Button
        self.btn_push_yt = QPushButton("Publish Chapters Direct to YouTube Description")
        self.btn_push_yt.setFixedHeight(42)
        self.btn_push_yt.setStyleSheet("background-color: #cc0000; color: white; font-weight: bold;")
        self.btn_push_yt.clicked.connect(self.handle_youtube_push)
        yt_section.addWidget(self.btn_push_yt)

        layout.addLayout(yt_section)
        self.setLayout(layout)

    def handle_edl(self):
        success, info = self.resolve_api.export_edl()
        self.status.setText(f"EDL Output: {os.path.basename(info)}" if success else f"Fail: {info}")

    def handle_srt(self):
        success, info = self.resolve_api.export_srt_plaintext()
        self.status.setText(f"SRT Output: {os.path.basename(info)}" if success else f"Fail: {info}")

    def handle_local_chapters(self):
        text, name = self.resolve_api.generate_youtube_chapters_text()
        if not text:
            self.status.setText(f"Fail: {name}")
            return
        out_path = os.path.expanduser(f"~/Documents/{name}_YouTube_Chapters.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(text)
        self.status.setText(f"Saved: {name}_YouTube_Chapters.txt")

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

    def handle_youtube_push(self):
        current_profile = self.channel_dropdown.currentText()
        current_selection = self.video_dropdown.currentText()
        video_id = self.video_mapping.get(current_selection)

        if not video_id:
            self.status.setText("Error: Refresh and select a real video from the list.")
            return

        self.status.setText("Reading timeline markers...")
        chapters_text, name = self.resolve_api.generate_youtube_chapters_text()
        if not chapters_text:
            self.status.setText(f"Fail: {name}")
            return

        self.status.setText(f"Updating {current_profile} description...")
        success, message = self.youtube_api.update_description(video_id, chapters_text, current_profile)
        self.status.setText(message)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    panel = PipelineControlPanel()
    panel.show()
    sys.exit(app.exec())
