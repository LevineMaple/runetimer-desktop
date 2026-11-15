"""Local reader for the yellow remaining-time overlay on a selected Janus icon."""
import base64
import math
import re
from functools import lru_cache

from PIL import Image, ImageChops

# The HUD uses small raster digits. Alternatives cover the flat and rounded
# strokes seen after UI scaling. The 3 and 4 variants include the supplied 3:34.
_GLYPHS = {
    '0': ['.###./##.##/#...#/#...#/#...#/#...#/#...#/##.##/.###.'],
    '1': ['..#../.##../..#../..#../..#../..#../..#../..#../.###.',
          '.##/###/.##/.##/.##/.##/.##/.##/.##'],
    '2': ['####./...##/....#/....#/...#./..#../.#.../#..../#####',
          '.###./#...#/....#/...##/..##./.#.../##.../#..../#####'],
    '3': ['#####/....#/....#/...##/.###./...##/....#/...##/####.',
          '####./...##/....#/...##/.###./....#/....#/...##/####.',
          '.###./#...#/....#/...##/..##./...##/....#/#...#/.###.'],
    '4': ['...##./...##./..###./..#.#./.#..#./##.##./######/....#./....#.'],
    '5': ['#####/#..../#..../####./...##/....#/....#/...##/####.'],
    '6': ['..###/.#.../#..../####./##..#/#...#/#...#/##.##/.###.'],
    '7': ['#####/....#/...##/...#./..##./..#../..#../.#.../.#...'],
    '8': ['.###./##.##/#...#/##.##/.###./##.##/#...#/##.##/.###.'],
    '9': ['.###./##.##/#...#/#...#/.####/....#/....#/...#./###..'],
}


def _signature(image):
    # Occupancy in a fixed grid normalizes glyph size, retaining stroke widths.
    return image.resize((8, 12), Image.Resampling.BOX).tobytes()


@lru_cache(maxsize=1)
def _templates():
    result = {}
    for digit, variants in _GLYPHS.items():
        result[digit] = []
        for variant in variants:
            rows = variant.split('/')
            im = Image.new('L', (len(rows[0]), len(rows)))
            im.putdata([255 if p == '#' else 0 for row in rows for p in row])
            result[digit].append(_signature(im.crop(im.getbbox())))
    return result


def _digit(im):
    sig = _signature(im)
    scores = sorted((min(sum(abs(x-y) for x, y in zip(sig, sample))
                         for sample in samples) / (len(sig)*255), digit)
                    for digit, samples in _templates().items())
    if scores[0][0] > .34 or scores[1][0] - scores[0][0] < .017:
        return None
    return scores[0][1]


def _parse(group, mask):
    if not 1 <= len(group) <= 4:
        return None
    tops = [b[1] for b in group]
    bottoms = [b[3] for b in group]
    top, bottom = min(tops), max(bottoms)
    h = bottom-top
    if h < 5:
        return None
    chars = []
    for x, y, r, b in group:
        w, gh = r-x, b-y
        glyph = mask.crop((x, y, r, b))
        # A colon is two compact, vertically separated dots between the digits.
        if w <= h*.35 and gh <= h*.84 and y > top and b < bottom:
            rows = glyph.getprojection()[1]
            bands = sum(v and (i == 0 or not rows[i-1]) for i, v in enumerate(rows))
            if bands != 2:
                return None
            chars.append(':')
            continue
        if gh < .78*h or not .12 <= w/gh <= 1.08:
            return None
        digit = _digit(glyph)
        if digit is None:
            return None
        chars.append(digit)
    s = ''.join(chars)
    if len(s) == 4 and s[1] == ':' and s[2:].isdigit() and s[0].isdigit():
        mins, secs = int(s[0]), int(s[2:])
        if secs < 60 and mins*60 + secs <= 300:
            return mins*60 + secs
    if s.isdigit() and len(s) <= 3 and int(s) <= 300:
        return int(s)
    return None


def read_seconds(image):
    """Read one yellow m:ss or seconds-only label; None if ambiguous/unreadable."""
    if image is None or not (3 <= image.width <= 512 and 5 <= image.height <= 512):
        return None
    mask = Image.new('L', image.size)
    mask.putdata([255 if r >= 150 and g >= 145 and min(r,g)-b > 75 and abs(r-g) < 45 else 0
                  for r,g,b in image.convert('RGB').getdata()])
    columns = mask.getprojection()[0]
    runs = []
    start = None
    for x, occupied in enumerate(list(columns) + [0]):
        if occupied and start is None:
            start = x
        elif not occupied and start is not None:
            _, y, _, b = mask.crop((start, 0, x, mask.height)).getbbox()
            runs.append((start, y, x, b))
            start = None
    groups = []
    for run in runs:
        if groups:
            prev = groups[-1][-1]
            h = max(run[3]-run[1], prev[3]-prev[1])
            same_row = (abs((run[1]+run[3])-(prev[1]+prev[3])) <= .55*h
                        and min(run[3]-run[1],prev[3]-prev[1]) >= .36*h)
            if same_row and run[0]-prev[2] <= .52*h:
                groups[-1].append(run)
                continue
        groups.append([run])
    values = [v for g in groups if (v := _parse(g, mask)) is not None]
    return values[0] if len(values) == 1 else None



# Grayscale samples of the upper five rows of the supplied icon, normalized
# to 16px wide. The center and lower-right badge vary as the timer runs.
_TOP_RIMS = tuple(base64.b64decode(pattern) for pattern in (
    'OU08JDdxm5ubm0Y3JElEME0bN3HBmGZmZnWswXEuEk08N1XXWXOCgoJ7c1nXRjc8JEb/hHPVc3NzpNVzhKo3JFZx13WQ6qSUlMfqkHXBN1Y=',
    'OU08JDdxm5ubm0Y3JElEMEQSNzeq11lZWYT/qjckE0RJLkbBmGZ7e3txZpjBPyRJVnHXdZDqpJSUx+qQdcE3VnGqV3uk/9Vzc+r/pHurVXE=',
))


def _correlation(a, b):
    ma, mb = sum(a)/len(a), sum(b)/len(b)
    av, bv = [x-ma for x in a], [x-mb for x in b]
    norm = math.sqrt(sum(x*x for x in av) * sum(x*x for x in bv))
    return sum(x*y for x,y in zip(av,bv))/norm if norm else 0.0


MAX_REGION_WIDTH = 2048
MAX_REGION_HEIGHT = 512
_RIM_RUN = re.compile(rb'\xff{6,}')


def _violet_mask(rgb):
    red, green, blue = rgb.split()
    mask = ImageChops.subtract(blue, red).point(lambda v: 255 if v > 12 else 0)
    for channel in (ImageChops.subtract(blue, green).point(lambda v: 255 if v > 22 else 0),
                    ImageChops.subtract(green, red).point(lambda v: 255 if v <= 3 else 0),
                    red.point(lambda v: 255 if v > 15 else 0)):
        mask = ImageChops.darker(mask, channel)
    return mask


def _rim_boxes(mask):
    # The very top of the circular purple rim is one horizontal stroke about
    # half the icon width. Use it to delimit a local search before measuring
    # the icon. Other purple skills elsewhere cannot expand its bounding box.
    width, height = mask.size
    pixels = mask.tobytes()
    for y in range(height):
        offset = y*width
        for run in _RIM_RUN.finditer(pixels, offset, offset+width):
            span = run.end()-run.start()
            if span > 128:
                continue
            if y and pixels.find(b'\xff', run.start()-width, run.end()-width) >= 0:
                continue
            center = (run.start()+run.end())//2-offset
            radius = round(span*1.12)+1
            left, right = max(0, center-radius), min(width, center+radius)
            local = mask.crop((left, y, right, min(height, y+2*radius))).getbbox()
            if local:
                x1, _, x2, bottom = local
                w = x2-x1
                if (min(w, bottom) >= 12 and .8 <= w/bottom <= 1.25
                        and abs((x1+x2)/2+left-center) <= w*.12):
                    yield left+x1, y, left+x2, y+bottom


def _rim_score(rgb, box):
    rim = rgb.crop(box).convert('L').resize((16, 16), Image.Resampling.BOX)
    data = rim.crop((0, 0, 16, 5)).tobytes()
    return max(_correlation(data, ref) for ref in _TOP_RIMS)


def read_observation(image):
    """Locate the Janus icon within the selected skill bar, then read its label."""
    if image is None or not (10 <= image.width <= MAX_REGION_WIDTH
                             and 10 <= image.height <= MAX_REGION_HEIGHT):
        return False, None
    rgb = image.convert('RGB')
    violet = _violet_mask(rgb)
    matches = []
    for box in _rim_boxes(violet):
        score = _rim_score(rgb, box)
        if score >= .63:
            matches.append((score, box))
    if not matches:
        return False, None
    matches.sort(reverse=True)
    _, (left, top, right, bottom) = matches[0]
    for _, (x1, y1, x2, y2) in matches[1:]:
        # Multiple independent Janus-like icons with different labels would
        # make the countdown ambiguous. Overlapping proposals are one icon.
        if x1 >= right or x2 <= left or y1 >= bottom or y2 <= top:
            return False, None
    height = bottom-top
    label = rgb.crop((left, top+height//4, right, top+height*4//5))
    return True, read_seconds(label)


class JanusTracker:
    """One warning per confirmed countdown, with bounded digitless prediction."""
    def __init__(self):
        self.previous = None
        self.candidate = None
        self.deadline = None
        self.last_change = None
        self.decreasing = False
        self.alerted = False

    @staticmethod
    def _follows(previous, seconds, now):
        if previous is None:
            return False
        value, at = previous
        elapsed = now-at
        return 0 <= elapsed <= 4 and seconds <= value and abs((value-seconds)-elapsed) <= 1.2

    def _lost_icon(self):
        self.previous = self.candidate = self.deadline = self.last_change = None
        self.decreasing = False
        # Keep the latch: a brief occlusion mustn't repeat a previous warning.

    def update(self, seconds, now, icon_present=True, region_observed=False):
        # A visible, successfully sampled empty slot is different from a covered
        # or unavailable game window. Only bridge icon loss near expected expiry.
        near_expiry = self.deadline is not None and -1 <= self.deadline-now <= 15
        if not math.isfinite(now) or not (icon_present or (region_observed and near_expiry)):
            self._lost_icon()
            return False
        if seconds is None:
            self.candidate = None
            if (not self.alerted and self.decreasing and self.previous is not None
                    and self.previous[0] > 5
                    and self.previous[1]-self.last_change <= 2
                    and self.deadline-5 <= now <= self.deadline+1):
                self.alerted = True
                return True
            return False
        if not 0 <= seconds <= 300:
            return False
        if self._follows(self.previous, seconds, now):
            prior = self.previous
        elif self._follows(self.candidate, seconds, now):
            prior = self.candidate
            if seconds > 5 and (prior[0] >= 9 if self.previous is None
                                else prior[0] > self.previous[0]+1):
                self.alerted = False
            self.decreasing = False
            self.last_change = prior[1]
            self.deadline = prior[0]+prior[1]
        else:
            if self.previous and seconds > self.previous[0]:
                # A possible late extension should suspend the old forecast
                # until reliable countdown evidence resumes.
                self.decreasing = False
            self.candidate = (seconds, now)
            return False
        self.previous = (seconds, now)
        self.candidate = None
        if seconds < prior[0]:
            self.decreasing = True
            self.last_change = now
            self.deadline = now+seconds
        if 0 < seconds <= 5 and not self.alerted:
            self.alerted = True
            return True
        return False
