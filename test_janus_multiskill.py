"""Replay wide skill-bar selections with real Janus samples at different positions."""
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pc_janus_reader import read_observation


FIXTURES = Path(__file__).parent / "tests" / "fixtures"


def icon(name):
    with Image.open(FIXTURES / name) as image:
        return image.convert("RGB")


def other_skill():
    # Keep the actual yellow 3:34 glyphs over a different purple skill.
    original = icon("janus-3m34.png")
    other = Image.new("RGB", original.size, "#333333")
    draw = ImageDraw.Draw(other)
    draw.rounded_rectangle((3, 3, 30, 30), radius=4, fill="#692fc0")
    draw.line((8, 27, 25, 6), fill="#ddddee", width=3)
    for y in range(original.height):
        for x in range(original.width):
            r, g, b = original.getpixel((x, y))
            if min(r, g) >= 150 and min(r, g) - b > 75:
                other.putpixel((x, y), (r, g, b))
    return other


class MultiSkillReaderTests(unittest.TestCase):
    def test_reordered_across_rows_and_ends(self):
        decoy = other_skill()
        janus = icon("janus-3m34.png")
        for row, col in ((0, 0), (0, 16), (1, 6), (1, 25)):
            with self.subTest(row=row, col=col):
                bar = Image.new("RGB", (936, 79), "#23282e")
                for y in range(2):
                    for x in range(26):
                        bar.paste(janus if (y, x) == (row, col) else decoy,
                                  (2 + x * 36, 3 + y * 39))
                self.assertEqual(read_observation(bar), (True, 214))

    def test_empty_digits_do_not_borrow_adjacent_cooldown(self):
        decoy = other_skill()
        bar = Image.new("RGB", (102, 34))
        bar.paste(decoy, (0, 0))
        bar.paste(icon("janus-icon.png"), (34, 0))
        bar.paste(decoy, (68, 0))
        self.assertEqual(read_observation(bar), (True, None))
        bar.paste(decoy, (34, 0))
        self.assertEqual(read_observation(bar), (False, None))

    def test_full_width_selection_at_supported_limit(self):
        bar = Image.new("RGB", (2048, 512), "#202429")
        bar.paste(other_skill(), (6, 5))
        bar.paste(icon("janus-3m34.png"), (2014, 478))
        self.assertEqual(read_observation(bar), (True, 214))

    def test_scaled_icon_with_skill_and_game_background(self):
        with Image.open(FIXTURES / "four_seasons_capture.png") as background:
            bar = background.convert("RGB")
        bar.paste(other_skill(), (50, 24))
        bar.paste(icon("janus-3m34.png").resize((51, 51), Image.Resampling.BILINEAR),
                  (127, 81))
        self.assertEqual(read_observation(bar), (True, 214))


if __name__ == "__main__":
    unittest.main()
