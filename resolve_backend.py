#!/usr/bin/env python3
import sys
import os
import re

# Explicitly pull Resolve's scripting library path on Linux
sys.path.append("/opt/resolve/Developer/Scripting/Modules")
try:
    import DaVinciResolveScript as bmd
except ImportError:
    bmd = None

class ResolveAutomation:
    def __init__(self):
        self.resolve = bmd.scriptapp("Resolve") if bmd else None

    def is_connected(self):
        return self.resolve is not None

    def get_current_project_name(self):
        if not self.is_connected(): return "Disconnected"
        pm = self.resolve.GetProjectManager()
        proj = pm.GetCurrentProject()
        return proj.GetName() if proj else "No Active Project"

    def format_timecode(self, frames, fps, for_youtube=False):
        total_seconds = int(frames // fps)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60

        if for_youtube:
            return f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"

        milliseconds = int(((frames / fps) % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def export_edl(self):
        if not self.is_connected(): return False, "Resolve not running."
        proj = self.resolve.GetProjectManager().GetCurrentProject()
        timeline = proj.GetCurrentTimeline() if proj else None
        if not timeline: return False, "No active timeline."

        out_path = os.path.expanduser(f"~/Documents/{timeline.GetName()}.edl")
        success = timeline.Export(out_path, self.resolve.EXPORT_EDL, self.resolve.EXPORT_CDL)
        return success, out_path if success else "Export sequence rejection."

    def export_srt_plaintext(self):
        if not self.is_connected(): return False, "Resolve not running."
        proj = self.resolve.GetProjectManager().GetCurrentProject()
        timeline = proj.GetCurrentTimeline() if proj else None
        if not timeline: return False, "No active timeline."

        fps = float(timeline.GetSetting("timelineFrameRate"))
        sub_items = timeline.GetItemListInTrack("subtitle", 1)
        if not sub_items: return False, "No items found on Subtitle Track 1."

        export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "YouTube")
        os.makedirs(export_dir, exist_ok=True)
        out_path = os.path.join(export_dir, f"{timeline.GetName()}.srt")
        try:
            with open(out_path, "w", encoding="utf-8") as f:
                for idx, item in enumerate(sub_items, start=1):
                    start_tc = self.format_timecode(item.GetStart(), fps)
                    end_tc = self.format_timecode(item.GetEnd(), fps)
                    clean_text = re.sub(r'<[^>]*>', '', item.GetName())
                    f.write(f"{idx}\n{start_tc} --> {end_tc}\n{clean_text}\n\n")
            return True, out_path
        except Exception as e:
            return False, str(e)

    def color_to_qc(self):
        """Renames timeline clips based on timeline item clip color using the QC suffix system.
        All clips get numbered. Only colored clips get a suffix."""
        if not self.is_connected():
            return False, "Resolve not running."
        proj = self.resolve.GetProjectManager().GetCurrentProject()
        if not proj:
            return False, "No open project."
        timeline = proj.GetCurrentTimeline()
        if not timeline:
            return False, "No active timeline."

        COLOR_MAP = {
            "Blue":   "HQ",
            "Orange": "LQ",
            "Purple": "TH",
            "Lime":   "HM",
            "Tan":    "FG",
            "Yellow": "PR",
        }
        STRUCTURE_REGEX = re.compile(r"^\d{3}_(.+?)_\d{3}(?:_(?:HQ|LQ|TH|HM|FG|PR))?$")

        all_items = []
        track_count = timeline.GetTrackCount("video")
        for track_index in range(1, track_count + 1):
            track_items = timeline.GetItemListInTrack("video", track_index)
            if not track_items:
                continue
            for item in track_items:
                all_items.append((item.GetStart(), item))

        all_items.sort(key=lambda x: x[0])

        timeline_location_marker = 0
        current_unique_id = None
        split_counter = 1
        renamed = 0

        for start_frame, item in all_items:
            clip_color = item.GetClipColor()
            suffix = COLOR_MAP.get(clip_color)  # None if no color assigned

            mpi = item.GetMediaPoolItem()
            if mpi:
                try:
                    unique_id = mpi.GetUniqueId()
                except Exception:
                    unique_id = mpi.GetClipProperty("File Path")
            else:
                unique_id = item.GetName()

            clip_name = item.GetName()
            match = STRUCTURE_REGEX.match(clip_name)
            if match:
                base_name = match.group(1)
            else:
                base_name = clip_name
                if "." in base_name:
                    base_name = base_name.rsplit(".", 1)[0]

            if unique_id != current_unique_id:
                timeline_location_marker += 1
                split_counter = 1
                current_unique_id = unique_id
            else:
                split_counter += 1

            if suffix:
                new_name = f"{timeline_location_marker:03d}_{base_name}_{split_counter:03d}_{suffix}"
            else:
                new_name = f"{timeline_location_marker:03d}_{base_name}_{split_counter:03d}"

            item.SetName(new_name)
            renamed += 1

        return True, f"QC rename complete — {renamed} clip(s) updated."

    def export_thumbnail(self):
        """
        Exports the current timeline frame as a JPEG using project.ExportCurrentFrameAsStill().
        Saves to ~/Desktop/Thumbnails/thumbnailN.jpg, auto-incrementing index.
        """
        if not self.is_connected():
            return False, "Resolve not running."
        proj = self.resolve.GetProjectManager().GetCurrentProject()
        if not proj:
            return False, "No open project."
        timeline = proj.GetCurrentTimeline()
        if not timeline:
            return False, "No active timeline."

        export_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "Thumbnails")
        os.makedirs(export_dir, exist_ok=True)

        pattern = re.compile(r"^thumbnail(\d+)\.")
        highest = 0
        for fname in os.listdir(export_dir):
            m = pattern.match(fname)
            if m:
                highest = max(highest, int(m.group(1)))
        target_path = os.path.join(export_dir, f"thumbnail{highest + 1}.jpg")

        success = proj.ExportCurrentFrameAsStill(target_path)
        if not success:
            return False, "ExportCurrentFrameAsStill() failed — ensure the timeline is active and a frame is visible."

        return True, target_path

    def generate_youtube_chapters_text(self):
        """Processes timeline markers directly and returns the text instead of writing a file"""
        if not self.is_connected(): return None, "Resolve not running."
        proj = self.resolve.GetProjectManager().GetCurrentProject()
        timeline = proj.GetCurrentTimeline() if proj else None
        if not timeline: return None, "No active timeline."

        fps = float(timeline.GetSetting("timelineFrameRate"))
        start_offset = int(timeline.GetStartFrame())
        markers = timeline.GetMarkers()
        if not markers: return None, "No markers found on active timeline."

        has_zero_start = False
        lines = []
        for f_id in sorted(markers.keys()):
            rel_frame = f_id - start_offset
            timestamp = self.format_timecode(max(0, rel_frame), fps, for_youtube=True)
            if timestamp in ["00:00", "00:00:00"]: has_zero_start = True

            title = markers[f_id].get("name") or markers[f_id].get("note") or f"Chapter {f_id}"
            lines.append(f"{timestamp} {title}")

        if not has_zero_start:
            lines.insert(0, "00:00 Intro")

        return "\n".join(lines), timeline.GetName()
