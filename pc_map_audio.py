"""Conservative, local visual allowlist for one map's rune-audio suppression.

This is an exact glyph matcher, not OCR or a general map classifier. Unknown
fonts, scaling, obscured titles, or missing assets fail open (audio allowed).
"""
import json
import sys
from pathlib import Path


class MapAudioMatcher:
    def __init__(self, asset_path=None):
        self.last_result = {"matched": False, "reason": "not_checked"}
        self._asset = None
        try:
            base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
            path = Path(asset_path) if asset_path else base / "assets" / "map_audio" / "four_seasons.json"
            asset = json.loads(path.read_text(encoding="utf-8"))
            if asset["version"] != 1 or asset["width"] != 120 or asset["height"] != 33:
                raise ValueError("Unsupported map reference")
            self._bands = []
            for band in asset["bands"]:
                width = band["width"]
                rows = band["rows"]
                if not rows or any(len(row) != width or set(row) - {"0", "1"} for row in rows):
                    raise ValueError("Invalid glyph reference")
                self._bands.append((band["x"], band["y"], width,
                                    [sum((ch == "1") << i for i, ch in enumerate(row)) for row in rows]))
            if len(self._bands) != 2:
                raise ValueError("Both title bands are required")
            self._asset = asset
        except (OSError, ValueError, KeyError, TypeError):
            self.last_result = {"matched": False, "reason": "reference_unavailable"}

    def match(self, frame):
        """Return True only when both reference text lines are visibly present.

        frame is an RGB-compatible PIL image of the game client's top-left
        area. Translation is supported. Never resize the screenshot here.
        """
        self.last_result = {"matched": False, "reason": "no_exact_title"}
        if self._asset is None:
            self.last_result["reason"] = "reference_unavailable"
            return False
        try:
            width, height = frame.size
            tw, th = self._asset["width"], self._asset["height"]
            if width < tw or height < th:
                return False
            rgb = frame.convert("RGB")
            pixels = iter(rgb.getdata())
            threshold = self._asset["threshold"]
            spread = self._asset["max_color_spread"]
            packed = []
            for _ in range(height):
                row = 0
                for x in range(width):
                    r, g, b = next(pixels)
                    low = min(r, g, b)
                    if low >= threshold and max(r, g, b) - low <= spread:
                        row |= 1 << x
                packed.append(row)

            # Fourteen required strokes are tested at every horizontal offset
            # in parallel using integer bit operations. The complete two-line
            # comparison, including empty margins, decides the final match.
            anchor_y = 20
            title_row = self._bands[1][3][2]
            anchors = [i for i in range(tw) if title_row & (1 << i)][:14]
            valid_origins = (1 << (width - tw + 1)) - 1
            for y in range(height - th + 1):
                candidates = valid_origins
                for x in anchors:
                    candidates &= packed[y + anchor_y] >> x
                    if not candidates:
                        break
                while candidates:
                    bit = candidates & -candidates
                    candidates ^= bit
                    x = bit.bit_length() - 1
                    errors = []
                    for bx, by, bw, expected_rows in self._bands:
                        mask = (1 << bw) - 1
                        missing = extra = 0
                        for dy, expected in enumerate(expected_rows):
                            actual = (packed[y + by + dy] >> (x + bx)) & mask
                            missing += (expected & ~actual).bit_count()
                            extra += (actual & ~expected).bit_count()
                            if missing > 2 or extra > 2:
                                break
                        errors.append((missing, extra))
                        if missing > 2 or extra > 2:
                            break
                    if len(errors) == 2 and all(m <= 2 and e <= 2 for m, e in errors):
                        self.last_result = {"matched": True, "reason": "both_title_lines", "origin": (x, y), "errors": errors}
                        return True
            return False
        except (AttributeError, TypeError, ValueError, IndexError, StopIteration):
            self.last_result = {"matched": False, "reason": "invalid_frame"}
            return False
