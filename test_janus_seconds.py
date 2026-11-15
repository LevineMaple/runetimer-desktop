"""Exercise seconds-only HUD labels through localization and recognition."""
import unittest
from pathlib import Path

from PIL import Image

from pc_janus_reader import _GLYPHS, read_observation


def icon_with_seconds(text):
    path = Path(__file__).parent / "tests" / "fixtures" / "janus-icon.png"
    with Image.open(path) as fixture:
        icon = fixture.convert("RGB")
    glyphs = [_GLYPHS[digit][0].split("/") for digit in text]
    width = sum(len(glyph[0]) for glyph in glyphs) + len(glyphs) - 1
    left = (icon.width - width) // 2
    top = (icon.height - len(glyphs[0])) // 2
    for glyph in glyphs:
        for y, row in enumerate(glyph):
            for x, char in enumerate(row):
                if char == "#":
                    icon.putpixel((left + x, top + y), (255, 255, 0))
        left += len(glyph[0]) + 1
    return icon


class SecondsOnlyTests(unittest.TestCase):
    def test_seconds_only_labels(self):
        for seconds in (0, 5, 59, 60, 70, 80, 99, 100, 120, 214, 299, 300):
            with self.subTest(seconds=seconds):
                self.assertEqual(read_observation(icon_with_seconds(str(seconds))), (True, seconds))

    def test_out_of_range(self):
        for label in ("301", "999", "1000"):
            with self.subTest(label=label):
                self.assertEqual(read_observation(icon_with_seconds(label)), (True, None))


if __name__ == "__main__":
    unittest.main()
