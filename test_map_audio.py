import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pc_map_audio import MapAudioMatcher


ASSET = Path(__file__).parent / "assets" / "map_audio"


class MapAudioMatcherTests(unittest.TestCase):
    def setUp(self):
        self.matcher = MapAudioMatcher()
        self.ref = Image.open(ASSET / "reference.png").convert("RGB")

    def scene(self, offset=(46, 19)):
        result = Image.new("RGB", (540, 180), (21, 32, 44))
        result.paste(self.ref, offset)
        return result

    def test_actual_reference_and_translations(self):
        for offset in [(46, 19), (0, 0), (250, 95), (420, 147)]:
            with self.subTest(offset=offset):
                self.assertTrue(self.matcher.match(self.scene(offset)))

    def test_actual_capture_if_available(self):
        sample = Path(__file__).parent / 'tests/fixtures/four_seasons_capture.png'
        self.assertTrue(self.matcher.match(Image.open(sample)))

    def test_dark_background_change(self):
        # Keep the actual captured text pixels; replace only low-luminance
        # background pixels. This tests compositing, not a newly rendered font.
        ref = self.ref.copy()
        ref.putdata([p if min(p) >= 165 and max(p) - min(p) <= 35 else (65, 55, 70)
                     for p in ref.getdata()])
        frame = self.scene()
        frame.paste(ref, (46, 19))
        self.assertTrue(self.matcher.match(frame))

    def test_blank_and_noise_negative(self):
        for color in ["black", "white", "purple", (150, 150, 150)]:
            self.assertFalse(self.matcher.match(Image.new("RGB", (540, 180), color)))
        import random
        random.seed(771)
        noise = Image.new("RGB", (540, 180))
        noise.putdata([(255, 255, 255) if random.random() < .35 else (20, 20, 20)
                       for _ in range(540 * 180)])
        self.assertFalse(self.matcher.match(noise))

    def test_missing_region_or_changed_map_character_negative(self):
        for box in [(46, 19, 84, 32), (133, 39, 143, 48), (81, 39, 90, 48)]:
            frame = self.scene()
            ImageDraw.Draw(frame).rectangle(box, fill="black")
            self.assertFalse(self.matcher.match(frame))

    def test_adjacent_prefix_and_suffix_rejected(self):
        for x in [47, 144, 151, 161]:
            frame = self.scene()
            ImageDraw.Draw(frame).line((x, 39, x, 48), fill="white", width=1)
            self.assertFalse(self.matcher.match(frame))

    def test_scaled_or_invalid_reference_fail_open(self):
        self.assertFalse(self.matcher.match(self.scene().resize((1080, 360), Image.Resampling.NEAREST)))
        self.assertFalse(self.matcher.match(Image.new("RGB", (90, 30))))
        self.assertFalse(MapAudioMatcher(ASSET / "missing.json").match(self.scene()))


if __name__ == "__main__":
    unittest.main()
