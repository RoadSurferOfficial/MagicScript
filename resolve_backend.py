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
        
        milliseconds = int(( (frames / fps) % 1 ) * 1000)
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
        
        out_path = os.path.expanduser(f"~/Documents/{timeline.GetName()}_Clean.srt")
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
