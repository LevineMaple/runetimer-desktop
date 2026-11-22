"""Regression coverage for the supplied Carcion village title and audio flow."""
import json
from pathlib import Path
import queue
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

from pc_map_audio import MapAudioMatcher
import test_pc
import pc_app


ASSETS = Path(__file__).parent / "assets" / "map_audio"


class CarcionMapAudioTests(unittest.TestCase):
    def setUp(self):
        with Image.open(ASSETS / "carcion-reference.png") as source:
            self.reference = source.convert("RGB")
        self.asset = json.loads((ASSETS / "carcion.json").read_text(encoding="utf-8"))
        self.matcher = MapAudioMatcher()

    def scene(self, offset=(46, 19), reference=None):
        image = Image.new("RGB", (540, 180), (38, 51, 63))
        image.paste(self.reference if reference is None else reference, offset)
        return image

    def test_original_title_and_translations(self):
        width, height = self.reference.size
        for offset in ((0, 0), (46, 19), (250, 95), (540-width, 180-height)):
            with self.subTest(offset=offset):
                self.assertTrue(self.matcher.match(self.scene(offset)))
                self.assertEqual(self.matcher.last_result["map_name"], "카르시온 / 이슈피라의 눈")

    def test_both_lines_required_and_region_alone_does_not_mute_hunting_map(self):
        for index in (0, 1):
            band = self.asset["bands"][index]
            modified = self.reference.copy()
            x, y, width = band["x"], band["y"], band["width"]
            ImageDraw.Draw(modified).rectangle(
                (x, y, x+width-1, y+len(band["rows"])-1), fill=(38, 51, 63))
            with self.subTest(missing_band=index):
                self.assertFalse(self.matcher.match(self.scene(reference=modified)))
        # Preserve the entire Carcion region line but replace the location line
        # with a different visible label. Region recognition alone cannot mute.
        band = self.asset["bands"][1]
        modified = self.reference.copy()
        draw = ImageDraw.Draw(modified)
        draw.rectangle((band["x"], band["y"], band["x"]+band["width"]-1,
                        band["y"]+len(band["rows"])-1), fill=(38, 51, 63))
        draw.text((band["x"]+2, band["y"]+2), "Hunting map", fill="white")
        self.assertFalse(self.matcher.match(self.scene(reference=modified)))

    def test_single_changed_location_character_is_rejected(self):
        modified = self.reference.copy()
        band = self.asset["bands"][1]
        rows = band["rows"]
        points = [(band["x"]+x, band["y"]+y) for y, row in enumerate(rows)
                  for x, bit in enumerate(row) if bit == "1"]
        left = min(x for x, _ in points)
        ImageDraw.Draw(modified).rectangle((left, band["y"], left+10,
                                           band["y"]+len(rows)-1), fill=(38, 51, 63))
        self.assertFalse(self.matcher.match(self.scene(reference=modified)))

    def test_original_boss_map_still_matches_and_empty_scene_unmutes(self):
        with Image.open(ASSETS / "reference.png") as original:
            frame = self.scene(reference=original.convert("RGB"))
        self.assertTrue(self.matcher.match(frame))
        self.assertEqual(self.matcher.last_result["map_name"], "도원경 / 사계가 머무는 누각")
        self.assertFalse(self.matcher.match(Image.new("RGB", (540, 180), (38, 51, 63))))
        self.assertFalse(self.matcher.last_result["matched"])

    def test_worker_mutes_village_and_resumes_after_location_changes(self):
        app = test_pc.RegressionTests().app_stub()
        app.pc_map_audio_muted = False
        app.rune_sound_enabled = True
        app.warning_sound_enabled = True
        app.root = Mock()
        app.root.winfo_viewable.return_value = False
        app.pc_diag = app.widget = None
        app.monitor_worker_running = False
        app.rune_region = (146, 195, 366, 374)
        app.pc_selected_window = dict(rect=(144, 184, 2064, 1264))
        app.pc_map_matcher = self.matcher
        app.worker_results = queue.Queue()
        frame = self.scene()
        app._grab_frame = Mock(return_value=frame)
        # Exercise the real worker/title decision and alert gates with a
        # controlled positive rune score, independent of an NPC's pixels.
        app._crop_minimap_view = Mock(return_value=Image.new("RGB", (100, 100)))
        app._score_rune = Mock(return_value=90)

        def immediate_thread(*, target, daemon):
            return Mock(start=target)

        with patch.object(pc_app.threading, "Thread", side_effect=immediate_thread):
            for expected in (True, True, False, False):
                if not expected:
                    band = self.asset["bands"][1]
                    ImageDraw.Draw(frame).rectangle(
                        (46+band["x"], 19+band["y"],
                         46+band["x"]+band["width"]-1,
                         19+band["y"]+len(band["rows"])-1), fill=(38, 51, 63))
                app.monitor_worker_running = False
                app._start_monitor_worker()
                _, result = app.worker_results.get_nowait()
                self.assertFalse(result["error"])
                self.assertEqual(result["map_audio_muted"], expected)
                app._apply_monitor_result(result)
                if expected:
                    app._play.assert_not_called()
                    self.assertIn("이슈피라의 눈", app.pc_status)
            app._play.assert_called_once_with("rune")
            self.assertFalse(app.pc_map_audio_muted)


if __name__ == "__main__":
    unittest.main()
