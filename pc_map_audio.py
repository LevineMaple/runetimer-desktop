"""Local two-line glyph references for map-specific rune-audio suppression.

Unknown fonts, scaling, obscured titles, or missing references allow audio.
"""
import json
import sys
from pathlib import Path


class MapAudioMatcher:
    def __init__(self, asset_path=None):
        self.last_result = {"matched": False, "reason": "not_checked"}
        self._references = []
        base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        directory = base / "assets" / "map_audio"
        paths = [Path(asset_path)] if asset_path is not None else [
            directory / "four_seasons.json", directory / "carcion.json"]
        for path in paths:
            try:
                self._references.append(self._load_reference(path))
            except (OSError, ValueError, KeyError, TypeError):
                continue
        if not self._references:
            self.last_result = {"matched": False, "reason": "reference_unavailable"}

    @staticmethod
    def _load_reference(path):
        asset = json.loads(path.read_text(encoding="utf-8"))
        width, height = asset["width"], asset["height"]
        if (asset["version"] != 1 or type(width) is not int or type(height) is not int
                or not 1 <= width <= 512 or not 1 <= height <= 128
                or not isinstance(asset["map_name"], str)):
            raise ValueError("Unsupported map reference")
        for value in (asset["threshold"], asset["max_color_spread"]):
            if type(value) is not int or not 0 <= value <= 255:
                raise ValueError("Invalid reference threshold")
        bands = []
        for band in asset["bands"]:
            x, y, bw, rows = band["x"], band["y"], band["width"], band["rows"]
            if (any(type(n) is not int for n in (x, y, bw))
                    or not isinstance(rows, list) or not rows
                    or not 0 <= x < x+bw <= width or not 0 <= y < y+len(rows) <= height
                    or any(not isinstance(row, str) or len(row) != bw
                           or set(row) - {"0", "1"} for row in rows)):
                raise ValueError("Invalid glyph reference")
            packed = [sum((ch == "1") << i for i, ch in enumerate(row)) for row in rows]
            if not any(packed):
                raise ValueError("Empty glyph reference")
            bands.append((x, y, bw, packed))
        if len(bands) != 2:
            raise ValueError("Both title bands are required")
        if bands[0][1] + len(bands[0][3]) > bands[1][1]:
            raise ValueError("Title bands must be separate and ordered")
        # Use the first nonempty row of the map-name band as a cheap stroke
        # filter, then compare both complete lines including blank margins.
        bx, by, bw, rows = bands[1]
        dy = next(i for i, row in enumerate(rows) if row)
        anchors = [bx+i for i in range(bw) if rows[dy] & (1 << i)][:14]
        return asset, bands, by+dy, anchors

    def match(self, frame):
        """Match both visible title lines at their native pixel scale."""
        self.last_result = {"matched": False, "reason": "no_exact_title"}
        if not self._references:
            self.last_result["reason"] = "reference_unavailable"
            return False
        try:
            width, height = frame.size
            rgb = frame.convert("RGB")
            masks = {}
            for asset, bands, anchor_y, anchors in self._references:
                tw, th = asset["width"], asset["height"]
                if width < tw or height < th:
                    continue
                threshold, spread = asset["threshold"], asset["max_color_spread"]
                key = (threshold, spread)
                if key not in masks:
                    pixels = iter(rgb.getdata())
                    packed = []
                    for _ in range(height):
                        row = 0
                        for x in range(width):
                            r, g, b = next(pixels)
                            low = min(r, g, b)
                            if low >= threshold and max(r, g, b)-low <= spread:
                                row |= 1 << x
                        packed.append(row)
                    masks[key] = packed
                packed = masks[key]
                valid_origins = (1 << (width-tw+1))-1
                for y in range(height-th+1):
                    candidates = valid_origins
                    for x in anchors:
                        candidates &= packed[y+anchor_y] >> x
                        if not candidates:
                            break
                    while candidates:
                        bit = candidates & -candidates
                        candidates ^= bit
                        x = bit.bit_length()-1
                        errors = []
                        for bx, by, bw, expected_rows in bands:
                            mask = (1 << bw)-1
                            missing = extra = 0
                            for dy, expected in enumerate(expected_rows):
                                actual = (packed[y+by+dy] >> (x+bx)) & mask
                                missing += (expected & ~actual).bit_count()
                                extra += (actual & ~expected).bit_count()
                                if missing > 2 or extra > 2:
                                    break
                            errors.append((missing, extra))
                            if missing > 2 or extra > 2:
                                break
                        if len(errors) == 2 and all(m <= 2 and e <= 2 for m, e in errors):
                            self.last_result = {
                                "matched": True, "reason": "both_title_lines",
                                "map_name": asset["map_name"], "origin": (x, y), "errors": errors}
                            return True
            return False
        except (AttributeError, TypeError, ValueError, IndexError, StopIteration):
            self.last_result = {"matched": False, "reason": "invalid_frame"}
            return False
