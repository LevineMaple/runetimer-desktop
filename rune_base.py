# SPDX-License-Identifier: GPL-3.0-or-later
#
# 룬 타이머 - Windows용 로컬 PiP 룬 알림 및 커스텀 타이머 도구
# Copyright (C) 2026
# Modified 2026-09-27 for this PC: isolated settings, capture backend and diagnostics.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

import json
import math
import os
import queue
import struct
import ctypes
import sys
import tempfile
import threading
import time
import traceback
import wave
import winsound
from datetime import datetime
from ctypes import wintypes
from collections import deque
from dataclasses import dataclass
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageGrab, ImageStat, ImageTk

np = None  # Optional acceleration is not required by rune detection.

dxcam = None  # This PC build uses physical-coordinate Pillow capture.


APP_DIR = Path(os.environ.get("RUNE_TIMER_PC_DATA", str(Path.home() / "AppData" / "Roaming" / "RuneTimerThisPC")))

def load_ui_profile():
    try:
        profile = json.loads((APP_DIR / "ui-profile.json").read_text(encoding="utf-8"))
        if profile in ("low", "high"):
            return profile
    except (OSError, ValueError, TypeError):
        pass
    return "low"

# One executable contains both asset sets; selection happens before Tk starts.
UI_PROFILE = next((arg.split("=", 1)[1] for arg in sys.argv[1:] if arg in ("--ui=low", "--ui=high")), load_ui_profile())
LOW_RES = UI_PROFILE == "low"
UI_FACTOR = 0.65 if LOW_RES else 1.0
MIN_UI_SCALE = 0.24 if LOW_RES else 0.55

def ui_px(value):
    return max(1, round(value * UI_FACTOR))

APP_NAME = "룬 타이머 · 이 PC용" + (" · 저해상도" if LOW_RES else " · 고해상도")
APP_USER_MODEL_ID = "Nilbox.RuneTimer.ThisPC"
DEFAULT_SESSION_SECONDS = 5 * 60 * 60
MIN_INTERVAL = 5
MAX_INTERVAL = 24 * 60 * 60
TRANSPARENT = "#ff00ff"
SETTINGS_PATH = APP_DIR / ("settings-low.json" if LOW_RES else "settings.json")
RUNTIME_LOG_PATH = APP_DIR / "runtime_log.txt"


def log_error(tag, exc=None):
    """무성 실패 추적용 경량 로그. 실패해도 앱에 영향 없음."""
    try:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        if RUNTIME_LOG_PATH.exists() and RUNTIME_LOG_PATH.stat().st_size > 512_000:
            RUNTIME_LOG_PATH.unlink()
        detail = ""
        if exc is not None:
            detail = " | " + "".join(traceback.format_exception_only(type(exc), exc)).strip()
        with RUNTIME_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} [{tag}]{detail}\n")
    except Exception:
        pass
SOUND_DIR = APP_DIR / "sounds"
FONT_FAMILY = "맑은 고딕"
SETTINGS_FONT_FAMILY = "NEXON Lv2 Gothic"
TIMER_NUMBER_FONT_FAMILY = "Poppins Thin"
TIMER_NUMBER_FONT_FILE = ("assets", "fonts", "timer", "Poppins-Thin.ttf")
NEXON_FONT_FILES = (
    "NEXON_Lv2_Gothic.ttf",
    "NEXON_Lv2_Gothic_Medium.ttf",
    "NEXON_Lv2_Gothic_Bold.ttf",
    "NEXON_Lv2_Gothic_Light.ttf",
)
MAPLE_PROCESS_NAMES = {"maplestory.exe"}
DEFAULT_RUNE_COOLDOWN_MINUTES = 15
RUNE_COOLDOWN_CHOICES = (10, 15)
RUNE_COOLDOWN_SECONDS = DEFAULT_RUNE_COOLDOWN_MINUTES * 60
WIDGET_WIDTH = 250 if LOW_RES else 384
WIDGET_HEIGHT = 90 if LOW_RES else 138
APP_WIDTH = 805
APP_HEIGHT = 1064
APP_SIZE_PRESETS = (
    (443, 586),
    (483, 638),
    (544, 719),
    (604, 798),
    (704, 931),
    (805, 1064),
    (906, 1198),
    (1006, 1330),
)
if LOW_RES:
    APP_SIZE_PRESETS = ((242, 320), (282, 373), (322, 426), (362, 479), (403, 532), (443, 586))
DEFAULT_APP_SIZE = (322, 426) if LOW_RES else (704, 931)
APP_MIN_WIDTH, APP_MIN_HEIGHT = APP_SIZE_PRESETS[0]
APP_MAX_WIDTH, APP_MAX_HEIGHT = APP_SIZE_PRESETS[-1]
SPLASH_WIDTH = ui_px(300)
SPLASH_HEIGHT = ui_px(310)
RESTORE_BLUR_CLEAR_TOP = 88
RESTORE_BLUR_HOLD_MS = 300
RESTORE_BLUR_FADE_STEP_MS = 50
RESTORE_BLUR_FADE_STEP_ALPHA = 0.20
OFFLINE_RUNE_ALERT_LIMIT = 3
OFFLINE_RUNE_ALERT_INTERVAL_SECONDS = 3.0
RUNE_WINDOW_SYNC_INTERVAL_SECONDS = 6.0
COPYRIGHT_YEAR = "2026"
LICENSE_NOTICE_TITLE = "라이선스 정보"
LICENSE_NOTICE_TEXT = (
    f"룬 타이머\n"
    f"Copyright (C) {COPYRIGHT_YEAR}\n\n"
    "이 프로그램은 자유 소프트웨어입니다.\n"
    "GNU General Public License version 3 또는 그 이후 버전의 조건에 따라\n"
    "재배포하거나 수정할 수 있습니다.\n\n"
    "이 프로그램은 유용하게 쓰이기를 바라며 배포되지만,\n"
    "어떠한 형태의 보증도 제공하지 않습니다.\n"
    "상품성이나 특정 목적 적합성에 대한 묵시적 보증도 포함되지 않습니다.\n\n"
    "라이선스 전문: 설치 폴더의 LICENSE 파일\n"
    "https://www.gnu.org/licenses/gpl-3.0.html\n\n"
    "포함된 외부 라이브러리와 폰트, 알림 음원의 라이선스는\n"
    "THIRD_PARTY_LICENSES.txt를 확인해 주세요."
)
DISCLAIMER_VERSION = 1
DISCLAIMER_TITLE = "이용약관"
DISCLAIMER_TERMS_PARAGRAPHS = (
    "룬 타이머는 넥슨 및 메이플스토리와 무관하게 제작된\n"
    "비공식 보조 프로그램입니다.\n\n"
    "본 프로그램은 사용자가 직접 지정한 화면 영역을 기반으로\n"
    "알림을 제공하기 위한 목적으로만 동작합니다.",
    "룬 타이머는 게임 클라이언트의 파일, 메모리, 패킷,\n"
    "프로세스 내부 데이터, 계정 정보, 키보드 입력,\n"
    "마우스 입력에 접근하지 않습니다.\n\n"
    "또한 게임을 대신 조작하거나, 자동으로 입력을 발생시키거나,\n"
    "게임 플레이를 자동화하는 기능을 포함하지 않습니다.",
    "프로그램은 사용자가 지정한 미니맵 영역을\n"
    "화면 캡처 방식으로 확인합니다.\n\n"
    "해당 캡처 데이터는 사용자 PC 안에서만 분석되며,\n"
    "캡처된 화면 정보는 외부 서버로 전송되지 않습니다.\n"
    "별도의 계정 로그인이나 인터넷 연결도 요구하지 않습니다.",
    "룬 타이머의 알림 기능은 화면에 표시되는\n"
    "특정 시각 정보를 기준으로 동작합니다.\n\n"
    "이는 게임 클라이언트 내부에 접근하는 방식이 아니라,\n"
    "사용자의 화면에 이미 표시된 정보를 확인하는\n"
    "보조 알림 구조입니다.",
    "본 프로그램은 메이플스토리의 공식 서비스 또는\n"
    "공식 허가 도구가 아닙니다.\n\n"
    "운영정책의 판단 및 적용은 게임 운영사의 기준에 따릅니다.\n"
    "사용자는 본 프로그램의 작동 방식과 책임 범위를 이해한 뒤,\n"
    "본인의 판단과 책임 하에 프로그램을 사용해야 합니다.",
)
DISCLAIMER_SECTIONS = (
    (
        "비공식 보조 도구",
        "룬 타이머는 메이플스토리 공식 서비스가 아니며, 넥슨 또는 게임 운영사의\n"
        "공식 허가를 받은 도구가 아닙니다.",
    ),
    (
        "화면 캡처 기반 분석",
        "사용자가 직접 지정한 미니맵 영역만 이 PC 안에서 분석합니다.\n"
        "게임 클라이언트 파일, 메모리, 패킷, 키보드/마우스 입력에는 접근하지 않으며,\n"
        "어떤 데이터도 외부로 전송하지 않습니다.\n"
        "인터넷 연결 자체가 필요 없는 프로그램입니다.",
    ),
    (
        "수동 모드",
        "화면 캡처가 부담스러운 경우, 캡처 없이 순수 타이머로만 작동하는\n"
        "수동 모드를 설정에서 켤 수 있습니다.",
    ),
    (
        "사용자 책임",
        "이 프로그램 사용으로 발생할 수 있는 계정, 게임 이용, 기타 문제의 책임은\n"
        "사용자 본인에게 있습니다.",
    ),
)
DISCLAIMER_CONFIRM_TEXT = "위 내용을 확인했으며,\n사용에 따른 책임이 본인에게 있음을 이해했습니다."


def resource_path(*parts):
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    if len(parts) == 1 and Path(parts[0]).suffix.lower() in (".png", ".ico"):
        variant = base / "assets" / "ui" / UI_PROFILE / parts[0]
        if variant.exists():
            return variant
    return base.joinpath(*parts)


def set_windows_app_user_model_id():
    if not sys.platform.startswith("win"):
        return
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass


def nearest_app_size(width, height):
    try:
        width = int(width)
        height = int(height)
    except (TypeError, ValueError):
        return DEFAULT_APP_SIZE
    return min(APP_SIZE_PRESETS, key=lambda size: (size[0] - width) ** 2 + (size[1] - height) ** 2)


def clamp_int(value, fallback, min_value=MIN_INTERVAL, max_value=MAX_INTERVAL):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(min_value, min(max_value, parsed))


def clamp_float(value, fallback, min_value, max_value):
    try:
        parsed = float(str(value).replace("%", "").strip())
    except (TypeError, ValueError):
        parsed = fallback
    return max(min_value, min(max_value, parsed))


def clamp_bool(value, fallback=True):
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
    if isinstance(value, (int, float)):
        return bool(value)
    return bool(fallback)


def normalize_rune_cooldown_minutes(value, fallback=DEFAULT_RUNE_COOLDOWN_MINUTES):
    try:
        parsed = int(float(value))
    except (TypeError, ValueError):
        parsed = fallback
    return parsed if parsed in RUNE_COOLDOWN_CHOICES else fallback


def hex_to_rgb(color):
    color = str(color).lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def rgb_to_hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*[max(0, min(255, int(v))) for v in rgb])


def blend_hex(start, end, t):
    t = max(0.0, min(1.0, float(t)))
    s = hex_to_rgb(start)
    e = hex_to_rgb(end)
    return rgb_to_hex(tuple(s[i] * (1 - t) + e[i] * t for i in range(3)))


def fmt(seconds):
    seconds = max(0, int(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def write_wav(path, samples, rate=44100):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        frames = bytearray()
        for sample in samples:
            sample = max(-1.0, min(1.0, sample))
            frames.extend(struct.pack("<h", int(sample * 32767)))
        wav.writeframes(frames)


def prepare_sounds():
    SOUND_DIR.mkdir(exist_ok=True)
    rate = 44100
    paths = {
        "left": SOUND_DIR / "left_clicks.wav",
        "right": SOUND_DIR / "right_chime.wav",
        "skill": SOUND_DIR / "skill_pop.wav",
        "warning": SOUND_DIR / "warning_triplet.wav",
        "rune": SOUND_DIR / "rune_alert.wav",
        "done": SOUND_DIR / "session_done.wav",
    }
    tts_warning = resource_path("assets", "sounds", "tts_warning.mp3")
    tts_rune = resource_path("assets", "sounds", "tts_rune.mp3")
    tts_rune_due_candidates = (
        resource_path("assets", "sounds", "tts_rune_due.mp3"),
        resource_path("assets", "sounds", "tts_rune_due.wav"),
        resource_path("assets", "sounds", "rune_due_tts.mp3"),
        resource_path("assets", "sounds", "rune_due_tts.wav"),
    )
    if tts_warning.exists():
        paths["warning_tts"] = tts_warning
    if tts_rune.exists():
        paths["rune_tts"] = tts_rune
    for tts_rune_due in tts_rune_due_candidates:
        if tts_rune_due.exists():
            paths["rune_due_tts"] = tts_rune_due
            break

    samples = [0.0] * int(rate * 0.34)
    for start_s in (0.02, 0.17):
        start = int(rate * start_s)
        for i in range(int(rate * 0.045)):
            decay = math.exp(-i / (rate * 0.008))
            pulse = math.sin(2 * math.pi * 2100 * i / rate)
            noise = 1.0 if i % 2 == 0 else -1.0
            samples[start + i] += 0.36 * decay * (0.65 * pulse + 0.35 * noise)
    write_wav(paths["left"], samples, rate)

    samples = []
    for i in range(int(rate * 0.48)):
        t = i / rate
        attack = min(1.0, t / 0.035)
        decay = math.exp(-t / 0.23)
        tone = 0.52 * math.sin(2 * math.pi * 784 * t) + 0.24 * math.sin(2 * math.pi * 1176 * t) + 0.12 * math.sin(2 * math.pi * 1568 * t)
        samples.append(0.42 * attack * decay * tone)
    write_wav(paths["right"], samples, rate)

    samples = []
    for i in range(int(rate * 0.22)):
        t = i / rate
        env = min(1.0, t / 0.015) * math.exp(-t / 0.11)
        samples.append(0.42 * env * math.sin(2 * math.pi * (980 + 120 * t) * t))
    write_wav(paths["skill"], samples, rate)

    samples = [0.0] * int(rate * 0.58)
    for start_s in (0.02, 0.20, 0.38):
        start = int(rate * start_s)
        for i in range(int(rate * 0.11)):
            t = i / rate
            samples[start + i] += 0.38 * math.exp(-t / 0.055) * math.sin(2 * math.pi * 520 * t)
    write_wav(paths["warning"], samples, rate)

    samples = []
    for i in range(int(rate * 0.62)):
        t = i / rate
        env = min(1.0, t / 0.025) * math.exp(-t / 0.34)
        shimmer = 0.38 * math.sin(2 * math.pi * 1046.5 * t) + 0.24 * math.sin(2 * math.pi * 1396.9 * t)
        samples.append(0.42 * env * shimmer)
    write_wav(paths["rune"], samples, rate)

    samples = []
    for i in range(int(rate * 0.86)):
        t = i / rate
        env = min(1.0, t / 0.04) * math.exp(-t / 0.55)
        chord = 0.4 * math.sin(2 * math.pi * 523.25 * t) + 0.35 * math.sin(2 * math.pi * 659.25 * t) + 0.3 * math.sin(2 * math.pi * 783.99 * t)
        samples.append(0.38 * env * chord)
    write_wav(paths["done"], samples, rate)
    return {k: str(v) for k, v in paths.items()}


@dataclass
class TimerItem:
    name: str
    seconds: int
    enabled: bool = True
    remaining: int = 0
    deadline: float = 0.0

    def reset(self, now=None):
        now = time.monotonic() if now is None else now
        self.remaining = self.seconds
        self.deadline = now + self.seconds

    def tick(self, now):
        if not self.enabled:
            return False
        if self.deadline <= 0:
            self.reset(now)
        self.remaining = max(0, int(self.deadline - now + 0.999))
        if self.remaining <= 0:
            self.reset(now)
            return True
        return False

    def to_dict(self):
        return {"name": self.name, "seconds": self.seconds, "enabled": self.enabled}

    @classmethod
    def from_dict(cls, data):
        item = cls(str(data.get("name") or "타이머"), clamp_int(data.get("seconds"), 60), bool(data.get("enabled", True)))
        item.reset()
        return item


class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, command, width=76, height=32, radius=16, bg="#50edb1", fg="#050706", hover="#25d999", font=(FONT_FAMILY, 10, "bold"), outline=None):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.command, self.width, self.height, self.radius = command, width, height, radius
        self.fill, self.hover, self.fg, self.text, self.font, self.outline = bg, hover, fg, text, font, outline
        self._draw(self.fill)
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e: self._draw(self.hover))
        self.bind("<Leave>", lambda _e: self._draw(self.fill))

    def _click(self, _event=None):
        self.command()
        return "break"

    def configure_style(self, text, bg, fg, hover, outline=None):
        self.text, self.fill, self.fg, self.hover = text, bg, fg, hover
        if outline is not None:
            self.outline = outline
        self._draw(self.fill)

    def _draw(self, fill):
        self.delete("all")
        self._rounded_rect(1, 1, self.width - 1, self.height - 1, self.radius, fill=fill, outline=self.outline or fill)
        self.create_text(self.width // 2, self.height // 2, text=self.text, fill=self.fg, font=self.font)

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)


class ApplyCheckButton(tk.Canvas):
    def __init__(self, parent, command, width=76, height=48, radius=24, bg="#050707", hover="#0a1512", outline="#000000"):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.width = width
        self.height = height
        self.radius = radius
        self.fill = bg
        self.hover = hover
        self.outline = outline
        self.check_photo = None
        self._draw(self.fill)
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e: self._draw(self.hover))
        self.bind("<Leave>", lambda _e: self._draw(self.fill))

    def _click(self, _event=None):
        self.command()
        return "break"

    def _draw(self, fill):
        self.delete("all")
        self._rounded_rect(1, 1, self.width - 1, self.height - 1, self.radius, fill=fill, outline=self.outline, width=2)
        self.check_photo = self._make_check_image()
        self.create_image(self.width // 2, self.height // 2, image=self.check_photo)

    def _make_check_image(self):
        width, height = self.width, self.height
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        points = [
            (int(width * 0.30), int(height * 0.52)),
            (int(width * 0.43), int(height * 0.67)),
            (int(width * 0.71), int(height * 0.33)),
        ]
        glow_mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(glow_mask).line(points, fill=155, width=max(12, int(height * 0.30)), joint="curve")
        glow = Image.new("RGBA", (width, height), (66, 246, 190, 0))
        glow.putalpha(glow_mask.filter(ImageFilter.GaussianBlur(max(3, int(height * 0.10)))))
        image.alpha_composite(glow)

        stroke_mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(stroke_mask).line(points, fill=255, width=max(6, int(height * 0.13)), joint="curve")
        gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pixels = gradient.load()
        for x in range(width):
            t = x / max(1, width - 1)
            red = int(66 * (1 - t) + 26 * t)
            green = int(246 * (1 - t) + 209 * t)
            blue = int(190 * (1 - t) + 221 * t)
            for y in range(height):
                pixels[x, y] = (red, green, blue, 255)
        gradient.putalpha(stroke_mask)
        image.alpha_composite(gradient)
        return ImageTk.PhotoImage(image)

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)


class IconButton(tk.Canvas):
    def __init__(self, parent, image_path, command, width=30, height=30, bg=None, hover=None, tint=None):
        self.bg_color = bg or parent["bg"]
        self.hover_color = hover or self.bg_color
        super().__init__(parent, width=width, height=height, bg=self.bg_color, highlightthickness=0, bd=0, cursor="hand2")
        self.command, self.width, self.height = command, width, height
        self.tint = tint
        self.image = self._load_image(image_path)
        self._draw(self.bg_color)
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e: self._draw(self.hover_color))
        self.bind("<Leave>", lambda _e: self._draw(self.bg_color))

    def _click(self, _event=None):
        self.command()
        return "break"

    def _load_image(self, image_path):
        size = min(self.width, self.height) - 4
        image = Image.open(image_path).convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        if self.tint:
            tint = self.tint.lstrip("#")
            color = tuple(int(tint[i:i+2], 16) for i in (0, 2, 4))
            alpha = image.getchannel("A")
            tinted = Image.new("RGBA", image.size, color + (0,))
            tinted.putalpha(alpha)
            image = tinted
        return ImageTk.PhotoImage(image)

    def _draw(self, fill):
        self.delete("all")
        self.configure(bg=fill)
        self.create_image(self.width // 2, self.height // 2, image=self.image)


class GearButton(tk.Canvas):
    def __init__(self, parent, command, width=44, height=44, bg="#111314", fg="#4af1ae", hover="#16201d", outline="#2b3031"):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.width = width
        self.height = height
        self.fill = bg
        self.fg = fg
        self.hover = hover
        self.outline = outline
        self.icon = self._load_icon()
        self._draw(self.fill)
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e: self._draw(self.hover))
        self.bind("<Leave>", lambda _e: self._draw(self.fill))

    def _click(self, _event=None):
        self.command()
        return "break"

    def _load_icon(self):
        path = resource_path("settings_icon.png")
        if not path.exists():
            return None
        size = max(18, int(min(self.width, self.height) * 0.39))
        image = Image.open(path).convert("RGBA")
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
        tint = self.fg.lstrip("#")
        color = tuple(int(tint[i:i+2], 16) for i in (0, 2, 4))
        alpha = image.getchannel("A")
        tinted = Image.new("RGBA", image.size, color + (0,))
        tinted.putalpha(alpha)
        return ImageTk.PhotoImage(tinted)

    def _draw(self, fill):
        self.delete("all")
        corner = max(14, int(min(self.width, self.height) * 0.32))
        self._rounded_rect(1, 1, self.width - 1, self.height - 1, corner, fill=fill, outline=self.outline)
        if self.icon is not None:
            self.create_image(self.width // 2, self.height // 2, image=self.icon)
            return
        cx, cy = self.width / 2, self.height / 2
        radius = max(8, int(min(self.width, self.height) * 0.17))
        self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, outline=self.fg, width=2)
        inner = max(3, int(radius * 0.36))
        self.create_oval(cx - inner, cy - inner, cx + inner, cy + inner, outline=self.fg, width=2)

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)


class BackIconButton(tk.Canvas):
    def __init__(self, parent, command, width=106, height=106, bg="#181a1b", fg="#f4f6f7", hover="#222526", outline="#2b3031"):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.command = command
        self.width = width
        self.height = height
        self.fill = bg
        self.fg = fg
        self.hover = hover
        self.outline = outline
        self._draw(self.fill)
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e: self._draw(self.hover))
        self.bind("<Leave>", lambda _e: self._draw(self.fill))

    def _click(self, _event=None):
        self.command()
        return "break"

    def _draw(self, fill):
        self.delete("all")
        inset = max(2, int(min(self.width, self.height) * 0.04))
        self.create_oval(inset, inset, self.width - inset, self.height - inset, fill=fill, outline=self.outline, width=2 if self.outline else 0)
        cx, cy = self.width / 2, self.height / 2
        scale = min(self.width, self.height) / 106
        self.create_line(cx + 14 * scale, cy - 21 * scale, cx - 10 * scale, cy, cx + 14 * scale, cy + 21 * scale, fill=self.fg, width=max(4, int(8 * scale)), capstyle=tk.ROUND, joinstyle=tk.ROUND)

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)


class ToggleSwitch(tk.Canvas):
    def __init__(self, parent, value, command, width=74, height=34, on="#4af1ae", off="#25292a", knob="#f4f6f7"):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.value = bool(value)
        self.command = command
        self.width = width
        self.height = height
        self.on = on
        self.off = off
        self.knob = knob
        self._draw()
        self.bind("<Button-1>", self._toggle)

    def set_value(self, value):
        self.value = bool(value)
        self._draw()

    def _toggle(self, _event=None):
        self.value = not self.value
        self._draw()
        self.command(self.value)
        return "break"

    def _draw(self):
        self.delete("all")
        radius = self.height // 2
        fill = self.on if self.value else self.off
        outline = self.on if self.value else "#3a3f40"
        self._rounded_rect(1, 1, self.width - 1, self.height - 1, radius, fill=fill, outline=outline, width=2)
        knob_radius = self.height // 2 - 5
        cx = self.width - self.height // 2 if self.value else self.height // 2
        cy = self.height // 2
        knob_fill = "#06100d" if self.value else self.knob
        self.create_oval(cx - knob_radius, cy - knob_radius, cx + knob_radius, cy + knob_radius, fill=knob_fill, outline=knob_fill)
        self.create_text(self.width * (0.32 if self.value else 0.68), cy, text="ON" if self.value else "OFF", fill="#06100d" if self.value else "#8a9094", font=(FONT_FAMILY, 7, "bold"))

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)


class VolumeSlider(tk.Canvas):
    def __init__(self, parent, value, command, width=250, height=42, start="#4af1ae", end="#9ff7d2"):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.value = int(max(0, min(100, value)))
        self.command = command
        self.width = width
        self.height = height
        self.start = start
        self.end = end
        self.dragging = False
        self._draw()
        self.bind("<Button-1>", self._set_from_event)
        self.bind("<B1-Motion>", self._set_from_event)
        self.bind("<ButtonRelease-1>", self._set_from_event)

    def set_value(self, value):
        self.value = int(max(0, min(100, value)))
        self._draw()

    def _set_from_event(self, event):
        bar_x = 8
        bar_w = max(1, self.width - 62)
        ratio = (event.x - bar_x) / bar_w
        self.value = int(round(max(0.0, min(1.0, ratio)) * 100))
        self._draw()
        self.command(self.value)
        return "break"

    def _draw(self):
        self.delete("all")
        bar_x = 8
        bar_y = self.height // 2 - 5
        bar_w = max(1, self.width - 62)
        bar_h = 10
        radius = bar_h // 2
        self._rounded_rect(bar_x, bar_y, bar_x + bar_w, bar_y + bar_h, radius, fill="#262b2c", outline="#262b2c")
        fill_w = int(bar_w * (self.value / 100.0))
        if fill_w > 0:
            for x in range(fill_w):
                color = blend_hex(self.start, self.end, x / max(1, bar_w - 1))
                self.create_line(bar_x + x, bar_y, bar_x + x, bar_y + bar_h, fill=color)
            self._rounded_rect(bar_x, bar_y, bar_x + fill_w, bar_y + bar_h, radius, fill="", outline="")
        knob_x = bar_x + fill_w
        knob_r = 8
        self.create_oval(knob_x - knob_r, self.height // 2 - knob_r, knob_x + knob_r, self.height // 2 + knob_r, fill="#f4f6f7", outline="#f4f6f7")
        self.create_text(self.width - 21, self.height // 2, text=str(self.value), fill="#4af1ae", font=(FONT_FAMILY, 9, "bold"))

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)


class MinuteSegmentedControl(tk.Canvas):
    def __init__(self, parent, value, command, width=214, height=40, active="#4af1ae", bg="#202324", fg="#eef3f4"):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.value = normalize_rune_cooldown_minutes(value)
        self.command = command
        self.width = width
        self.height = height
        self.active = active
        self.fill = bg
        self.fg = fg
        self._draw()
        self.bind("<Button-1>", self._select)

    def set_value(self, value):
        self.value = normalize_rune_cooldown_minutes(value, self.value)
        self._draw()

    def _select(self, event):
        selected = RUNE_COOLDOWN_CHOICES[0] if event.x < self.width / 2 else RUNE_COOLDOWN_CHOICES[1]
        if selected == self.value:
            return "break"
        self.value = selected
        self._draw()
        self.command(selected)
        return "break"

    def _draw(self):
        self.delete("all")
        radius = self.height // 2
        self._rounded_rect(1, 1, self.width - 1, self.height - 1, radius, fill=self.fill, outline="#353a3b", width=2)
        segment_w = self.width / len(RUNE_COOLDOWN_CHOICES)
        for index, minutes in enumerate(RUNE_COOLDOWN_CHOICES):
            x1 = index * segment_w + 4
            x2 = (index + 1) * segment_w - 4
            active = minutes == self.value
            if active:
                self._rounded_rect(x1, 5, x2, self.height - 5, radius - 5, fill=self.active, outline=self.active, width=1)
            self.create_text(
                (x1 + x2) / 2,
                self.height / 2,
                text=f"{minutes}분",
                fill="#06100d" if active else self.fg,
                font=(FONT_FAMILY, 9, "bold"),
            )

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        self.create_polygon(points, smooth=True, splinesteps=18, **kwargs)


def parse_booster_use_count(value):
    if isinstance(value, str):
        text = value.strip()
        if not text or not text.isdecimal():
            raise ValueError("1 이상의 정수를 입력하세요.")
        value = int(text)
    if type(value) is not int or value < 1:
        raise ValueError("1 이상의 정수를 입력하세요.")
    return value


def normalize_booster_use_count(value):
    try:
        return parse_booster_use_count(value)
    except (ValueError, TypeError, OverflowError):
        return 3


class ScanButton(tk.Canvas):
    def __init__(self, parent, text, command, width=380, height=136, bg="#050707", fg="#4af1ae", hover="#0a1512"):
        super().__init__(parent, width=width, height=height, bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        self.text = text
        self.command = command
        self.width = width
        self.height = height
        self.fill = bg
        self.fg = fg
        self.hover = hover
        self._draw(self.fill)
        self.bind("<Button-1>", self._click)
        self.bind("<Enter>", lambda _e: self._draw(self.hover))
        self.bind("<Leave>", lambda _e: self._draw(self.fill))

    def _click(self, _event=None):
        self.command()
        return "break"

    def _draw(self, fill):
        self.delete("all")
        radius = self.height // 2
        self._rounded_rect(2, 2, self.width - 2, self.height - 2, radius, fill=fill, outline=self.fg, width=4)
        cx = self.width * 0.32
        cy = self.height / 2
        s = 20
        line_opts = {"fill": self.fg, "width": 3, "capstyle": tk.ROUND}
        self.create_line(cx - s, cy - s, cx - s + 11, cy - s, **line_opts)
        self.create_line(cx - s, cy - s, cx - s, cy - s + 11, **line_opts)
        self.create_line(cx + s, cy - s, cx + s - 11, cy - s, **line_opts)
        self.create_line(cx + s, cy - s, cx + s, cy - s + 11, **line_opts)
        self.create_line(cx - s, cy + s, cx - s + 11, cy + s, **line_opts)
        self.create_line(cx - s, cy + s, cx - s, cy + s - 11, **line_opts)
        self.create_line(cx + s, cy + s, cx + s - 11, cy + s, **line_opts)
        self.create_line(cx + s, cy + s, cx + s, cy + s - 11, **line_opts)
        self.create_text(self.width * 0.58, cy, text=self.text, fill=self.fg, font=(FONT_FAMILY, 12, "bold"), anchor="center")

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        self.create_polygon(points, smooth=True, splinesteps=24, **kwargs)


class RegionSelector(tk.Toplevel):
    def __init__(self, parent, on_selected, prompt="감지할 게임 영역을 드래그하세요 · Esc 취소", on_closed=None):
        super().__init__(parent)
        self.on_selected, self.start_x, self.start_y, self.rect_id = on_selected, 0, 0, None
        self.on_closed = on_closed
        self.closed = False
        self.parent = parent
        self.attributes("-fullscreen", True)
        self.attributes("-alpha", 0.28)
        self.attributes("-topmost", True)
        self.configure(bg="#000")
        self.canvas = tk.Canvas(self, bg="#000", highlightthickness=0, cursor="crosshair")
        self.canvas.pack(fill="both", expand=True)
        self.canvas.create_text(self.winfo_screenwidth()//2, 48, text=prompt, fill="#50edb1", font=(FONT_FAMILY, 18, "bold"))
        self.canvas.bind("<ButtonPress-1>", self._start)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._finish)
        self.bind("<Escape>", self._cancel)
        self.canvas.bind("<Escape>", self._cancel)
        self.bind_all("<Escape>", self._cancel)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(30, self._claim_keyboard_focus)

    def _claim_keyboard_focus(self):
        if self.closed:
            return
        try:
            self.lift()
            self.focus_force()
            self.canvas.focus_set()
            self.grab_set()
        except tk.TclError:
            pass

    def _cancel(self, _event=None):
        self._close()
        return "break"

    def _start(self, event):
        self.start_x, self.start_y = event.x, event.y
        self.rect_id = self.canvas.create_rectangle(event.x, event.y, event.x, event.y, outline="#ff9f0a", width=3)

    def _drag(self, event):
        if self.rect_id is not None:
            self.canvas.coords(self.rect_id, self.start_x, self.start_y, event.x, event.y)

    def _finish(self, event):
        if self.rect_id is None:
            return
        x1, x2 = sorted((self.start_x, event.x))
        y1, y2 = sorted((self.start_y, event.y))
        if x2 - x1 >= 24 and y2 - y1 >= 24:
            self.on_selected((x1, y1, x2, y2))
        self._close()

    def _close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.unbind_all("<Escape>")
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        if self.on_closed:
            self.on_closed()


class MapleTimerApp:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        set_windows_app_user_model_id()
        self.sound_paths = prepare_sounds()
        self.sound_queue = queue.Queue()
        self.sound_thread = threading.Thread(target=self._sound_loop, daemon=True)
        self.sound_thread.start()
        self.root = tk.Tk()
        if LOW_RES:
            self.root.tk.call("tk", "scaling", 1.0)
        self.root.title(APP_NAME)
        self.root.geometry(f"{DEFAULT_APP_SIZE[0]}x{DEFAULT_APP_SIZE[1]}+80+80")
        self.root.minsize(APP_MIN_WIDTH, APP_MIN_HEIGHT)
        self.root.attributes("-topmost", True)
        self.root.overrideredirect(False)
        self.root.protocol("WM_DELETE_WINDOW", self._quit_app)
        self.root.configure(bg=TRANSPARENT)
        self.icon_path = resource_path("maple_timer_custom_icon.ico")
        self.app_icon_photo = None
        self._apply_window_icon(self.root)
        try:
            self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass
        self.root.withdraw()
        self.font_family = self._load_nexon_fonts()
        self.settings_font_family = self._load_settings_font()
        self.timer_number_family = self._load_timer_number_font()

        self.colors = {
            "surface": "#000000",
            "surface_alt": "#121314",
            "panel": "#111314",
            "panel_2": "#191b1c",
            "panel_3": "#202324",
            "text": "#eef3f4",
            "muted": "#8a9094",
            "muted_2": "#5e666a",
            "line": "#2b3031",
            "line_strong": "#4af1ae",
            "blue": "#4af1ae",
            "blue_hover": "#6cf6be",
            "cyan": "#9ff7d2",
            "orange": "#ff9f0a",
            "orange_hover": "#ffb340",
            "red": "#ff5b5b",
            "yellow": "#ffcc36",
            "green": "#2ad668",
            "purple": "#4af1ae",
            "shadow": "#000000",
            "glow": "#071915",
            "hover": "#1b2222",
        }
        self.running = False
        self.session_seconds = DEFAULT_SESSION_SECONDS
        self.session_remaining = DEFAULT_SESSION_SECONDS
        self.session_deadline = 0.0
        self.session_cycles = 0
        self.timers = []
        self.region = None
        self.rune_region = None
        self.rune_window_anchor = None
        self.app_position = None
        self.app_size = DEFAULT_APP_SIZE
        self.monitor_enabled = False
        self.monitor_threshold = 4.0
        self.blue_damage_threshold = 0.08
        self.blue_presence_threshold = 2.0
        self.rune_threshold = 50.0
        self.blue_activity_max = 8.0
        self.monitor_stall_seconds = 7.0
        self.monitor_interval_ms = 3000
        self.timer_display_interval_ms = 1000
        self.timer_display_after_id = None
        self.last_capture = None
        self.last_motion_at = time.monotonic()
        self.last_motion_score = 0.0
        self.blue_damage_score = 0.0
        self.last_blue_damage_score = None
        self.blue_activity_score = 0.0
        self.blue_event_seen = False
        self.rune_score = 0.0
        self.rune_baseline_score = None
        self.blue_baseline_score = None
        self.last_blue_mask = None
        self.blue_presence_seen = False
        self.warning_loop_seconds = 58.0
        self.last_stall_alert_at = self.last_motion_at
        self.warning_timer_paused = False
        self.warning_paused_remaining = self.warning_loop_seconds
        self.warning_sound_enabled = True
        self.rune_sound_enabled = True
        self.booster_mode_enabled = False
        self.booster_use_count = 3
        self.tts_sound_enabled = False
        self.warning_volume = 100
        self.rune_volume = 100
        self.halfhour_volume = 100
        self.shutting_down = False
        self.sound_volume_cache = {}
        self.rune_cooldown_minutes = DEFAULT_RUNE_COOLDOWN_MINUTES
        self.last_rune_cleared_at = None
        self.last_rune_cleared_wall = None
        self.offline_mode_enabled = False
        self.offline_rune_due = False
        self.offline_rune_alert_count = 0
        self.offline_rune_next_alert_at = 0.0
        self.last_offline_rune_progress_draw_at = 0.0
        self.countdown_press_root = None
        self.countdown_number_item = None
        self.countdown_progress_item = None
        self.countdown_progress_update_interval = 5.0
        self.last_countdown_progress_update_at = 0.0
        self.last_rune_alert_at = 0.0
        self.rune_alert_interval = 1.0
        self.stall_alert_latched = False
        self.rune_alert_latched = False
        self.rune_active_visual = False
        self.rune_capture_active = False
        self.maplestory_process_running = False
        self.last_maplestory_process_check_at = 0.0
        self.last_rune_window_sync_at = 0.0
        self.rune_blink_on = False
        self.rune_blink_after_id = None
        self.auto_detect_enabled = False
        self.auto_detect_interval_ms = 60000
        self.auto_detect_notice_shown = False
        self.last_auto_detect_region = None
        self.auto_detect_status_var = None
        self.drag_blocked = False
        self.drag_start_x = self.drag_start_y = 0
        self.drag_offset_x = self.drag_offset_y = 0
        self.dragging_main_window = False
        self.drag_using_proxy = False
        self.drag_proxy = None
        self.drag_proxy_photo = None
        self.widget_drag_start_x = self.widget_drag_start_y = 0
        self.widget_window_start_x = self.widget_window_start_y = 0
        self.widget_mode_active = False
        self.widget_position = None
        self.widget = None
        self.widget_canvas = None
        self.widget_count_text_item = None
        self.widget_background_photo = None
        self.widget_count_press_root = None
        self.widget_rune_press_root = None
        self.resize_start_x = self.resize_start_y = 0
        self.resize_start_w = self.resize_start_h = 0
        self.resize_fixed_position = None
        self.resizing_main_window = False
        self.surface_refresh_after_id = None
        self.surface_widgets = []
        self.timer_rows = []
        self.capture_camera = None
        self.capture_lock = threading.Lock()
        self.worker_results = queue.Queue()
        self.monitor_worker_running = False
        self.auto_detect_worker_running = False
        self.main_app_started = False
        self.keep_visible_tick_started = False
        self.disclaimer_accepted = False
        self.disclaimer_accepted_at = None
        self.disclaimer_version = 0
        self.disclaimer_dialog = None
        self.first_launch_centered_done = False
        self.center_first_launch_after_disclaimer = False

        self._load_settings()
        self.warning_timer_paused = True
        self.warning_paused_remaining = self.warning_loop_seconds
        self.last_stall_alert_at = time.monotonic()
        self.rune_capture_active = bool(self.rune_region) and not self.offline_mode_enabled
        self.stall_var = tk.StringVar(value=str(self.warning_loop_seconds))
        self.threshold_var = tk.StringVar(value=str(int(self.monitor_threshold)))
        self.blue_threshold_var = tk.StringVar(value=f"{self.blue_damage_threshold:.2f}")
        self.rune_threshold_var = tk.StringVar(value=f"{self.rune_threshold:.2f}")
        self.warning_sound_var = tk.BooleanVar(value=self.warning_sound_enabled)
        self.rune_sound_var = tk.BooleanVar(value=self.rune_sound_enabled)
        self.tts_sound_var = tk.BooleanVar(value=self.tts_sound_enabled)
        self.offline_mode_var = tk.BooleanVar(value=self.offline_mode_enabled)
        if self.offline_mode_enabled and self.last_rune_cleared_at is None:
            self.last_rune_cleared_at = time.monotonic()
            self.last_rune_cleared_wall = time.time()
        width, height = self.app_size
        # The splash is centered using the virtual desktop bounds. Start the
        # main window from that same center so every monitor layout, taskbar
        # position, and resolution follows one coordinate system.
        self.app_position = self._center_app_position(width, height)
        self.root.geometry(f"{width}x{height}+{self.app_position[0]}+{self.app_position[1]}")
        self.monitor_enabled = True
        self._build_ui()
        if self._disclaimer_acceptance_required():
            self.root.after(50, self._start_main_app)
        else:
            self._show_startup_splash()

    def _load_nexon_fonts(self):
        if FONT_FAMILY != SETTINGS_FONT_FAMILY:
            return FONT_FAMILY
        return self._load_settings_font()

    def _register_nexon_font_files(self):
        font_dir = resource_path("assets", "fonts", "package", "src")
        try:
            add_font = ctypes.windll.gdi32.AddFontResourceExW
            loaded = False
            for name in NEXON_FONT_FILES:
                path = font_dir / name
                if path.exists():
                    add_font(str(path), 0x10, 0)
                    loaded = True
            if not loaded:
                return False
            ctypes.windll.user32.PostMessageW(0xFFFF, 0x001D, 0, 0)
            return True
        except Exception:
            return False

    def _load_settings_font(self):
        if self._register_nexon_font_files():
            return SETTINGS_FONT_FAMILY
        return "맑은 고딕"

    def _font(self, size, weight="normal"):
        return (self.font_family, size, weight)

    def _settings_font(self, size, weight="normal"):
        return (getattr(self, "settings_font_family", SETTINGS_FONT_FAMILY), size, weight)

    def _load_timer_number_font(self):
        fallback = "Segoe UI Light"
        try:
            path = resource_path(*TIMER_NUMBER_FONT_FILE)
            if path.exists():
                ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, 0)
                ctypes.windll.user32.PostMessageW(0xFFFF, 0x001D, 0, 0)
                return TIMER_NUMBER_FONT_FAMILY
        except Exception:
            pass
        return fallback

    def _timer_number_font(self, size=82):
        return (getattr(self, "timer_number_family", "Segoe UI Light"), size, "normal")

    def _warning_timer_total(self):
        return max(1.0, float(getattr(self, "warning_loop_seconds", 58.0)))

    def _warning_remaining_float(self, now=None):
        total = self._warning_timer_total()
        if getattr(self, "warning_timer_paused", False):
            return max(0.0, min(total, float(getattr(self, "warning_paused_remaining", total))))
        now = time.monotonic() if now is None else now
        return max(0.0, min(total, total - (now - float(getattr(self, "last_stall_alert_at", now)))))

    def _warning_countdown_progress(self, now=None):
        total = self._warning_timer_total()
        remaining = self._warning_remaining_float(now)
        return max(0.0, min(1.0, 1.0 - (remaining / total)))

    def _center_geometry(self, width, height):
        x, y = self._primary_monitor_center(width, height)
        return f"{width}x{height}+{x}+{y}"

    def _primary_monitor_center(self, width, height):
        try:
            sw = max(1, int(self.root.winfo_screenwidth()))
            sh = max(1, int(self.root.winfo_screenheight()))
            return (max(0, (sw - width) // 2), max(0, (sh - height) // 2))
        except Exception:
            return (80, 80)

    def _center_app_position(self, width=None, height=None, margin=24):
        width = max(1, int(width or self.app_size[0] or APP_WIDTH))
        height = max(1, int(height or self.app_size[1] or APP_HEIGHT))
        left, top, right, bottom = self._virtual_screen_bounds()
        x = left + int((max(1, right - left) - width) / 2)
        y = top + int((max(1, bottom - top) - height) / 2)
        return self._clamp_app_position((x, y), width, height, margin)

    def _virtual_screen_bounds(self):
        if sys.platform.startswith("win"):
            try:
                user32 = ctypes.windll.user32
                left = int(user32.GetSystemMetrics(76))
                top = int(user32.GetSystemMetrics(77))
                width = int(user32.GetSystemMetrics(78))
                height = int(user32.GetSystemMetrics(79))
                if width > 0 and height > 0:
                    return (left, top, left + width, top + height)
            except Exception:
                pass
        width = max(1, int(self.root.winfo_screenwidth()))
        height = max(1, int(self.root.winfo_screenheight()))
        return (0, 0, width, height)

    def _safe_app_position(self, position=None, width=None, height=None):
        width = max(1, int(width or self.app_size[0] or APP_WIDTH))
        height = max(1, int(height or self.app_size[1] or APP_HEIGHT))
        left, top, right, bottom = self._virtual_screen_bounds()
        screen_w = max(1, right - left)
        screen_h = max(1, bottom - top)
        # A stale position can point to a monitor that no longer exists (or
        # to a previous DPI/layout). Use the splash-aligned center as the
        # recovery position instead of the old bottom-left default.
        fallback = (
            left + int((screen_w - width) / 2),
            top + int((screen_h - height) / 2),
        )
        if not position or len(position) != 2:
            return self._clamp_app_position(fallback, width, height, margin=24)
        try:
            x, y = int(position[0]), int(position[1])
        except (TypeError, ValueError):
            return self._clamp_app_position(fallback, width, height, margin=24)

        visible_w = max(0, min(x + width, right) - max(x, left))
        visible_h = max(0, min(y + height, bottom) - max(y, top))
        if visible_w < min(120, width) or visible_h < min(120, height):
            return self._clamp_app_position(fallback, width, height, margin=24)
        return self._clamp_app_position((x, y), width, height)

    def _clamp_app_position(self, position, width=None, height=None, margin=12):
        width = max(1, int(width or self.app_size[0] or APP_WIDTH))
        height = max(1, int(height or self.app_size[1] or APP_HEIGHT))
        left, top, right, bottom = self._virtual_screen_bounds()
        try:
            x, y = int(position[0]), int(position[1])
        except (TypeError, ValueError, IndexError):
            return self._safe_app_position(None, width, height)

        min_x = left + margin
        min_y = top + margin
        max_x = right - width - margin
        max_y = bottom - height - margin
        if max_x < min_x:
            x = left + max(0, int((right - left - width) / 2))
        else:
            x = max(min_x, min(x, max_x))
        if max_y < min_y:
            y = top + max(0, int((bottom - top - height) / 2))
        else:
            y = max(min_y, min(y, max_y))
        return (int(x), int(y))

    def _top_left_app_position(self, width=None, height=None, margin=24):
        # Kept as a compatibility alias for older call sites. The app should
        # start/restore in the same center used by the splash screen.
        return self._center_app_position(width, height, margin)

    def _bottom_left_app_position(self, width=None, height=None, margin=24):
        width = max(1, int(width or self.app_size[0] or APP_WIDTH))
        height = max(1, int(height or self.app_size[1] or APP_HEIGHT))
        left, _top, _right, bottom = self._virtual_screen_bounds()
        return self._clamp_app_position((left + margin, bottom - height - margin), width, height, margin)

    def _main_position_from_widget(self, width, height):
        widget = getattr(self, "widget", None)
        if widget is None:
            return self._safe_app_position(self.app_position, width, height)
        try:
            widget.update_idletasks()
            widget_x = int(widget.winfo_x())
            widget_y = int(widget.winfo_y())
        except tk.TclError:
            return self._safe_app_position(self.app_position, width, height)
        x = widget_x + int((WIDGET_WIDTH - width) / 2)
        y = widget_y + int((WIDGET_HEIGHT - height) / 2)
        return self._clamp_app_position((x, y), width, height)

    def _current_safe_position(self):
        try:
            if self.root.state() == "normal":
                return self._safe_app_position((self.root.winfo_x(), self.root.winfo_y()))
        except tk.TclError:
            pass
        return self._safe_app_position(self.app_position)

    def _current_raw_position(self):
        try:
            return (int(self.root.winfo_x()), int(self.root.winfo_y()))
        except tk.TclError:
            return getattr(self, "app_position", None) or self._top_left_app_position()

    def _resize_main_window_nomove(self, width, height):
        width = max(1, int(width))
        height = max(1, int(height))
        if sys.platform.startswith("win"):
            try:
                self.root.update_idletasks()
                user32 = ctypes.windll.user32
                hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
                swp_nomove = 0x0002
                swp_nozorder = 0x0004
                swp_noactivate = 0x0010
                user32.SetWindowPos(hwnd, 0, 0, 0, width, height, swp_nomove | swp_nozorder | swp_noactivate)
                return
            except Exception:
                pass
        try:
            self.root.geometry(f"{width}x{height}")
        except tk.TclError:
            pass

    def _refresh_resize_surface(self):
        try:
            self.root.update_idletasks()
            width = max(1, int(self.root.winfo_width()))
            height = max(1, int(self.root.winfo_height()))
            if hasattr(self, "backdrop"):
                self._draw_backdrop()
            if getattr(self, "current_page", None) == "monitor":
                self._layout_monitor_page()
            elif getattr(self, "current_page", None) == "settings":
                self._layout_settings_page()
            self._apply_rounded_window(self.root, width, height, max(28, int(42 * self._monitor_scale())))
        except tk.TclError:
            pass

    def _quit_app(self):
        self.shutting_down = True
        self.widget_mode_active = False
        after_id = getattr(self, "timer_display_after_id", None)
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except Exception:
                pass
            self.timer_display_after_id = None
        try:
            self._save_settings()
        except Exception:
            pass
        try:
            self._release_capture_camera()
        except Exception:
            pass
        for name in ("widget", "splash", "restore_blur_overlay", "drag_proxy", "disclaimer_dialog"):
            window = getattr(self, name, None)
            if window is not None:
                try:
                    window.destroy()
                except Exception:
                    pass
        try:
            self.root.quit()
            self.root.destroy()
        except Exception:
            pass
        try:
            os._exit(0)
        except Exception:
            pass

    def _apply_window_icon(self, window):
        icon_path = getattr(self, "icon_path", None)
        if not icon_path or not Path(icon_path).exists():
            return
        try:
            window.iconbitmap(default=str(icon_path))
        except tk.TclError:
            pass
        try:
            if getattr(self, "app_icon_photo", None) is None:
                icon_image = Image.open(icon_path).convert("RGBA")
                icon_image.thumbnail((256, 256), Image.Resampling.LANCZOS)
                self.app_icon_photo = ImageTk.PhotoImage(icon_image)
            window.iconphoto(True, self.app_icon_photo)
        except Exception:
            pass

    def _apply_taskbar_window_style(self, window=None):
        if not sys.platform.startswith("win"):
            return
        try:
            window = window or self.root
            window.update_idletasks()
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
            gwl_exstyle = -20
            ws_ex_toolwindow = 0x00000080
            ws_ex_appwindow = 0x00040000
            swp_nosize = 0x0001
            swp_nomove = 0x0002
            swp_nozorder = 0x0004
            swp_framechanged = 0x0020
            swp_showwindow = 0x0040
            try:
                current = user32.GetWindowLongPtrW(hwnd, gwl_exstyle)
                user32.SetWindowLongPtrW(hwnd, gwl_exstyle, (current & ~ws_ex_toolwindow) | ws_ex_appwindow)
            except AttributeError:
                current = user32.GetWindowLongW(hwnd, gwl_exstyle)
                user32.SetWindowLongW(hwnd, gwl_exstyle, (current & ~ws_ex_toolwindow) | ws_ex_appwindow)
            user32.SetWindowPos(
                hwnd,
                0,
                0,
                0,
                0,
                0,
                swp_nomove | swp_nosize | swp_nozorder | swp_framechanged | swp_showwindow,
            )
        except Exception:
            pass

    def _apply_main_window_chrome(self):
        if not sys.platform.startswith("win"):
            return
        try:
            self.root.overrideredirect(False)
            self.root.update_idletasks()
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            gwl_style = -16
            ws_caption = 0x00C00000
            ws_thickframe = 0x00040000
            ws_maximizebox = 0x00010000
            ws_sysmenu = 0x00080000
            ws_minimizebox = 0x00020000
            swp_nosize = 0x0001
            swp_nomove = 0x0002
            swp_nozorder = 0x0004
            swp_framechanged = 0x0020
            try:
                style = user32.GetWindowLongPtrW(hwnd, gwl_style)
                style = (style & ~(ws_caption | ws_thickframe | ws_maximizebox)) | ws_sysmenu | ws_minimizebox
                user32.SetWindowLongPtrW(hwnd, gwl_style, style)
            except AttributeError:
                style = user32.GetWindowLongW(hwnd, gwl_style)
                style = (style & ~(ws_caption | ws_thickframe | ws_maximizebox)) | ws_sysmenu | ws_minimizebox
                user32.SetWindowLongW(hwnd, gwl_style, style)
            user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, swp_nomove | swp_nosize | swp_nozorder | swp_framechanged)
        except Exception:
            pass
        self._refresh_windows_taskbar_identity()

    def _refresh_windows_taskbar_identity(self):
        self._apply_window_icon(self.root)
        self._apply_taskbar_window_style(self.root)

    def _schedule_surface_refresh(self, delay=30):
        if getattr(self, "shutting_down", False):
            return
        if getattr(self, "widget_mode_active", False):
            self._hide_main_for_widget_mode()
            return
        after_id = getattr(self, "surface_refresh_after_id", None)
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        try:
            self.surface_refresh_after_id = self.root.after(delay, self._refresh_window_surface)
        except tk.TclError:
            self.surface_refresh_after_id = None

    def _cancel_surface_refresh(self):
        after_id = getattr(self, "surface_refresh_after_id", None)
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self.surface_refresh_after_id = None

    def _hide_main_for_widget_mode(self):
        if not getattr(self, "widget_mode_active", False):
            return
        self._cancel_surface_refresh()
        try:
            self.root.withdraw()
            self.root.update_idletasks()
            self.root.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        widget = getattr(self, "widget", None)
        if widget is not None:
            try:
                if widget.winfo_exists():
                    widget.deiconify()
                    widget.attributes("-alpha", 1.0)
                    widget.attributes("-topmost", True)
                    widget.lift()
            except tk.TclError:
                pass

    def _refresh_window_surface(self):
        self.surface_refresh_after_id = None
        if getattr(self, "shutting_down", False):
            return
        if getattr(self, "dragging_main_window", False):
            return
        if getattr(self, "resizing_main_window", False):
            return
        if getattr(self, "widget_mode_active", False):
            self._hide_main_for_widget_mode()
            return
        try:
            self.root.update_idletasks()
            width = max(1, int(self.root.winfo_width()))
            height = max(1, int(self.root.winfo_height()))
            if hasattr(self, "backdrop"):
                self._draw_backdrop()
            if getattr(self, "current_page", None) == "monitor":
                self._layout_monitor_page()
            self._apply_main_window_chrome()
            self._apply_rounded_window(self.root, width, height, max(28, int(42 * self._monitor_scale())))
            self.root.update_idletasks()
        except tk.TclError:
            pass

    def _move_main_window(self, x, y):
        x, y = int(x), int(y)
        self.app_position = (x, y)
        try:
            self.root.geometry(f"+{x}+{y}")
        except tk.TclError:
            return

    def _show_main_window(self, alpha=None, force_focus=False):
        if getattr(self, "widget_mode_active", False):
            self._hide_main_for_widget_mode()
            return
        width, height = nearest_app_size(
            getattr(self, "app_size", DEFAULT_APP_SIZE)[0],
            getattr(self, "app_size", DEFAULT_APP_SIZE)[1],
        )
        self.app_size = (width, height)
        self.app_position = self._safe_app_position(self.app_position, width, height)
        x, y = self.app_position
        try:
            self.root.attributes("-alpha", 1.0 if alpha is None else alpha)
            self.root.overrideredirect(False)
            self.root.deiconify()
            try:
                self.root.state("normal")
            except tk.TclError:
                pass
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self._apply_main_window_chrome()
            self._schedule_surface_refresh(80)
            self.root.attributes("-topmost", False)
            self.root.attributes("-topmost", True)
            self.root.lift()
            if force_focus:
                self.root.focus_force()
            self.root.update_idletasks()
            self.root.after(250, self._refresh_windows_taskbar_identity)
        except tk.TclError:
            pass

    def _force_main_window_visible(self, force_focus=False, attempts=2):
        if getattr(self, "widget_mode_active", False):
            self._hide_main_for_widget_mode()
            return
        width, height = nearest_app_size(
            getattr(self, "app_size", DEFAULT_APP_SIZE)[0],
            getattr(self, "app_size", DEFAULT_APP_SIZE)[1],
        )
        self.app_size = (width, height)
        # The splash is centered using the virtual desktop bounds. Start the
        # main window from that same center so every monitor layout, taskbar
        # position, and resolution follows one coordinate system.
        self.app_position = self._center_app_position(width, height)
        x, y = self.app_position
        try:
            self.root.attributes("-alpha", 1.0)
            self.root.overrideredirect(False)
            self.root.deiconify()
            try:
                self.root.state("normal")
            except tk.TclError:
                pass
            self.root.geometry(f"{width}x{height}+{x}+{y}")
            self.root.update_idletasks()
            self._apply_main_window_chrome()
            self._schedule_surface_refresh(80)
            self._force_windows_topmost(self.root, x, y, width, height, force_focus=force_focus)
            self.root.attributes("-topmost", False)
            self.root.attributes("-topmost", True)
            self.root.lift()
            if force_focus:
                self.root.focus_force()
            self._apply_main_window_chrome()
            self.root.update_idletasks()
            self.root.after(250, self._refresh_windows_taskbar_identity)
        except tk.TclError:
            pass
    def _force_windows_topmost(self, window, x, y, width, height, force_focus=False):
        if not sys.platform.startswith("win"):
            return
        try:
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(window.winfo_id()) or window.winfo_id()
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            flags = 0x0040  # SWP_SHOWWINDOW
            if not force_focus:
                flags |= 0x0010  # SWP_NOACTIVATE
            user32.SetWindowPos(hwnd, -1, int(x), int(y), int(width), int(height), flags)
            if force_focus:
                user32.SetForegroundWindow(hwnd)
        except Exception:
            pass

    def _keep_visible_tick(self):
        if getattr(self, "shutting_down", False):
            return
        try:
            widget = getattr(self, "widget", None)
            if getattr(self, "widget_mode_active", False) and widget is not None and widget.winfo_exists():
                self._hide_main_for_widget_mode()
                widget.attributes("-topmost", True)
            elif self.root.state() == "normal" and self.root.winfo_viewable():
                self.root.attributes("-topmost", True)
        except tk.TclError:
            pass
        try:
            self.root.after(5000, self._keep_visible_tick)
        except tk.TclError:
            pass

    def _apply_rounded_window(self, window, width, height, radius=34):
        if not sys.platform.startswith("win"):
            return
        try:
            window.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
            region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, width + 1, height + 1, radius, radius)
            ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
        except Exception:
            pass

    def _show_startup_splash(self, on_done=None):
        self.startup_splash_done_callback = on_done
        width, height = SPLASH_WIDTH, SPLASH_HEIGHT
        with Image.open(resource_path("assets", "runetimer_splash.png")) as source:
            artwork = source.convert("RGBA")
        # Trim the generated asset's transparent padding for a compact window.
        bounds = (300, 234, 1011, 966)  # Solid card bounds; exclude generated edge specks.
        if bounds:
            artwork = artwork.crop(bounds)
        # Render the credit from the bundled official font, never generated lettering.
        credit_font = ImageFont.truetype(str(resource_path("assets", "fonts", "maplestory", "Maplestory Bold.ttf")), 50)
        ImageDraw.Draw(artwork).text((artwork.width / 2, 650), "by 꼬맹협회",
                                   font=credit_font, fill="#176B5B", anchor="mm")
        artwork = artwork.resize((width, height), Image.Resampling.LANCZOS)
        artwork.putalpha(artwork.getchannel("A").point(lambda a: 255 if a >= 128 else 0))
        self.splash = tk.Toplevel(self.root)
        self.splash.overrideredirect(True)
        self.splash.attributes("-topmost", True)
        self.splash.configure(bg=TRANSPARENT)
        self.splash.wm_attributes("-transparentcolor", TRANSPARENT)
        self.splash.geometry(self._center_geometry(width, height))
        self.splash_canvas = tk.Canvas(self.splash, width=width, height=height,
                                      bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.splash_canvas.pack(fill="both", expand=True)
        self.splash_logo_image = ImageTk.PhotoImage(artwork)
        self.splash_image_item = self.splash_canvas.create_image(0, 0, anchor="nw", image=self.splash_logo_image)
        self.root.after(2000, lambda: self._fade_startup_splash(0.92))

    def _finish_startup_splash(self):
        callback = getattr(self, "startup_splash_done_callback", None)
        self.startup_splash_done_callback = None
        if callback:
            callback()
        else:
            self._start_main_app()

    def _get_splash_font(self, size, bold=False):
        font_dir = resource_path("assets", "fonts", "package", "src")
        font_names = (
            ("NEXON_Lv2_Gothic_Bold.ttf", "NEXON_Lv2_Gothic_Medium.ttf", "NEXON_Lv2_Gothic.ttf")
            if bold
            else ("NEXON_Lv2_Gothic_Medium.ttf", "NEXON_Lv2_Gothic_Bold.ttf", "NEXON_Lv2_Gothic.ttf")
        )
        for name in font_names:
            try:
                path = font_dir / name
                if path.exists():
                    return ImageFont.truetype(str(path), size)
            except Exception:
                continue
        fallback_names = ("segoeuib.ttf", "malgunbd.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "malgun.ttf", "arial.ttf")
        for name in fallback_names:
            try:
                return ImageFont.truetype(name, size)
            except Exception:
                continue
        return ImageFont.load_default()

    def _make_powered_by_image(self):
        scale = 3
        powered_font = self._get_splash_font(31 * scale)
        brand_font = self._get_splash_font(31 * scale, bold=True)
        powered = "powered by"
        brand = "nilbox"
        probe = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(probe)
        powered_box = draw.textbbox((0, 0), powered, font=powered_font)
        brand_box = draw.textbbox((0, 0), brand, font=brand_font)
        powered_w = powered_box[2] - powered_box[0]
        brand_w = brand_box[2] - brand_box[0]
        text_h = max(powered_box[3] - powered_box[1], brand_box[3] - brand_box[1])
        padding = 7 * scale
        gap = 9 * scale
        image = Image.new("RGBA", (powered_w + gap + brand_w + padding * 2, text_h + padding * 2), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        y = padding - min(powered_box[1], brand_box[1])
        draw.text((padding, y), powered, font=powered_font, fill=(255, 255, 255, 244))

        mask = Image.new("L", (brand_w + 6 * scale, text_h + padding * 2), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.text((0, y), brand, font=brand_font, fill=255)
        gradient = Image.new("RGBA", mask.size, (0, 0, 0, 0))
        grad_pixels = gradient.load()
        start = (79, 244, 180)
        middle = (38, 224, 220)
        end = (83, 198, 244)
        denom = max(1, gradient.size[0] - 1)
        for x in range(gradient.size[0]):
            t = x / denom
            if t < 0.58:
                local = t / 0.58
                color_rgb = tuple(int(start[i] * (1 - local) + middle[i] * local) for i in range(3))
            else:
                local = (t - 0.58) / 0.42
                color_rgb = tuple(int(middle[i] * (1 - local) + end[i] * local) for i in range(3))
            for yy in range(gradient.size[1]):
                shine = 1.0 + max(0.0, 1.0 - abs((yy / max(1, gradient.size[1] - 1)) - 0.36) / 0.36) * 0.08
                grad_pixels[x, yy] = tuple(min(255, int(channel * shine)) for channel in color_rgb) + (255,)
        gradient.putalpha(mask)
        image.alpha_composite(gradient, (padding + powered_w + gap, 0))
        output_size = (ui_px(image.width // scale), ui_px(image.height // scale))
        return image.resize(output_size, Image.Resampling.LANCZOS)

    def _gradient_color(self, start, end, t):
        t = max(0.0, min(1.0, float(t)))
        return tuple(int(start[i] * (1.0 - t) + end[i] * t) for i in range(3))

    def _point_on_polyline(self, points, distance):
        if not points:
            return 0, 0
        remaining = max(0.0, float(distance))
        for index in range(len(points) - 1):
            x1, y1 = points[index]
            x2, y2 = points[index + 1]
            length = math.hypot(x2 - x1, y2 - y1)
            if length <= 0:
                continue
            if remaining <= length:
                t = remaining / length
                return x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            remaining -= length
        return points[-1]

    def _make_splash_logo_frame(self, progress, blurred=False):
        size = ui_px(190)
        logo_size = ui_px(142)
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

        try:
            logo = Image.open(resource_path("nilbox_splash_icon.png")).convert("RGBA")
            logo.thumbnail((logo_size, logo_size), Image.Resampling.LANCZOS)
            logo_x = int((size - logo.width) / 2)
            logo_y = int((size - logo.height) / 2)
            image.alpha_composite(logo, (logo_x, logo_y))
        except Exception:
            pass

        if blurred:
            image = image.filter(ImageFilter.GaussianBlur(4))
        return image

    def _make_spinner_frames(self):
        frames = []
        size = 62
        center = size / 2
        radius = 18
        for frame_index in range(12):
            image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
            draw = ImageDraw.Draw(image)
            for step in range(12):
                age = (step - frame_index) % 12
                alpha = int(42 + (11 - age) * 17)
                angle = (step / 12.0) * math.tau
                inner = radius * 0.58
                outer = radius
                x1 = center + math.cos(angle) * inner
                y1 = center + math.sin(angle) * inner
                x2 = center + math.cos(angle) * outer
                y2 = center + math.sin(angle) * outer
                draw.line((x1, y1, x2, y2), fill=(255, 255, 255, alpha), width=6)
            frames.append(image.filter(ImageFilter.GaussianBlur(0.15)))
        return frames

    def _animate_startup_spinner(self, elapsed_ms):
        if not hasattr(self, "splash_canvas") or not hasattr(self, "splash_spinner_frames"):
            return
        if elapsed_ms >= 2000:
            self._blur_startup_splash()
            return
        self.splash_spinner_index = (self.splash_spinner_index + 1) % len(self.splash_spinner_frames)
        self.splash_canvas.itemconfigure(self.splash_spinner_item, image=self.splash_spinner_frames[self.splash_spinner_index])
        self.root.after(75, lambda: self._animate_startup_spinner(elapsed_ms + 75))

    def _blur_startup_splash(self):
        if not hasattr(self, "splash_canvas"):
            self._finish_startup_splash()
            return
        blur_image = getattr(self, "splash_logo_blur", None)
        if blur_image is not None:
            self.splash_canvas.itemconfigure(self.splash_image_item, image=blur_image)
        if hasattr(self, "splash_spinner_item"):
            self.splash_canvas.itemconfigure(self.splash_spinner_item, state="hidden")
        self._fade_startup_splash(0.92)

    def _fade_startup_splash(self, alpha):
        if not hasattr(self, "splash") or not self.splash.winfo_exists():
            self._finish_startup_splash()
            return
        if alpha <= 0.08:
            self.splash.destroy()
            self._finish_startup_splash()
            return
        try:
            self.splash.attributes("-alpha", alpha)
        except tk.TclError:
            pass
        self.root.after(45, lambda: self._fade_startup_splash(alpha - 0.10))

    def _disclaimer_acceptance_required(self):
        return not (
            bool(getattr(self, "disclaimer_accepted", False))
            and int(getattr(self, "disclaimer_version", 0) or 0) == DISCLAIMER_VERSION
        )

    def _accept_startup_disclaimer(self):
        self.disclaimer_accepted = True
        self.disclaimer_accepted_at = datetime.now().isoformat(timespec="seconds")
        self.disclaimer_version = DISCLAIMER_VERSION
        self.center_first_launch_after_disclaimer = not bool(getattr(self, "first_launch_centered_done", False))
        self._save_settings()
        self._show_startup_splash(on_done=self._start_main_app_after_disclaimer)

    def _show_disclaimer_label(self, parent, text, fg, font, **pack_options):
        label = tk.Label(
            parent,
            text=text,
            bg=parent.cget("bg"),
            fg=fg,
            font=font,
            justify="left",
            anchor="w",
            wraplength=510,
        )
        label.pack(**pack_options)
        return label

    def _show_disclaimer_dialog(self, readonly=False, on_accept=None, on_close=None):
        existing = getattr(self, "disclaimer_dialog", None)
        try:
            if existing is not None and existing.winfo_exists():
                self._raise_disclaimer_dialog(existing)
                return
        except tk.TclError:
            pass

        c = self.colors
        screen_left, screen_top, screen_right, screen_bottom = self._virtual_screen_bounds()
        screen_w = max(1, screen_right - screen_left)
        screen_h = max(1, screen_bottom - screen_top)
        width = min(720 if LOW_RES else 1120, max(480, screen_w - 40))
        height = min(700 if LOW_RES else 1240, max(480, screen_h - 70))
        dialog = tk.Toplevel(self.root)
        self.disclaimer_dialog = dialog
        dialog.title(DISCLAIMER_TITLE)
        dialog.geometry(self._center_geometry(width, height))
        dialog.resizable(False, False)
        dialog.overrideredirect(True)
        dialog.configure(bg=TRANSPARENT)
        try:
            dialog.wm_attributes("-transparentcolor", TRANSPARENT)
        except tk.TclError:
            pass
        dialog.attributes("-topmost", True)
        self._apply_window_icon(dialog)
        try:
            if readonly or getattr(self, "main_app_started", False):
                dialog.transient(self.root)
        except tk.TclError:
            pass

        def clear_dialog():
            try:
                dialog.grab_release()
            except tk.TclError:
                pass
            self.disclaimer_dialog = None
            try:
                dialog.destroy()
            except tk.TclError:
                pass

        def handle_close():
            clear_dialog()
            if on_close:
                on_close()

        def handle_accept():
            clear_dialog()
            if on_accept:
                on_accept()

        shell = tk.Canvas(dialog, width=width, height=height, bg=TRANSPARENT, highlightthickness=0, bd=0)
        shell.pack(fill="both", expand=True)
        outer_radius = max(54, min(82, int(min(width, height) * 0.08)))
        self._canvas_rounded_rect(shell, 16, 18, width - 12, height - 8, outer_radius, fill="#000000", outline="")
        self._canvas_rounded_rect(
            shell,
            8,
            8,
            width - 14,
            height - 14,
            outer_radius,
            fill=c["surface"],
            outline="#182020",
            width=1,
        )

        container = tk.Frame(shell, bg=c["surface"], padx=0, pady=0)
        shell.create_window(18, 18, anchor="nw", window=container, width=width - 40, height=height - 40)

        drag_state = {"x": 0, "y": 0}

        def start_drag(event):
            drag_state["x"] = event.x_root - dialog.winfo_x()
            drag_state["y"] = event.y_root - dialog.winfo_y()

        def drag_dialog(event):
            dialog.geometry(f"+{event.x_root - drag_state['x']}+{event.y_root - drag_state['y']}")

        inner_width = width - 40
        hero_height = max(132, int((height - 40) * 0.14))
        hero = tk.Frame(container, bg="#0b1111", height=hero_height, padx=52, pady=22)
        hero.pack(fill="x")
        hero.pack_propagate(False)
        hero.bind("<ButtonPress-1>", start_drag)
        hero.bind("<B1-Motion>", drag_dialog)
        hero_inner = tk.Frame(hero, bg="#0b1111")
        hero_inner.place(relx=0.5, rely=0.5, anchor="center")
        tk.Label(
            hero_inner,
            text=DISCLAIMER_TITLE,
            bg="#0b1111",
            fg=c["text"],
            font=self._settings_font(26, "bold"),
            justify="center",
            anchor="center",
            wraplength=inner_width - 160,
        ).pack(anchor="center")

        body = tk.Frame(container, bg=c["surface"], padx=46, pady=30)
        body.pack(fill="both", expand=True)

        scroll_row = tk.Frame(body, bg=c["surface"])
        scroll_row.pack(fill="both", expand=True)

        scroll_canvas = tk.Canvas(scroll_row, bg=c["surface"], highlightthickness=0, bd=0)
        scroll_canvas.pack(side="left", fill="both", expand=True)
        scroll_indicator = tk.Canvas(scroll_row, width=6, bg=c["surface"], highlightthickness=0, bd=0)
        scroll_indicator.pack(side="right", fill="y", padx=(12, 0))

        content = tk.Frame(scroll_canvas, bg=c["surface"], padx=34, pady=28, highlightthickness=1, highlightbackground=c["line"])
        content_window = scroll_canvas.create_window(0, 0, anchor="nw", window=content)

        def draw_scroll_indicator():
            try:
                scroll_indicator.delete("all")
                visible_h = max(1, int(scroll_canvas.winfo_height()))
                total_h = max(visible_h, int(content.winfo_reqheight()))
                track_h = max(1, int(scroll_indicator.winfo_height()))
                if total_h <= visible_h + 2:
                    return
                top_ratio, bottom_ratio = scroll_canvas.yview()
                thumb_h = max(44, int(track_h * max(0.12, visible_h / total_h)))
                thumb_y = int(top_ratio * max(1, track_h - thumb_h))
                self._canvas_rounded_rect(scroll_indicator, 2, 0, 5, track_h, 2, fill="#151a1a", outline="")
                self._canvas_rounded_rect(scroll_indicator, 1, thumb_y, 6, thumb_y + thumb_h, 3, fill=c["line_strong"], outline="")
            except tk.TclError:
                pass

        def refresh_scroll_region(_event=None):
            try:
                scroll_canvas.configure(scrollregion=scroll_canvas.bbox("all"))
                draw_scroll_indicator()
            except tk.TclError:
                pass

        def resize_scroll_content(event):
            try:
                scroll_canvas.itemconfigure(content_window, width=max(1, event.width))
                refresh_scroll_region()
            except tk.TclError:
                pass

        def scroll_disclaimer(event):
            try:
                delta = -1 if event.delta > 0 else 1
                scroll_canvas.yview_scroll(delta * 3, "units")
                draw_scroll_indicator()
            except tk.TclError:
                pass
            return "break"

        scroll_canvas.bind("<Configure>", resize_scroll_content)
        content.bind("<Configure>", refresh_scroll_region)
        dialog.bind("<MouseWheel>", scroll_disclaimer)

        max_text_width = max(520, inner_width - 150)
        terms_panel = tk.Frame(content, bg=c["panel"], padx=24, pady=24, highlightthickness=1, highlightbackground=c["line"])
        terms_panel.pack(fill="x", pady=(0, 22))
        for index, paragraph in enumerate(DISCLAIMER_TERMS_PARAGRAPHS):
            tk.Label(
                terms_panel,
                text=paragraph,
                bg=c["panel"],
                fg=c["text"] if index == 0 else c["muted"],
                font=self._settings_font(10 if index == 0 else 9, "bold" if index == 0 else "normal"),
                justify="left",
                anchor="w",
                wraplength=max_text_width,
            ).pack(fill="x", anchor="w", pady=(0, 18 if index < len(DISCLAIMER_TERMS_PARAGRAPHS) - 1 else 0))

        action_area = tk.Frame(body, bg=c["surface"], padx=34, pady=0)
        action_area.pack(fill="x", pady=(22, 0))

        confirm = tk.Frame(action_area, bg=c["panel"], padx=20, pady=15, highlightthickness=1, highlightbackground=c["line"])
        confirm.pack(fill="x", anchor="w", pady=(0, 24))
        tk.Label(
            confirm,
            text=DISCLAIMER_CONFIRM_TEXT,
            bg=c["panel"],
            fg=c["text"] if not readonly else c["muted"],
            font=self._settings_font(9, "bold"),
            justify="center",
            anchor="center",
            wraplength=max_text_width,
        ).pack(fill="x", anchor="center")

        if readonly:
            RoundedButton(
                action_area,
                "닫기",
                clear_dialog,
                width=104,
                height=46,
                radius=21,
                bg=c["blue"],
                fg=c["surface"],
                hover=c["blue_hover"],
                font=self._settings_font(11, "bold"),
            ).pack(anchor="center", pady=(0, 34))
        else:
            RoundedButton(
                action_area,
                "동의",
                handle_accept,
                width=244,
                height=50,
                radius=22,
                bg=c["blue"],
                fg=c["surface"],
                hover=c["blue_hover"],
                font=self._settings_font(11, "bold"),
            ).pack(anchor="center", pady=(0, 12))
            RoundedButton(
                action_area,
                "동의하지 않음",
                handle_close,
                width=244,
                height=50,
                radius=22,
                bg="#1b2020",
                hover="#252b2b",
                fg=c["text"],
                font=self._settings_font(10, "bold"),
                outline="#5f6969",
            ).pack(anchor="center", pady=(0, 34))

        close_action = clear_dialog if readonly else handle_close
        close_button = tk.Label(
            hero,
            text="×",
            bg="#0b1111",
            fg=c["text"],
            activebackground="#0b1111",
            activeforeground=c["text"],
            font=self._settings_font(16, "bold"),
            cursor="hand2",
            padx=8,
            pady=2,
        )
        close_button.place(relx=1.0, x=-18, rely=0.5, anchor="e")
        close_button.bind("<Button-1>", lambda _event: close_action())
        close_button.lift()

        dialog.protocol("WM_DELETE_WINDOW", clear_dialog if readonly else handle_close)
        self._raise_disclaimer_dialog(dialog, width, height)
        for delay in (120, 450, 1000):
            try:
                self.root.after(delay, lambda window=dialog, w=width, h=height: self._raise_disclaimer_dialog(window, w, h))
            except tk.TclError:
                break

    def _raise_disclaimer_dialog(self, dialog, width=None, height=None):
        try:
            if dialog is None or not dialog.winfo_exists():
                return
            dialog.deiconify()
            dialog.attributes("-topmost", True)
            dialog.lift()
            dialog.update_idletasks()
            width = int(width or dialog.winfo_width())
            height = int(height or dialog.winfo_height())
            self._apply_rounded_window(dialog, width, height, max(54, min(82, int(min(width, height) * 0.08))))
            x = int(dialog.winfo_x())
            y = int(dialog.winfo_y())
            self._force_windows_topmost(dialog, x, y, width, height, force_focus=True)
            dialog.lift()
            dialog.focus_force()
            try:
                dialog.grab_set()
            except tk.TclError:
                pass
        except tk.TclError:
            pass

    def _start_main_app(self):
        if getattr(self, "main_app_started", False):
            return
        if self._disclaimer_acceptance_required():
            try:
                self.root.geometry("1x1+-10000+-10000")
                self.root.deiconify()
                self.root.attributes("-alpha", 0.0)
                self.root.update_idletasks()
                self._show_disclaimer_dialog(
                    readonly=False,
                    on_accept=self._accept_startup_disclaimer,
                    on_close=self._quit_app,
                )
            except Exception as exc:
                log_error("startup_disclaimer_dialog", exc)
                try:
                    messagebox.showerror(APP_NAME, "이용 안내 창을 표시하지 못했습니다.\n앱을 다시 실행해 주세요.")
                finally:
                    self._quit_app()
            return
        self._start_main_app_after_disclaimer()

    def _start_main_app_after_disclaimer(self):
        if getattr(self, "main_app_started", False):
            return
        self.main_app_started = True
        if getattr(self, "center_first_launch_after_disclaimer", False):
            width, height = nearest_app_size(
                getattr(self, "app_size", DEFAULT_APP_SIZE)[0],
                getattr(self, "app_size", DEFAULT_APP_SIZE)[1],
            )
            self.app_size = (width, height)
            self.app_position = self._center_app_position(width, height)
            self.center_first_launch_after_disclaimer = False
            self.first_launch_centered_done = True
            self._save_settings()
        self._show_main_window(force_focus=True)
        self.root.after(100, self._process_worker_results)
        if not getattr(self, "keep_visible_tick_started", False):
            self.keep_visible_tick_started = True
            self.root.after(600, self._keep_visible_tick)
        self.root.after(900, self._ensure_widget_window)
        self._timer_display_tick()
        self._monitor_tick()

    def _timer_display_tick(self):
        self.timer_display_after_id = None
        if getattr(self, "shutting_down", False):
            return
        try:
            self._render_timer_display_only()
            self.timer_display_after_id = self.root.after(
                self.timer_display_interval_ms,
                self._timer_display_tick,
            )
        except tk.TclError:
            self.timer_display_after_id = None

    def _render_timer_display_only(self):
        now = time.monotonic()
        self._offline_rune_tick(now)
        self._update_countdown_display_lightweight(now)
        self._update_widget_timer_display_lightweight(now)

    def _default_timers(self):
        return [TimerItem("야누스/설치기",60,True), TimerItem("룬 쿨타임",900,True), TimerItem("재획비",7200,False), TimerItem("유니온/쿠폰",1800,False), TimerItem("부스터 종료",90,False)]

    def _load_settings(self):
        data = {}
        source = SETTINGS_PATH
        importing_legacy = LOW_RES and not source.exists()
        if importing_legacy:
            source = APP_DIR / "settings.json"
        if source.exists():
            try:
                data = json.loads(source.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                data = {}
        if importing_legacy:
            # Preserve existing feature preferences without importing a large window.
            for key in ("app_size", "app_position", "widget_position"):
                data.pop(key, None)
        self.session_seconds = clamp_int(data.get("session_seconds"), DEFAULT_SESSION_SECONDS, 60, MAX_INTERVAL)
        self.region = tuple(data["region"]) if isinstance(data.get("region"), list) and len(data["region"]) == 4 else None
        self.rune_region = tuple(data["rune_region"]) if isinstance(data.get("rune_region"), list) and len(data["rune_region"]) == 4 else None
        self.rune_window_anchor = self._load_rune_window_anchor(data.get("rune_window_anchor"))
        self.app_position = tuple(data["app_position"]) if isinstance(data.get("app_position"), list) and len(data["app_position"]) == 2 else None
        self.widget_position = tuple(data["widget_position"]) if isinstance(data.get("widget_position"), list) and len(data["widget_position"]) == 2 else None
        if isinstance(data.get("app_size"), list) and len(data["app_size"]) == 2:
            self.app_size = nearest_app_size(data["app_size"][0], data["app_size"][1])
        self.monitor_enabled = bool(data.get("monitor_enabled", bool(self.region)))
        self.auto_detect_enabled = False
        self.monitor_threshold = float(data.get("monitor_threshold", self.monitor_threshold))
        stored_blue_threshold = clamp_float(data.get("blue_damage_threshold"), self.blue_damage_threshold, 0.01, 5.0)
        if stored_blue_threshold >= 0.3:
            stored_blue_threshold = self.blue_damage_threshold
        self.blue_damage_threshold = stored_blue_threshold
        stored_rune_threshold = clamp_float(data.get("rune_threshold"), self.rune_threshold, 0.01, 100.0)
        if stored_rune_threshold < 5.0:
            stored_rune_threshold = self.rune_threshold
        self.rune_threshold = stored_rune_threshold
        self.blue_activity_max = 100.0
        self.monitor_stall_seconds = clamp_float(data.get("monitor_stall_seconds"), self.monitor_stall_seconds, 3.0, 600.0)
        self.warning_loop_seconds = clamp_float(data.get("warning_loop_seconds"), self.warning_loop_seconds, 10.0, 600.0)
        self.warning_sound_enabled = clamp_bool(data.get("warning_sound_enabled"), self.warning_sound_enabled)
        self.rune_sound_enabled = clamp_bool(data.get("rune_sound_enabled"), self.rune_sound_enabled)
        self.booster_mode_enabled = clamp_bool(data.get("booster_mode_enabled"), self.booster_mode_enabled)
        self.booster_use_count = normalize_booster_use_count(data.get("booster_use_count"))
        self.halfhour_enabled = clamp_bool(data.get("halfhour_enabled"), False)
        self.tts_sound_enabled = clamp_bool(data.get("tts_sound_enabled"), self.tts_sound_enabled)
        self.offline_mode_enabled = clamp_bool(data.get("offline_mode_enabled"), self.offline_mode_enabled)
        self.warning_volume = int(clamp_float(data.get("warning_volume"), self.warning_volume, 0.0, 100.0))
        self.rune_volume = int(clamp_float(data.get("rune_volume"), self.rune_volume, 0.0, 100.0))
        self.halfhour_volume = int(clamp_float(data.get("halfhour_volume"), 100, 0.0, 100.0))
        self.rune_cooldown_minutes = normalize_rune_cooldown_minutes(data.get("rune_cooldown_minutes"), self.rune_cooldown_minutes)
        self.disclaimer_accepted = clamp_bool(data.get("disclaimer_accepted"), False)
        self.disclaimer_accepted_at = data.get("disclaimer_accepted_at") if isinstance(data.get("disclaimer_accepted_at"), str) else None
        try:
            self.disclaimer_version = int(data.get("disclaimer_version") or 0)
        except (TypeError, ValueError):
            self.disclaimer_version = 0
        self.first_launch_centered_done = clamp_bool(
            data.get("first_launch_centered_done"),
            bool(self.disclaimer_accepted),
        )
        self.last_rune_cleared_wall = data.get("last_rune_cleared_wall")
        try:
            self.last_rune_cleared_wall = float(self.last_rune_cleared_wall)
        except (TypeError, ValueError):
            self.last_rune_cleared_wall = None
        if self.last_rune_cleared_wall:
            elapsed = max(0.0, time.time() - self.last_rune_cleared_wall)
            self.last_rune_cleared_at = time.monotonic() - elapsed
        raw = data.get("timers")
        self.timers = [TimerItem.from_dict(x) for x in raw] if isinstance(raw, list) and raw else self._default_timers()
        for timer in self.timers:
            timer.reset()

    def _save_settings(self):
        data = {
            "region": list(self.region) if self.region else None,
            "rune_region": list(self.rune_region) if self.rune_region else None,
            "rune_window_anchor": self.rune_window_anchor,
            "app_position": list(self.app_position) if self.app_position else None,
            "widget_position": list(self.widget_position) if self.widget_position else None,
            "app_size": list(self.app_size) if self.app_size else None,
            "monitor_enabled": True,
            "monitor_threshold": self.monitor_threshold,
            "blue_damage_threshold": self.blue_damage_threshold,
            "rune_threshold": self.rune_threshold,
            "monitor_stall_seconds": self.monitor_stall_seconds,
            "warning_loop_seconds": self.warning_loop_seconds,
            "warning_sound_enabled": self.warning_sound_enabled,
            "rune_sound_enabled": self.rune_sound_enabled,
            "booster_mode_enabled": self.booster_mode_enabled,
            "booster_use_count": normalize_booster_use_count(getattr(self, "booster_use_count", 3)),
            "halfhour_enabled": getattr(self, "halfhour_enabled", False),
            "tts_sound_enabled": self.tts_sound_enabled,
            "offline_mode_enabled": self.offline_mode_enabled,
            "warning_volume": self.warning_volume,
            "rune_volume": self.rune_volume,
            "halfhour_volume": self.halfhour_volume,
            "rune_cooldown_minutes": self.rune_cooldown_minutes,
            "disclaimer_accepted": bool(getattr(self, "disclaimer_accepted", False)),
            "disclaimer_accepted_at": getattr(self, "disclaimer_accepted_at", None),
            "disclaimer_version": int(getattr(self, "disclaimer_version", 0) or 0),
            "first_launch_centered_done": bool(getattr(self, "first_launch_centered_done", False)),
            "last_rune_cleared_wall": self.last_rune_cleared_wall,
        }
        payload = json.dumps(data, ensure_ascii=False, indent=2)
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            tmp_path = SETTINGS_PATH.with_suffix(".json.tmp")
            with tmp_path.open("w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, SETTINGS_PATH)
        except Exception as exc:
            log_error("save_settings", exc)

    def _load_rune_window_anchor(self, raw):
        if not isinstance(raw, dict):
            return None
        try:
            window_rect = [int(v) for v in raw.get("window_rect", [])]
            relative_region = [float(v) for v in raw.get("relative_region", [])]
        except (TypeError, ValueError):
            return None
        if len(window_rect) != 4 or len(relative_region) != 4:
            return None
        if window_rect[2] <= window_rect[0] or window_rect[3] <= window_rect[1]:
            return None
        return {
            "pid": int(raw.get("pid") or 0),
            "process_name": str(raw.get("process_name") or "maplestory.exe").lower(),
            "window_rect": window_rect,
            "relative_region": relative_region,
        }

    def _build_ui(self):
        c = self.colors
        self.backdrop = tk.Canvas(self.root, bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.backdrop.pack(fill="both", expand=True)
        self._bind_drag(self.backdrop)
        self.backdrop.bind("<Configure>", self._draw_backdrop)
        self.card = tk.Frame(self.backdrop, bg=c["surface"])
        self.card_window = self.backdrop.create_window(12, 12, anchor="nw", window=self.card)
        self.surface_widgets.append(self.card)

        titlebar = tk.Frame(self.card, bg=c["surface_alt"], padx=ui_px(26), pady=0, height=ui_px(76))
        titlebar.pack(fill="x")
        titlebar.pack_propagate(False)
        self._bind_drag(titlebar)
        self.surface_widgets.append(titlebar)
        dots = tk.Frame(titlebar, bg=c["surface_alt"])
        dots.pack(side="left", pady=(ui_px(26),0), anchor="n")
        self._dot(dots, c["red"], self._quit_app).pack(side="left", padx=(0,ui_px(13)))
        self._dot(dots, c["yellow"], self._minimize).pack(side="left", padx=(0,ui_px(13)))
        self._dot(dots, c["green"], self._reset_app_size).pack(side="left")

        self.body = tk.Frame(self.card, bg=c["surface"])
        self.body.pack(fill="both", expand=True)
        self.surface_widgets.append(self.body)

        self.page_shell = tk.Frame(self.body, bg=c["surface"])
        self.page_shell.pack(fill="both", expand=True)
        self.pages = {
            "monitor": self._build_monitor_page(),
            "settings": self._build_settings_page(),
        }
        self.monitor_page = self.pages["monitor"]
        self._show_page("monitor")
        self.resize_grip = tk.Canvas(self.card, width=24, height=24, bg=c["surface"], highlightthickness=0, bd=0, cursor="size_nw_se")
        self.resize_grip.place(relx=1.0, rely=1.0, anchor="se", x=-10, y=-10)
        self.resize_grip.bind("<ButtonPress-1>", self._start_resize)
        self.resize_grip.bind("<B1-Motion>", self._resize)
        self.resize_grip.bind("<ButtonRelease-1>", self._end_resize)

    def _entry_block(self, parent, label, variable, unit):
        c = self.colors
        block = tk.Frame(parent, bg=c["panel"])
        if label:
            tk.Label(block, text=label, bg=c["panel"], fg=c["muted"], font=self._settings_font(9)).pack(anchor="w")
        shell = tk.Frame(block, bg=c["panel_2"], padx=12, pady=8, highlightthickness=1, highlightbackground=c["line"])
        shell.pack(anchor="w", pady=(5 if label else 0,0))
        entry = tk.Entry(shell, textvariable=variable, width=5, justify="center", relief="flat", borderwidth=0, bg=c["panel_2"], fg=c["blue"], insertbackground=c["blue"], font=self._settings_font(20, "bold"))
        entry.pack(side="left")
        entry.bind("<Return>", lambda _event: self._apply_monitor_config())
        if unit:
            tk.Label(shell, text=unit, bg=c["panel_2"], fg=c["muted"], font=self._settings_font(10)).pack(side="left", padx=(4,0))
        return block

    def _settings_toggle_row(self, parent, label, value, command):
        c = self.colors
        row = tk.Frame(parent, bg=c["panel"])
        row.pack(fill="x", pady=(0, 3 if LOW_RES else 8))
        tk.Label(row, text=label, bg=c["panel"], fg=c["text"],
                 font=self._settings_font(9 if LOW_RES else 10, "bold")).pack(side="left")
        ToggleSwitch(row, value, command, width=46 if LOW_RES else 64,
                     height=23 if LOW_RES else 30, on=c["blue"], off=c["panel_3"]).pack(side="right")
        return row

    def _settings_volume_row(self, parent, label, value, command):
        c = self.colors
        row = tk.Frame(parent, bg=c["panel"])
        row.pack(fill="x", pady=(0, 2 if LOW_RES else 8))
        tk.Label(row, text=label, bg=c["panel"], fg=c["muted"], font=self._settings_font(9)).pack(anchor="w")
        VolumeSlider(row, value, command, width=138 if LOW_RES else 245,
                     height=22 if LOW_RES else 32, start=c["blue"], end=c["cyan"]).pack(fill="x")
        return row

    def _settings_rune_cooldown_row(self, parent):
        c = self.colors
        row = tk.Frame(parent, bg=c["panel"])
        row.pack(fill="x", pady=(0, 5 if LOW_RES else 10))
        tk.Label(row, text="룬 게이지 기준", bg=c["panel"], fg=c["text"],
                 font=self._settings_font(9 if LOW_RES else 10, "bold")).pack(anchor="w")
        self.rune_cooldown_control = MinuteSegmentedControl(
            row, self.rune_cooldown_minutes, self._set_rune_cooldown_minutes,
            width=138 if LOW_RES else 245, height=27 if LOW_RES else 36,
            active=c["blue"], bg=c["panel_3"], fg=c["text"])
        self.rune_cooldown_control.pack(fill="x", pady=(2, 0))
        return row

    def _settings_booster_use_count_row(self, parent):
        c = self.colors
        row = tk.Frame(parent, bg=c["panel"])
        row.pack(fill="x", pady=(0, 2))
        tk.Label(row, text="부스터 사용 횟수", bg=c["panel"], fg=c["text"],
                 font=self._settings_font(9 if LOW_RES else 10, "bold")).pack(anchor="w")
        controls = tk.Frame(row, bg=c["panel"])
        controls.pack(fill="x", pady=(2, 0))
        self.booster_use_count_var = tk.StringVar(value=str(self.booster_use_count))
        self.booster_use_count_entry = tk.Entry(
            controls, textvariable=self.booster_use_count_var, width=5, justify="center",
            bg=c["panel_3"], fg=c["text"], insertbackground=c["text"], relief="flat",
            font=self._settings_font(9 if LOW_RES else 10))
        self.booster_use_count_entry.pack(side="left", ipady=2)
        tk.Label(controls, text="회", bg=c["panel"], fg=c["text"],
                 font=self._settings_font(9)).pack(side="left", padx=(3, 4))
        self.booster_use_count_apply_button = tk.Button(
            controls, text="적용", command=self._apply_booster_use_count,
            bg=c["panel_3"], fg=c["text"], activebackground=c["blue"],
            relief="flat", font=self._settings_font(9, "bold"), padx=6, pady=0)
        self.booster_use_count_apply_button.pack(side="right")
        self.booster_use_count_entry.bind("<Return>", self._apply_booster_use_count)
        self.booster_use_count_status = tk.StringVar(value="첫 안내 포함 · 다음 주기 적용")
        tk.Label(parent, textvariable=self.booster_use_count_status, bg=c["panel"], fg=c["muted"],
                 font=self._settings_font(8), justify="left", wraplength=138 if LOW_RES else 245).pack(anchor="w", pady=(0, 5))
        return row

    def _apply_booster_use_count(self, _event=None):
        self._set_booster_use_count(self.booster_use_count_var.get())
        return "break"

    def _set_booster_use_count(self, value):
        try:
            count = parse_booster_use_count(value)
        except (ValueError, TypeError, OverflowError):
            if hasattr(self, "booster_use_count_status"):
                self.booster_use_count_status.set("1 이상의 정수를 입력하세요.")
            return False
        # Only the preference changes; the controller snapshots the next cycle.
        self.booster_use_count = count
        if hasattr(self, "booster_use_count_var"):
            self.booster_use_count_var.set(str(count))
        if hasattr(self, "booster_use_count_status"):
            self.booster_use_count_status.set("저장됨 · 첫 안내 포함· 다음 주기 적용")
        self._save_settings()
        return True

    def _build_timers_page(self):
        page = tk.Frame(self.page_shell, bg=self.colors["surface"])
        header = tk.Frame(page, bg=self.colors["surface"])
        header.pack(fill="x")
        tk.Label(header, text="스킬 · 버프 · 룬 타이머", bg=self.colors["surface"], fg=self.colors["text"], font=self._font(11, "bold")).pack(side="left")
        RoundedButton(header, "+", self._add_timer, width=34, height=28, bg=self.colors["blue"], fg=self.colors["surface"], hover=self.colors["blue_hover"]).pack(side="right")
        self.timers_list = tk.Frame(page, bg=self.colors["surface"])
        self.timers_list.pack(fill="both", expand=True, pady=(8,0))
        self._rebuild_timer_rows()
        return page

    def _build_monitor_page(self):
        c = self.colors
        page = tk.Frame(self.page_shell, bg=c["surface"])
        self.monitor_page = page
        self.monitor_glow_image = self._make_monitor_glow_image()
        self.monitor_backdrop = tk.Canvas(page, width=APP_WIDTH - 26, height=APP_HEIGHT - 100, bg=c["surface"], highlightthickness=0, bd=0)
        self.monitor_backdrop.place(x=0, y=0, relwidth=1, relheight=1)
        self.monitor_backdrop.create_image(0, 0, image=self.monitor_glow_image, anchor="nw")
        self._bind_drag(self.monitor_backdrop)
        page.bind("<Configure>", self._layout_monitor_page)

        self.countdown_remaining = int(self.warning_loop_seconds)
        self.countdown_canvas = self.monitor_backdrop
        self._draw_countdown_display()

        self.auto_detect_status_var = tk.StringVar(value="수동 지정 대기")

        self.bottom_dock = tk.Canvas(page, width=620, height=160, bg=c["surface"], highlightthickness=0, bd=0, cursor="hand2")
        self.bottom_dock.place(relx=0.5, y=720, anchor="n")
        self.bottom_dock.bind("<Button-1>", self._handle_bottom_dock_click)
        self._draw_bottom_dock()

        return page

    def _build_settings_page(self):
        c = self.colors
        page = tk.Frame(self.page_shell, bg=c["surface"])
        viewport = tk.Canvas(page, bg=c["surface"], highlightthickness=0)
        viewport.pack(fill="both", expand=True, padx=0, pady=(36 if LOW_RES else 64, 4))
        viewport.configure(yscrollincrement=18)
        stack = tk.Frame(viewport, bg=c["surface"])
        stack_item = viewport.create_window(0, 0, anchor="n", window=stack)
        self.settings_viewport, self.settings_stack = viewport, stack
        self.settings_stack_item = stack_item
        stack.bind("<Configure>", self._center_settings_content)
        viewport.bind("<Configure>", self._center_settings_content)
        panel = tk.Frame(stack, bg=c["panel"], padx=4 if LOW_RES else 14,
                         pady=4 if LOW_RES else 14, highlightthickness=1, highlightbackground=c["line"])
        panel.pack(anchor="center")
        columns = tk.Frame(panel, bg=c["panel"])
        columns.pack(fill="x")
        left = tk.Frame(columns, bg=c["panel"])
        left.pack(side="left", anchor="n")
        tk.Frame(columns, bg=c["line"], width=1).pack(side="left", fill="y", padx=5 if LOW_RES else 18)
        right = tk.Frame(columns, bg=c["panel"])
        right.pack(side="left", anchor="n")
        tk.Label(left, text="화면 크기", bg=c["panel"], fg=c["text"],
                 font=self._settings_font(9 if LOW_RES else 10, "bold")).pack(anchor="w")
        profile_row = tk.Frame(left, bg=c["panel"])
        profile_row.pack(fill="x", pady=(2, 1))
        for profile, label in (("low", "저해상도"), ("high", "고해상도")):
            RoundedButton(profile_row, label, lambda value=profile: self._set_ui_profile(value),
                          width=67 if LOW_RES else 120, height=24 if LOW_RES else 30, radius=8,
                          bg=c["panel_3"], fg=c["text"], hover=c["panel_2"],
                          font=self._settings_font(9)).pack(side="left", padx=(0, 3))
        self.ui_profile_status = tk.StringVar(value="현재: " + ("저해상도" if LOW_RES else "고해상도"))
        tk.Label(left, textvariable=self.ui_profile_status, bg=c["panel"], fg=c["muted"],
                 font=self._settings_font(8), wraplength=138 if LOW_RES else 245).pack(anchor="w", pady=(0, 1))
        tk.Label(left, text="카운트 간격", bg=c["panel"], fg=c["text"],
                 font=self._settings_font(9 if LOW_RES else 10, "bold")).pack(anchor="w")
        row = tk.Frame(left, bg=c["panel"])
        row.pack(fill="x", pady=(2, 2))
        self.settings_count_entry = tk.Entry(row, textvariable=self.stall_var, width=5,
            justify="center", relief="flat", bg=c["panel_3"], fg=c["text"],
            insertbackground=c["text"], font=self._settings_font(9 if LOW_RES else 10))
        self.settings_count_entry.pack(side="left", ipady=2)
        self.settings_count_entry.bind("<Return>", lambda _event: self._apply_monitor_config())
        tk.Label(row, text="초", bg=c["panel"], fg=c["text"], font=self._settings_font(9)).pack(side="left", padx=3)
        self.settings_count_apply_button = tk.Button(row, text="적용", command=self._apply_monitor_config,
            bg=c["panel_3"], fg=c["text"], relief="flat", font=self._settings_font(9, "bold"), padx=6, pady=0)
        self.settings_count_apply_button.pack(side="right")
        self._settings_toggle_row(left, "카운트 알림음", self.warning_sound_enabled, self._set_warning_sound_enabled)
        self._settings_toggle_row(left, "룬 알림음", self.rune_sound_enabled, self._set_rune_sound_enabled)
        self._settings_toggle_row(left, "TTS 알림음", self.tts_sound_enabled, self._set_tts_sound_enabled)
        self._settings_volume_row(left, "카운트 볼륨", self.warning_volume, self._set_warning_volume)
        self._settings_volume_row(left, "룬 볼륨", self.rune_volume, self._set_rune_volume)
        self._settings_toggle_row(right, "수동 모드", self.offline_mode_enabled, self._set_offline_mode_enabled)
        self._settings_toggle_row(right, "부스터 모드", self.booster_mode_enabled, self._set_booster_mode_enabled)
        self._settings_booster_use_count_row(right)
        self._settings_rune_cooldown_row(right)
        self._settings_volume_row(right, "30분 쿠폰 볼륨", self.halfhour_volume, self._set_halfhour_volume)
        self.settings_diagnostics_parent = right
        footer = tk.Frame(panel, bg=c["panel"])
        footer.pack(fill="x", pady=(1, 0))
        notice_button = tk.Label(footer, text="이용 안내 다시 보기", bg=c["panel"], fg=c["muted"],
            font=self._settings_font(9), cursor="hand2")
        notice_button.pack(anchor="center")
        notice_button.bind("<Button-1>", lambda _event: self._show_disclaimer_dialog(readonly=True))
        license_button = tk.Label(footer, text="GPL-3.0-or-later · 무보증",
            wraplength=290 if LOW_RES else 540, bg=c["panel"], fg=c["muted"],
            font=self._settings_font(8), cursor="hand2")
        license_button.pack(anchor="center", pady=(2, 0))
        license_button.bind("<Button-1>", lambda _event: self._show_license_notice())
        self.settings_back_button = BackIconButton(page, lambda: self._switch_page_with_blur("monitor"),
            width=28 if LOW_RES else 44, height=28 if LOW_RES else 44,
            bg="#181a1b", hover="#222526", outline="#2b3031")
        self.settings_back_button.place(x=6, y=3, anchor="nw")
        self._raise_widget(self.settings_back_button)
        page.bind("<Configure>", self._layout_settings_page)
        wheel_tag = f"SettingsWheel{str(page)}"
        page.bind_class(wheel_tag, "<MouseWheel>", self._scroll_settings)
        page.bind_class(wheel_tag, "<Button-4>", self._scroll_settings)
        page.bind_class(wheel_tag, "<Button-5>", self._scroll_settings)
        def bind_wheel(widget):
            widget.bindtags((wheel_tag,) + widget.bindtags())
            for child in widget.winfo_children():
                bind_wheel(child)
        bind_wheel(page)
        return page

    def _center_settings_content(self, _event=None):
        viewport = self.settings_viewport
        stack = self.settings_stack
        width = max(1, viewport.winfo_width())
        height = max(1, viewport.winfo_height())
        content_height = stack.winfo_reqheight()
        page = viewport.master
        # Center in the page when it fits; keep the first row reachable when tall.
        top = max(0, (page.winfo_height() - content_height) / 2 - viewport.winfo_y())
        viewport.coords(self.settings_stack_item, width / 2, top)
        viewport.configure(scrollregion=(0, 0, width, max(height, top + content_height)))
        if top + content_height <= height:
            viewport.yview_moveto(0)

    def _scroll_settings(self, event):
        if getattr(self, "current_page", None) != "settings":
            return
        viewport = self.settings_viewport
        if self.settings_stack.winfo_reqheight() <= viewport.winfo_height():
            return "break"
        number = getattr(event, "num", None)
        delta = getattr(event, "delta", 0)
        if number in (4, 5):
            units = -3 if number == 4 else 3
        elif delta:
            units = (-1 if delta > 0 else 1) * max(1, round(abs(delta) / 120)) * 3
        else:
            return "break"
        viewport.yview_scroll(units, "units")
        return "break"

    def _set_ui_profile(self, profile):
        if profile not in ("low", "high"):
            return
        try:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            destination = APP_DIR / "ui-profile.json"
            temporary = destination.with_suffix(".json.tmp")
            temporary.write_text(json.dumps(profile), encoding="utf-8")
            os.replace(temporary, destination)
            label = "저해상도" if profile == "low" else "고해상도"
            self.ui_profile_status.set(f"다음 실행: {label}")
        except OSError as exc:
            log_error("save_ui_profile", exc)
            self.ui_profile_status.set("저장 실패 · 다시 선택해주세요")

    def _show_license_notice(self):
        """GPLv3 5(d)에 따른 저작권/무보증/라이선스 고지."""
        try:
            messagebox.showinfo(LICENSE_NOTICE_TITLE, LICENSE_NOTICE_TEXT, parent=self.root)
        except Exception as exc:
            log_error("license_notice", exc)

    def _raise_widget(self, widget):
        try:
            widget.tk.call("raise", widget._w)
        except tk.TclError:
            pass

    def _layout_settings_page(self, _event=None):
        button = getattr(self, "settings_back_button", None)
        if button is None:
            return
        try:
            width = max(1, int(self.root.winfo_width()))
            x = 6 if LOW_RES else 12
            y = 3 if LOW_RES else 8
            button.place_configure(x=x, y=y)
            self._raise_widget(button)
        except tk.TclError:
            pass

    def _monitor_scale(self):
        try:
            width = max(APP_MIN_WIDTH, int(self.root.winfo_width()))
            height = max(APP_MIN_HEIGHT, int(self.root.winfo_height()))
        except tk.TclError:
            width, height = self.app_size or DEFAULT_APP_SIZE
        if LOW_RES:
            return max(MIN_UI_SCALE, min(width / APP_WIDTH, (height - ui_px(76) - 24) / (APP_HEIGHT - 100)))
        return max(0.55, min(1.28, min(width / APP_WIDTH, height / APP_HEIGHT)))

    def _layout_monitor_page(self, _event=None):
        if not hasattr(self, "bottom_dock"):
            return
        scale = self._monitor_scale()
        dock_width = max(140 if LOW_RES else 340, int(620 * scale))
        dock_height = max(44, int(160 * scale))
        try:
            page_height = max(1, self.monitor_page.winfo_height())
        except tk.TclError:
            page_height = int((APP_HEIGHT - 100) * scale)
        dock_y = int(720 * scale)
        dock_y = min(dock_y, max(int(570 * scale), page_height - dock_height - int(30 * scale)))
        self.bottom_dock.configure(width=dock_width, height=dock_height)
        self.bottom_dock.place_configure(relx=0.5, y=dock_y, anchor="n")
        self._draw_bottom_dock()
        self._draw_countdown_display()

    def _draw_countdown_display(self, _event=None):
        if not hasattr(self, "countdown_canvas"):
            return
        c = self.colors
        canvas = self.countdown_canvas
        canvas.delete("countdown")
        progress = self._warning_countdown_progress()
        display_seconds = max(0, int(self._warning_remaining_float() + 0.999))
        canvas_width = max(1, int(canvas.winfo_width()))
        if canvas_width <= 1:
            canvas_width = max(canvas.winfo_reqwidth(), APP_WIDTH - 26)
        scale = self._monitor_scale()
        card_y = int(124 * scale)
        card_size = max(125, int(500 * scale))
        card_x = (canvas_width - card_size) / 2
        self.countdown_card_metrics = (card_x, card_y, card_size)
        self.countdown_panel_photo = self._make_countdown_panel_image(card_size, card_size, max(22, int(88 * scale)))
        canvas.create_image(card_x, card_y, image=self.countdown_panel_photo, anchor="nw", tags=("countdown", "countdown_card"))
        number_fill = "#8a9094" if self.warning_timer_paused else "#ffffff"
        self.countdown_number_item = canvas.create_text(card_x + card_size / 2, card_y + card_size * 0.48, text=str(display_seconds), fill=number_fill, font=self._timer_number_font(max(22, int(82 * scale))), anchor="center", tags=("countdown", "countdown_card"))
        progress_width = card_size - max(30, int(118 * scale))
        progress_height = max(4, int(16 * scale))
        progress_x = card_x + (card_size - progress_width) / 2
        progress_y = card_y + card_size - max(18, int(66 * scale))
        self.countdown_progress_photo = self._make_countdown_progress_image(progress_width, progress_height, progress)
        self.countdown_progress_item = canvas.create_image(progress_x, progress_y, image=self.countdown_progress_photo, anchor="nw", tags=("countdown", "countdown_card"))
        self.last_countdown_progress_update_at = time.monotonic()
        self._bind_countdown_card_tags(canvas)
        self._draw_rune_status_bar()

    def _draw_countdown_ring(self, _event=None):
        self._draw_countdown_display(_event)

    def _monitor_ui_visible(self):
        if getattr(self, "widget_mode_active", False):
            return False
        if getattr(self, "current_page", "monitor") != "monitor":
            return False
        try:
            return self.root.state() == "normal" and bool(self.root.winfo_viewable())
        except tk.TclError:
            return False

    def _update_countdown_display_lightweight(self, now=None):
        if not self._monitor_ui_visible() or not hasattr(self, "countdown_canvas"):
            return
        now = time.monotonic() if now is None else now
        canvas = self.countdown_canvas
        remaining = max(0, int(self._warning_remaining_float(now) + 0.999))
        self.countdown_remaining = remaining
        number_item = getattr(self, "countdown_number_item", None)
        if number_item is None:
            self._draw_countdown_display()
            return
        number_fill = "#8a9094" if self.warning_timer_paused else "#ffffff"
        try:
            canvas.itemconfigure(number_item, text=str(remaining), fill=number_fill)
        except tk.TclError:
            self.countdown_number_item = None
            self._draw_countdown_display()
            return

        progress_item = getattr(self, "countdown_progress_item", None)
        if progress_item is not None and now - float(getattr(self, "last_countdown_progress_update_at", 0.0)) >= self.countdown_progress_update_interval:
            try:
                bbox = canvas.bbox(progress_item)
                if bbox:
                    width = max(1, bbox[2] - bbox[0])
                    height = max(1, bbox[3] - bbox[1])
                    self.countdown_progress_photo = self._make_countdown_progress_image(width, height, self._warning_countdown_progress(now))
                    canvas.itemconfigure(progress_item, image=self.countdown_progress_photo)
                    self.last_countdown_progress_update_at = now
            except tk.TclError:
                self.countdown_progress_item = None

    def _bind_countdown_card_tags(self, canvas):
        canvas.tag_bind("countdown_card", "<ButtonPress-1>", self._handle_countdown_card_press)
        canvas.tag_bind("countdown_card", "<ButtonRelease-1>", self._handle_countdown_card_release)
        canvas.tag_bind("countdown_card", "<Enter>", lambda _e: canvas.configure(cursor="hand2"))
        canvas.tag_bind("countdown_card", "<Leave>", lambda _e: canvas.configure(cursor=""))

    def _handle_countdown_card_press(self, event):
        self.countdown_press_root = (event.x_root, event.y_root)
        return "break"

    def _handle_countdown_card_release(self, event):
        start = getattr(self, "countdown_press_root", None)
        self.countdown_press_root = None
        if start is None:
            return "break"
        dx = abs(event.x_root - start[0])
        dy = abs(event.y_root - start[1])
        if dx <= 8 and dy <= 8:
            self._toggle_warning_countdown_pause()
        return "break"

    def _toggle_warning_countdown_pause(self):
        now = time.monotonic()
        total = self._warning_timer_total()
        if getattr(self, "warning_timer_paused", False):
            remaining = max(0.0, min(total, float(getattr(self, "warning_paused_remaining", total))))
            self.last_stall_alert_at = now - (total - remaining)
            self.warning_timer_paused = False
        else:
            self.warning_paused_remaining = self._warning_remaining_float(now)
            self.warning_timer_paused = True
        self._render_monitor_status()
        if getattr(self, "widget_mode_active", False):
            self._draw_widget_mode(force=True)

    def _make_countdown_panel_image(self, width, height, radius):
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        base = Image.new("RGBA", (width, height), (5, 7, 7, 248))
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.ellipse((-80, -120, width * 0.85, height * 0.70), fill=(77, 241, 178, 23))
        draw.ellipse((width * 0.28, height * 0.08, width * 1.15, height * 0.95), fill=(26, 197, 196, 13))
        draw.rectangle((0, 0, width, int(height * 0.55)), fill=(255, 255, 255, 3))
        glow = glow.filter(ImageFilter.GaussianBlur(46))
        base.alpha_composite(glow)
        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=radius, fill=255)
        image.alpha_composite(Image.composite(base, Image.new("RGBA", (width, height), (0, 0, 0, 0)), mask))
        border = ImageDraw.Draw(image)
        border.rounded_rectangle((1, 1, width - 2, height - 2), radius=radius, outline=(43, 50, 52, 225), width=2)
        return ImageTk.PhotoImage(image)

    def _make_countdown_progress_image(self, width, height, progress):
        progress = max(0.0, min(1.0, progress))
        radius = height // 2
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=(29, 34, 33, 215))
        fill_width = int(round(width * progress))
        if fill_width > 0:
            gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            pixels = gradient.load()
            start = (170, 180, 185, 255)
            end = (255, 255, 255, 255)
            denom = max(1, width - 1)
            for x in range(width):
                t = x / denom
                color = tuple(int(start[i] * (1 - t) + end[i] * t) for i in range(4))
                for y in range(height):
                    pixels[x, y] = color
            gradient = gradient.crop((0, 0, fill_width, height))
            mask = Image.new("L", (fill_width, height), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle((0, 0, fill_width - 1, height - 1), radius=radius, fill=255)
            image.alpha_composite(Image.composite(gradient, Image.new("RGBA", (fill_width, height), (0, 0, 0, 0)), mask), (0, 0))
        return ImageTk.PhotoImage(image)

    def _make_rune_status_bar_image(self, width, height, active, cooldown_progress=0.0):
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        radius = height // 2
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=(28, 34, 32, 165))
        fill_ratio = 1.0 if active else max(0.0, min(1.0, cooldown_progress))
        if fill_ratio <= 0:
            return ImageTk.PhotoImage(image)
        gradient = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pixels = gradient.load()
        start = (74, 241, 174, 255)
        end = (224, 252, 240, 255)
        denom = max(1, width - 1)
        for x in range(width):
            t = x / denom
            color = tuple(int(start[i] * (1 - t) + end[i] * t) for i in range(4))
            for y in range(height):
                pixels[x, y] = color
        fill_width = max(1, int(round(width * fill_ratio)))
        gradient = gradient.crop((0, 0, fill_width, height))
        mask = Image.new("L", (width, height), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, fill_width - 1, height - 1), radius=radius, fill=255)
        mask = mask.crop((0, 0, fill_width, height))
        image.alpha_composite(Image.composite(gradient, Image.new("RGBA", (fill_width, height), (0, 0, 0, 0)), mask), (0, 0))
        return ImageTk.PhotoImage(image)

    def _rune_cooldown_progress(self, now=None):
        started_at = getattr(self, "last_rune_cleared_at", None)
        if not started_at:
            return 0.0
        now = now or time.monotonic()
        return max(0.0, min(1.0, (now - started_at) / self._rune_cooldown_seconds()))

    def _rune_cooldown_seconds(self):
        return max(60, int(getattr(self, "rune_cooldown_minutes", DEFAULT_RUNE_COOLDOWN_MINUTES)) * 60)

    def _rune_cooldown_display_pair(self):
        total_minutes = normalize_rune_cooldown_minutes(getattr(self, "rune_cooldown_minutes", DEFAULT_RUNE_COOLDOWN_MINUTES))
        if getattr(self, "rune_active_visual", False):
            return total_minutes, total_minutes
        progress = self._rune_cooldown_progress()
        elapsed_minutes = int(max(0, min(total_minutes, math.floor(progress * total_minutes))))
        return elapsed_minutes, total_minutes

    def _mark_rune_cleared(self):
        self.last_rune_cleared_at = time.monotonic()
        self.last_rune_cleared_wall = time.time()
        self._save_settings()

    def _reset_offline_rune_cycle(self, save=True):
        now = time.monotonic()
        self.last_rune_cleared_at = now
        self.last_rune_cleared_wall = time.time()
        self.offline_rune_due = False
        self.offline_rune_alert_count = 0
        self.offline_rune_next_alert_at = 0.0
        self.last_rune_alert_at = 0.0
        self._clear_queued_sound("rune")
        self._clear_queued_sound("rune_offline_tts")
        self._set_rune_visual(False)
        if save:
            self._save_settings()
        self._refresh_rune_progress_visuals(force=True)

    def _refresh_rune_progress_visuals(self, now=None, force=False):
        now = time.monotonic() if now is None else now
        if not force and now - float(getattr(self, "last_offline_rune_progress_draw_at", 0.0)) < 1.0:
            return
        self.last_offline_rune_progress_draw_at = now
        if self._monitor_ui_visible():
            self._draw_rune_status_bar()
        if getattr(self, "widget_mode_active", False):
            self._draw_widget_mode(force=True)

    def _offline_rune_tick(self, now=None):
        if not getattr(self, "offline_mode_enabled", False):
            return
        now = time.monotonic() if now is None else now
        if self.last_rune_cleared_at is None:
            self._reset_offline_rune_cycle(save=True)
            return

        progress = self._rune_cooldown_progress(now)
        if progress >= 1.0:
            if not getattr(self, "offline_rune_due", False):
                self.offline_rune_due = True
                self.offline_rune_alert_count = 0
                self.offline_rune_next_alert_at = 0.0
                self._set_rune_visual(True)
            if (
                self.offline_rune_alert_count < OFFLINE_RUNE_ALERT_LIMIT
                and now >= self.offline_rune_next_alert_at
            ):
                self._play_offline_rune_due_alert()
                self.offline_rune_alert_count += 1
                self.offline_rune_next_alert_at = now + OFFLINE_RUNE_ALERT_INTERVAL_SECONDS
            self._refresh_rune_progress_visuals(now, force=True)
            return

        if getattr(self, "offline_rune_due", False):
            self.offline_rune_due = False
            self.offline_rune_alert_count = 0
            self.offline_rune_next_alert_at = 0.0
        if getattr(self, "rune_active_visual", False):
            self._set_rune_visual(False)
        self._refresh_rune_progress_visuals(now)

    def _play_offline_rune_due_alert(self):
        if not bool(getattr(self, "rune_sound_enabled", True)):
            return
        volume = self._sound_volume_for_key("rune")
        if volume <= 0:
            return
        self._clear_queued_sound("rune")
        self._clear_queued_sound("rune_offline_tts")
        tts = self._offline_rune_due_tts_path()
        if tts and Path(tts).exists():
            self.sound_queue.put(("rune_offline_tts", str(tts), volume))
        base = self.sound_paths.get("rune")
        if base:
            self.sound_queue.put(("rune", self._volume_adjusted_sound_path("rune", volume, base), volume))

    def _offline_rune_due_tts_path(self):
        path = self.sound_paths.get("rune_due_tts")
        if not path:
            return None
        path = Path(path)
        try:
            if path.exists() and path.stat().st_size > 0:
                return path
        except OSError:
            pass
        return None

    def _draw_rune_status_bar(self):
        if not hasattr(self, "monitor_backdrop"):
            return
        canvas = self.monitor_backdrop
        canvas.delete("rune_status")
        card_x, card_y, card_size = getattr(self, "countdown_card_metrics", ((APP_WIDTH - 26 - 500) / 2, 124, 500))
        scale = self._monitor_scale()
        bar_width = card_size
        bar_height = max(4, int(17 * scale))
        bar_x = card_x
        bar_y = card_y + card_size + int(32 * scale)
        active = getattr(self, "rune_active_visual", False)
        self.rune_status_bar_photo = self._make_rune_status_bar_image(bar_width, bar_height, active, self._rune_cooldown_progress())
        canvas.create_image(bar_x, bar_y, image=self.rune_status_bar_photo, anchor="nw", tags="rune_status")

    def _draw_scan_icon(self, canvas, cx, cy, color):
        size = max(7, round(30 * self._monitor_scale())) if LOW_RES else 18
        arm = max(4, round(size * 0.55)) if LOW_RES else 10
        opts = {"fill": color, "width": 3, "capstyle": tk.ROUND}
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            x = cx + sx * size
            y = cy + sy * size
            canvas.create_line(x, y, x - sx * arm, y, **opts)
            canvas.create_line(x, y, x, y - sy * arm, **opts)

    def _draw_gear_icon(self, canvas, cx, cy, color):
        icon = self._make_tinted_settings_icon(max(16, round(70 * self._monitor_scale())) if LOW_RES else 42, color)
        if icon is not None:
            self.bottom_settings_icon_photo = icon
            canvas.create_image(cx, cy, image=self.bottom_settings_icon_photo)
            return
        opts = {"fill": color, "width": 3, "capstyle": tk.ROUND}
        for index in range(8):
            angle = math.radians(index * 45)
            inner = 17
            outer = 22
            canvas.create_line(
                cx + math.cos(angle) * inner,
                cy + math.sin(angle) * inner,
                cx + math.cos(angle) * outer,
                cy + math.sin(angle) * outer,
                **opts,
            )
        canvas.create_oval(cx - 15, cy - 15, cx + 15, cy + 15, outline=color, width=3)
        canvas.create_oval(cx - 5, cy - 5, cx + 5, cy + 5, outline=color, width=3)

    def _make_tinted_settings_icon(self, size, color):
        try:
            path = resource_path("settings_icon.png")
            if not path.exists():
                return None
            image = Image.open(path).convert("RGBA")
            image.thumbnail((size, size), Image.Resampling.LANCZOS)
            tint = color.lstrip("#")
            rgb = tuple(int(tint[i:i+2], 16) for i in (0, 2, 4))
            alpha = image.getchannel("A")
            tinted = Image.new("RGBA", image.size, rgb + (0,))
            tinted.putalpha(alpha)
            return ImageTk.PhotoImage(tinted)
        except Exception:
            return None

    def _scan_capture_is_active(self):
        return (
            not getattr(self, "offline_mode_enabled", False)
            and
            bool(getattr(self, "rune_region", None))
            and bool(getattr(self, "rune_capture_active", False))
            and self._maplestory_process_is_running()
        )

    def _set_rune_capture_active(self, active):
        active = (
            bool(active)
            and bool(getattr(self, "rune_region", None))
            and not getattr(self, "offline_mode_enabled", False)
        )
        if getattr(self, "rune_capture_active", False) == active:
            return
        self.rune_capture_active = active
        self._draw_bottom_dock()

    def _maplestory_process_is_running(self, max_age=1.0):
        now = time.monotonic()
        if now - getattr(self, "last_maplestory_process_check_at", 0.0) < max_age:
            return bool(getattr(self, "maplestory_process_running", False))
        running = False
        if sys.platform.startswith("win"):
            snapshot = None
            invalid_snapshot = (-1, ctypes.c_void_p(-1).value)
            try:
                kernel32 = ctypes.windll.kernel32
                kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
                snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
                if snapshot and snapshot not in invalid_snapshot:
                    class ProcessEntry32(ctypes.Structure):
                        _fields_ = [
                            ("dwSize", wintypes.DWORD),
                            ("cntUsage", wintypes.DWORD),
                            ("th32ProcessID", wintypes.DWORD),
                            ("th32DefaultHeapID", ctypes.c_void_p),
                            ("th32ModuleID", wintypes.DWORD),
                            ("cntThreads", wintypes.DWORD),
                            ("th32ParentProcessID", wintypes.DWORD),
                            ("pcPriClassBase", ctypes.c_long),
                            ("dwFlags", wintypes.DWORD),
                            ("szExeFile", wintypes.WCHAR * 260),
                        ]
                    entry = ProcessEntry32()
                    entry.dwSize = ctypes.sizeof(ProcessEntry32)
                    has_item = kernel32.Process32FirstW(snapshot, ctypes.byref(entry))
                    while has_item:
                        if str(entry.szExeFile).lower() in MAPLE_PROCESS_NAMES:
                            running = True
                            break
                        has_item = kernel32.Process32NextW(snapshot, ctypes.byref(entry))
            except Exception:
                running = bool(self._find_maplestory_windows())
            finally:
                if snapshot and snapshot not in invalid_snapshot:
                    try:
                        ctypes.windll.kernel32.CloseHandle(snapshot)
                    except Exception:
                        pass
        else:
            running = bool(self._find_maplestory_windows())
        self.maplestory_process_running = running
        self.last_maplestory_process_check_at = now
        return running

    def _draw_bottom_dock(self):
        if not hasattr(self, "bottom_dock"):
            return
        c = self.colors
        canvas = self.bottom_dock
        canvas.delete("all")
        width = max(1, int(canvas.winfo_width() or float(canvas.cget("width")) or 620))
        height = max(1, int(canvas.winfo_height() or float(canvas.cget("height")) or 160))
        scale = max(MIN_UI_SCALE, min(1.28, width / 620))
        dock_x1, dock_y1, dock_x2, dock_y2 = 0, 4, width, height - 4
        self._canvas_rounded_rect(canvas, dock_x1 + 2, dock_y1 + 2, dock_x2 - 2, dock_y2 - 2, max(14, int(48 * scale)), fill=(c["panel"]), outline=c["line"], width=2)

        button_size = max(30, int(106 * scale))
        button_y = height / 2
        centers = {
            "scan": (width * 0.22, button_y),
            "rune": (width * 0.50, button_y),
            "settings": (width * 0.78, button_y),
        }
        if getattr(self, "booster_mode_enabled", False):
            centers = {name: (width * fraction, button_y) for name, fraction in
                       (("scan", .17), ("rune", .39), ("booster", .61), ("settings", .83))}
            button_size = min(button_size, width * .19)
        self.bottom_dock_regions = {}
        for name, (cx, cy) in centers.items():
            x1 = cx - button_size / 2
            y1 = cy - button_size / 2
            x2 = cx + button_size / 2
            y2 = cy + button_size / 2
            self.bottom_dock_regions[name] = (x1, y1, x2, y2)
            outline = "#353a3b"
            line_width = 2
            if name == "scan":
                outline = c["blue"] if self._scan_capture_is_active() else c["red"]
                line_width = max(2, int(3 * scale))
            elif name == "booster":
                outline = "#4af1ae" if getattr(self, "booster_running", False) else "#353a3b"
                line_width = max(2, int(3 * scale))
            self._canvas_rounded_rect(canvas, x1, y1, x2, y2, max(8, int(30 * scale)), fill="#101213", outline=outline, width=line_width)

        self._draw_scan_icon(canvas, *centers["scan"], "#f4f6f7")
        rune_cx, rune_cy = centers["rune"]
        rune_size = max(5, int(18 * scale))
        if getattr(self, "rune_active_visual", False):
            blink_on = getattr(self, "rune_blink_on", True)
            canvas.create_polygon(
                rune_cx, rune_cy - rune_size,
                rune_cx + rune_size, rune_cy,
                rune_cx, rune_cy + rune_size,
                rune_cx - rune_size, rune_cy,
                fill="#4af1ae" if blink_on else "#12382b",
                outline="#9ff7d2" if blink_on else "#367d60",
                width=3 if blink_on else 2,
            )
        else:
            canvas.create_polygon(
                rune_cx, rune_cy - rune_size,
                rune_cx + rune_size, rune_cy,
                rune_cx, rune_cy + rune_size,
                rune_cx - rune_size, rune_cy,
                fill="#4af1ae",
                outline="",
                width=0,
            )
        if "booster" in centers:
            self._draw_booster_icon(canvas, *centers["booster"], rune_size)
        self._draw_gear_icon(canvas, *centers["settings"], "#f4f6f7")

    def _draw_booster_icon(self, canvas, cx, cy, half_height):
        running = bool(getattr(self, "booster_running", False))
        half_width = max(4, int(half_height * .72))
        corner = max(2, int(half_width * .42))
        canvas.create_polygon(
            cx - half_width + corner, cy - half_height,
            cx + half_width - corner, cy - half_height,
            cx + half_width, cy - half_height + corner,
            cx + half_width, cy + half_height - corner,
            cx + half_width - corner, cy + half_height,
            cx - half_width + corner, cy + half_height,
            cx - half_width, cy + half_height - corner,
            cx - half_width, cy - half_height + corner,
            fill="#9ff7d2", outline="", width=0)

    def _handle_bottom_dock_click(self, event):
        for name, (x1, y1, x2, y2) in getattr(self, "bottom_dock_regions", {}).items():
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                if name == "scan":
                    self._select_rune_region()
                elif name == "rune":
                    if getattr(self, "offline_mode_enabled", False):
                        self._reset_offline_rune_cycle()
                elif name == "settings":
                    self._toggle_settings_page()
                elif name == "booster":
                    self._toggle_booster()
                return "break"
        return "break"

    def _set_rune_visual(self, active, rune_cleared=False):
        active = bool(active)
        was_active = bool(getattr(self, "rune_active_visual", False))
        if was_active and not active and rune_cleared:
            self._mark_rune_cleared()
        self.rune_active_visual = active
        if active:
            self._start_rune_blink()
        else:
            self._stop_rune_blink()
        if self._monitor_ui_visible():
            self._draw_rune_status_bar()
            self._draw_bottom_dock()
        if getattr(self, "widget_mode_active", False):
            self._draw_widget_mode(force=True)

    def _start_rune_blink(self):
        if getattr(self, "rune_blink_after_id", None) is not None:
            return
        self.rune_blink_on = True
        self.rune_blink_after_id = self.root.after(520, self._tick_rune_blink)

    def _tick_rune_blink(self):
        self.rune_blink_after_id = None
        if not getattr(self, "rune_active_visual", False):
            self.rune_blink_on = False
            if self._monitor_ui_visible():
                self._draw_bottom_dock()
            if getattr(self, "widget_mode_active", False):
                self._draw_widget_mode(force=True)
            return
        self.rune_blink_on = not getattr(self, "rune_blink_on", True)
        if self._monitor_ui_visible():
            self._draw_bottom_dock()
        if getattr(self, "widget_mode_active", False):
            self._draw_widget_mode(force=True)
        self.rune_blink_after_id = self.root.after(520, self._tick_rune_blink)

    def _stop_rune_blink(self):
        after_id = getattr(self, "rune_blink_after_id", None)
        if after_id is not None:
            try:
                self.root.after_cancel(after_id)
            except tk.TclError:
                pass
        self.rune_blink_after_id = None
        self.rune_blink_on = False

    def _make_monitor_glow_image(self):
        width = max(1, APP_WIDTH - 26)
        height = max(1, APP_HEIGHT - 100)
        image = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.ellipse((210, 170, 650, 660), fill=(19, 242, 174, 18))
        draw.ellipse((70, 720, 710, 1010), fill=(19, 242, 174, 12))
        draw.ellipse((565, 30, 830, 280), fill=(19, 242, 174, 22))
        glow = glow.filter(ImageFilter.GaussianBlur(74))
        image.alpha_composite(glow)
        return ImageTk.PhotoImage(image)

    def _draw_rune_diamond(self, active=False):
        if not hasattr(self, "rune_diamond"):
            return
        c = self.colors
        canvas = self.rune_diamond
        canvas.delete("all")
        width = max(58, canvas.winfo_width(), canvas.winfo_reqwidth())
        height = max(58, canvas.winfo_height(), canvas.winfo_reqheight())
        cx, cy = width / 2, height / 2
        size = min(width, height) * 0.43
        outline = c["purple"] if active else "#4af1ae"
        canvas.create_polygon(cx, cy - size, cx + size, cy, cx, cy + size, cx - size, cy, fill=c["panel"], outline=outline, width=3)

    def _toggle_settings_page(self):
        target = "monitor" if getattr(self, "current_page", "monitor") == "settings" else "settings"
        self._switch_page_with_blur(target)

    def _switch_page_with_blur(self, name):
        if getattr(self, "current_page", None) == name:
            return
        should_blur = False
        position_before = self._current_raw_position()
        size_before = nearest_app_size(
            getattr(self, "app_size", DEFAULT_APP_SIZE)[0],
            getattr(self, "app_size", DEFAULT_APP_SIZE)[1],
        )
        try:
            should_blur = self.root.state() == "normal" and bool(self.root.winfo_viewable())
        except tk.TclError:
            should_blur = False
        self._cancel_surface_refresh()
        self._show_page(name)
        self._restore_page_transition_position(position_before, size_before)
        if should_blur:
            try:
                self.root.update_idletasks()
                self._capture_restore_blur_image()
                self._show_restore_blur_overlay()
            except tk.TclError:
                pass
        self.root.after(40, lambda pos=position_before, size=size_before: self._restore_page_transition_position(pos, size))
        self.root.after(180, lambda pos=position_before, size=size_before: self._restore_page_transition_position(pos, size))

    def _restore_page_transition_position(self, position, size=None):
        if getattr(self, "widget_mode_active", False):
            return
        if position is None:
            return
        try:
            x, y = int(position[0]), int(position[1])
            self.app_position = (x, y)
            if size:
                width, height = int(size[0]), int(size[1])
                self.root.geometry(f"{width}x{height}+{x}+{y}")
            else:
                self.root.geometry(f"+{x}+{y}")
            self.root.update_idletasks()
        except (tk.TclError, TypeError, ValueError):
            pass

    def _build_preset_page(self):
        page = tk.Frame(self.page_shell, bg=self.colors["surface"])
        tk.Label(page, text="프리셋", bg=self.colors["surface"], fg=self.colors["text"], font=self._font(11, "bold")).pack(anchor="w")
        tk.Label(page, text="타이머 구성을 저장하거나 다른 파일로 옮길 수 있습니다.", bg=self.colors["surface"], fg=self.colors["muted"], font=self._font(8)).pack(anchor="w", pady=(2,12))
        for text, cmd in (("설정 저장", self._save_settings), ("프리셋 내보내기", self._export_preset), ("프리셋 가져오기", self._import_preset), ("기본값 복원", self._reset_defaults), ("경고음 테스트", lambda: self._play("warning")), ("왼쪽 소리 테스트", lambda: self._play("left")), ("오른쪽 소리 테스트", lambda: self._play("right"))):
            RoundedButton(page, text, cmd, width=150, bg=self.colors["panel_2"], fg=self.colors["text"], hover=self.colors["hover"]).pack(anchor="w", pady=(0,8))
        return page

    def _show_page(self, name):
        for page in self.pages.values():
            page.pack_forget()
        self.pages[name].pack(fill="both", expand=True)
        self.current_page = name
        if name == "settings":
            self._layout_settings_page()

    def _rebuild_timer_rows(self):
        if not hasattr(self, "timers_list"):
            return
        for child in self.timers_list.winfo_children():
            child.destroy()
        self.timer_rows = []
        for index, timer in enumerate(self.timers):
            row = tk.Frame(self.timers_list, bg=self.colors["panel"], padx=10, pady=8)
            row.pack(fill="x", pady=(0,7))
            name = tk.Entry(row, width=12, relief="flat", bg=self.colors["panel"], fg=self.colors["text"], insertbackground=self.colors["blue"], font=self._font(9, "bold"))
            name.insert(0, timer.name)
            name.pack(side="left")
            secs = tk.Entry(row, width=6, justify="center", relief="flat", bg=self.colors["surface_alt"], fg=self.colors["text"], insertbackground=self.colors["blue"], font=self._font(9, "bold"))
            secs.insert(0, str(timer.seconds))
            secs.pack(side="left", padx=(8,0))
            countdown = tk.Label(row, text=fmt(timer.remaining or timer.seconds), bg=self.colors["panel"], fg=self.colors["blue"], font=self._font(10, "bold"))
            countdown.pack(side="left", padx=(10,0))
            enabled = tk.BooleanVar(value=timer.enabled)
            tk.Checkbutton(row, variable=enabled, bg=self.colors["panel"], activebackground=self.colors["panel"], activeforeground=self.colors["text"], selectcolor=self.colors["surface_alt"], fg=self.colors["muted"], text="켜기", font=self._font(8)).pack(side="right")
            tk.Button(row, text="×", command=lambda i=index: self._remove_timer(i), relief="flat", bg=self.colors["panel"], activebackground=self.colors["hover"], activeforeground=self.colors["text"], fg=self.colors["muted"]).pack(side="right", padx=(0,6))
            self.timer_rows.append({"name": name, "secs": secs, "countdown": countdown, "enabled": enabled, "timer": timer})

    def _sync_timer_rows_to_model(self):
        for row in self.timer_rows:
            timer = row["timer"]
            timer.name = row["name"].get().strip() or "타이머"
            timer.seconds = clamp_int(row["secs"].get(), timer.seconds)
            timer.enabled = bool(row["enabled"].get())

    def _add_timer(self):
        self._sync_timer_rows_to_model()
        item = TimerItem("새 타이머", 60, True)
        item.reset()
        self.timers.append(item)
        self._rebuild_timer_rows()
        self._save_settings()

    def _remove_timer(self, index):
        if 0 <= index < len(self.timers):
            self.timers.pop(index)
            self._rebuild_timer_rows()
            self._save_settings()

    def _draw_backdrop(self, _event=None):
        w, h = max(self.backdrop.winfo_width(),1), max(self.backdrop.winfo_height(),1)
        self.backdrop.delete("backdrop")
        self._rounded_rect(14,18,w-10,h-8,30,fill=self.colors["shadow"],outline="",tag="backdrop")
        self._rounded_rect(8,8,w-14,h-14,28,fill=self.colors["surface"],outline="#0f1212",tag="backdrop")
        self.backdrop.tag_lower("backdrop")
        self.backdrop.itemconfigure(self.card_window, width=max(w-26,1), height=max(h-24,1))

    def _rounded_rect(self, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        self.backdrop.create_polygon(points, smooth=True, splinesteps=22, **kwargs)

    def _canvas_rounded_rect(self, canvas, x1, y1, x2, y2, radius, **kwargs):
        points = [x1+radius,y1,x2-radius,y1,x2,y1,x2,y1+radius,x2,y2-radius,x2,y2,x2-radius,y2,x1+radius,y2,x1,y2,x1,y2-radius,x1,y1+radius,x1,y1]
        canvas.create_polygon(points, smooth=True, splinesteps=24, **kwargs)

    def _dot(self, parent, color, command):
        dot = tk.Canvas(parent, width=ui_px(20), height=ui_px(20), bg=parent["bg"], highlightthickness=0, bd=0, cursor="hand2")
        dot.create_oval(1,1,ui_px(20)-1,ui_px(20)-1,fill=color,outline=color)
        dot.bind("<Button-1>", lambda _e: command())
        return dot

    def _bind_drag(self, widget):
        widget.bind("<ButtonPress-1>", self._start_drag)
        widget.bind("<B1-Motion>", self._drag)
        widget.bind("<ButtonRelease-1>", self._end_drag)

    def _event_in_countdown_card(self, event):
        if not hasattr(self, "monitor_backdrop") or event.widget is not self.monitor_backdrop:
            return False
        card_x, card_y, card_size = getattr(self, "countdown_card_metrics", (None, None, None))
        if card_x is None:
            return False
        return card_x <= event.x <= card_x + card_size and card_y <= event.y <= card_y + card_size

    def _start_drag(self, event):
        if self._event_in_countdown_card(event):
            self.drag_blocked = True
            return "break"
        self.drag_blocked = False
        self.dragging_main_window = True
        self.drag_using_proxy = False
        self._cancel_surface_refresh()
        try:
            self.root.update_idletasks()
            self.drag_offset_x = int(event.x_root) - int(self.root.winfo_x())
            self.drag_offset_y = int(event.y_root) - int(self.root.winfo_y())
        except tk.TclError:
            self.drag_offset_x, self.drag_offset_y = event.x, event.y
        self.drag_using_proxy = self._begin_proxy_window_drag()
        return "break"

    def _begin_proxy_window_drag(self):
        try:
            self.root.update_idletasks()
            x = int(self.root.winfo_x())
            y = int(self.root.winfo_y())
            width = max(1, int(self.root.winfo_width()))
            height = max(1, int(self.root.winfo_height()))
            image = ImageGrab.grab(bbox=(x, y, x + width, y + height)).convert("RGBA")
            image = self._clip_restore_blur_to_app_shape(image)
            self.drag_proxy_photo = ImageTk.PhotoImage(image)
            proxy = tk.Toplevel(self.root)
            proxy.overrideredirect(True)
            proxy.attributes("-topmost", True)
            proxy.configure(bg=TRANSPARENT)
            try:
                proxy.wm_attributes("-transparentcolor", TRANSPARENT)
            except tk.TclError:
                pass
            proxy.geometry(f"{width}x{height}+{x}+{y}")
            canvas = tk.Canvas(proxy, width=width, height=height, bg=TRANSPARENT, highlightthickness=0, bd=0)
            canvas.pack(fill="both", expand=True)
            canvas.create_image(0, 0, image=self.drag_proxy_photo, anchor="nw")
            canvas.bind("<B1-Motion>", self._drag)
            canvas.bind("<ButtonRelease-1>", self._end_drag)
            proxy.bind("<B1-Motion>", self._drag)
            proxy.bind("<ButtonRelease-1>", self._end_drag)
            self._apply_rounded_window(proxy, width, height, max(28, int(42 * self._monitor_scale())))
            self.drag_proxy = proxy
            self.root.attributes("-alpha", 0.02)
            proxy.lift()
            return True
        except Exception:
            self._destroy_drag_proxy()
            try:
                self.root.attributes("-alpha", 1.0)
            except tk.TclError:
                pass
            return False

    def _drag(self, event):
        if getattr(self, "drag_blocked", False):
            return "break"
        x = int(event.x_root) - int(getattr(self, "drag_offset_x", 0))
        y = int(event.y_root) - int(getattr(self, "drag_offset_y", 0))
        self.app_position = (x, y)
        if getattr(self, "drag_using_proxy", False) and getattr(self, "drag_proxy", None) is not None:
            try:
                self.drag_proxy.geometry(f"+{x}+{y}")
            except tk.TclError:
                self.drag_using_proxy = False
                self._move_main_window(x, y)
        else:
            self._move_main_window(x, y)
        return "break"

    def _end_drag(self, _event):
        if getattr(self, "drag_blocked", False):
            self.drag_blocked = False
            self.dragging_main_window = False
            return "break"
        if not getattr(self, "dragging_main_window", False):
            return "break"
        self._finish_main_window_drag()
        return "break"

    def _finish_main_window_drag(self):
        x, y = self._safe_app_position(getattr(self, "app_position", None))
        self.app_position = (x, y)
        self._destroy_drag_proxy()
        try:
            self.root.attributes("-alpha", 1.0)
            self.root.geometry(f"+{x}+{y}")
            self.root.deiconify()
            self.root.lift()
        except tk.TclError:
            pass
        self.drag_using_proxy = False
        self.dragging_main_window = False
        try:
            self.root.update_idletasks()
        except tk.TclError:
            pass
        self.app_position = self._current_safe_position()
        self._schedule_surface_refresh(80)
        self._save_settings()

    def _destroy_drag_proxy(self):
        proxy = getattr(self, "drag_proxy", None)
        if proxy is not None:
            try:
                proxy.destroy()
            except tk.TclError:
                pass
        self.drag_proxy = None
        self.drag_proxy_photo = None

    def _start_resize(self, event):
        self.resizing_main_window = True
        self._cancel_surface_refresh()
        self.resize_start_x = event.x_root
        self.resize_start_y = event.y_root
        self.resize_start_w = self.root.winfo_width()
        self.resize_start_h = self.root.winfo_height()
        self.resize_fixed_position = self._current_raw_position()
        self.app_position = self.resize_fixed_position
        return "break"

    def _resize(self, event):
        proposed_width = self.resize_start_w + event.x_root - self.resize_start_x
        proposed_height = self.resize_start_h + event.y_root - self.resize_start_y
        width, height = nearest_app_size(proposed_width, proposed_height)
        if self.app_size == (width, height):
            return "break"
        self.app_size = (width, height)
        x, y = self.resize_fixed_position or self._current_raw_position()
        self.app_position = (x, y)
        self._resize_main_window_nomove(width, height)
        self._refresh_resize_surface()
        return "break"

    def _end_resize(self, _event):
        self.app_size = nearest_app_size(self.app_size[0], self.app_size[1])
        self.app_position = self.resize_fixed_position or self._current_raw_position()
        self._resize_main_window_nomove(self.app_size[0], self.app_size[1])
        self.resizing_main_window = False
        self.resize_fixed_position = None
        self._refresh_resize_surface()
        self._save_settings()
        return "break"

    def _reset_app_size(self):
        self.app_size = DEFAULT_APP_SIZE
        self.app_position = self._current_safe_position()
        self.root.geometry(f"{DEFAULT_APP_SIZE[0]}x{DEFAULT_APP_SIZE[1]}+{self.app_position[0]}+{self.app_position[1]}")
        self.root.update_idletasks()
        self._refresh_window_surface()
        self._save_settings()

    def _toggle_topmost(self):
        self.root.attributes("-topmost", not bool(self.root.attributes("-topmost")))

    def _minimize(self):
        self._show_widget_mode()

    def _ensure_widget_window(self):
        widget = getattr(self, "widget", None)
        if widget is not None:
            try:
                if widget.winfo_exists() and getattr(self, "widget_canvas", None) is not None:
                    return True
            except tk.TclError:
                pass
        self.widget = None
        self.widget_canvas = None
        try:
            self.widget = tk.Toplevel(self.root)
            self.widget.withdraw()
            try:
                self.widget.attributes("-alpha", 0.0)
            except tk.TclError:
                pass
            self.widget.overrideredirect(True)
            self.widget.attributes("-topmost", True)
            self.widget.configure(bg=TRANSPARENT)
            try:
                self.widget.wm_attributes("-transparentcolor", TRANSPARENT)
            except tk.TclError:
                pass
            self.widget.geometry(f"{WIDGET_WIDTH}x{WIDGET_HEIGHT}+-32000+-32000")
            self._apply_window_icon(self.widget)
            self.widget_canvas = tk.Canvas(self.widget, width=WIDGET_WIDTH, height=WIDGET_HEIGHT, bg=TRANSPARENT, highlightthickness=0, bd=0, cursor="arrow")
            self.widget_canvas.pack(fill="both", expand=True)
            self.widget_canvas.bind("<ButtonPress-1>", self._start_widget_drag)
            self.widget_canvas.bind("<B1-Motion>", self._drag_widget)
            self.widget_canvas.bind("<ButtonRelease-1>", self._end_widget_drag)
            self.widget_canvas.bind("<Motion>", self._update_widget_cursor)
            self.widget_canvas.bind("<Leave>", self._reset_widget_cursor)
            self.widget.bind("<Escape>", self._restore_from_widget_mode)
            self._draw_widget_mode(force=True)
            self.widget.update_idletasks()
            return True
        except tk.TclError:
            self.widget = None
            self.widget_canvas = None
            return False

    def _show_widget_mode(self):
        self.app_position = self._current_safe_position()
        self._save_settings()
        self.widget_mode_active = True
        self._cancel_surface_refresh()
        if not self._ensure_widget_window():
            self.widget_mode_active = False
            try:
                self.root.attributes("-alpha", 1.0)
                self.root.deiconify()
            except tk.TclError:
                pass
            return
        try:
            widget_position = getattr(self, "widget_position", None) or self.app_position
            x, y = self._safe_app_position(widget_position, WIDGET_WIDTH, WIDGET_HEIGHT)
            self.widget_position = (x, y)
            self._draw_widget_mode(force=True)
            self.widget.attributes("-alpha", 0.0)
            self.widget.geometry(f"{WIDGET_WIDTH}x{WIDGET_HEIGHT}+{x}+{y}")
            self.widget.update_idletasks()
            self.root.withdraw()
            self.root.update_idletasks()
            self.root.attributes("-alpha", 0.0)
            self.widget.deiconify()
            self.widget.lift()
            self.widget.update_idletasks()
            self.widget.attributes("-alpha", 1.0)
        except tk.TclError:
            self.widget_mode_active = False
            self._hide_widget_window()
            try:
                self.root.attributes("-alpha", 1.0)
                self.root.deiconify()
            except tk.TclError:
                pass

    def _restore_from_widget_mode(self, _event=None):
        width, height = nearest_app_size(
            getattr(self, "app_size", DEFAULT_APP_SIZE)[0],
            getattr(self, "app_size", DEFAULT_APP_SIZE)[1],
        )
        self.app_size = (width, height)
        # The splash is centered using the virtual desktop bounds. Start the
        # main window from that same center so every monitor layout, taskbar
        # position, and resolution follows one coordinate system.
        self.app_position = self._center_app_position(width, height)
        self.widget_mode_active = False
        self._hide_widget_window()
        self._force_main_window_visible(force_focus=True, attempts=0)
        self._save_settings()

    def _hide_widget_window(self):
        widget = getattr(self, "widget", None)
        if widget is not None:
            try:
                widget.attributes("-alpha", 0.0)
                widget.withdraw()
                widget.geometry(f"{WIDGET_WIDTH}x{WIDGET_HEIGHT}+-32000+-32000")
            except tk.TclError:
                pass

    def _destroy_widget_mode(self):
        widget = getattr(self, "widget", None)
        if widget is not None:
            try:
                widget.destroy()
            except tk.TclError:
                pass
        self.widget = None
        self.widget_canvas = None

    def _start_widget_drag(self, event):
        self.widget_booster_press_root = None
        self.widget_coupon_press_root = None
        self.widget_count_press_root = None
        self.widget_rune_press_root = None
        if self._point_in_widget_restore(event.x, event.y):
            return "break"
        self.widget_drag_start_x = event.x_root
        self.widget_drag_start_y = event.y_root
        try:
            self.widget_window_start_x = self.widget.winfo_x()
            self.widget_window_start_y = self.widget.winfo_y()
        except tk.TclError:
            self.widget_window_start_x = self.widget_window_start_y = 0
        if self._point_in_widget_coupon(event.x, event.y):
            self.widget_coupon_press_root = (event.x_root, event.y_root)
            return "break"
        if self._point_in_widget_booster(event.x, event.y):
            self.widget_count_press_root = None
            self.widget_rune_press_root = None
            self.widget_booster_press_root = (event.x_root, event.y_root)
            return "break"
        if self._point_in_widget_count(event.x, event.y):
            self.widget_count_press_root = (event.x_root, event.y_root)
            return "break"
        self.widget_count_press_root = None
        if self._point_in_widget_rune(event.x, event.y):
            self.widget_rune_press_root = (event.x_root, event.y_root)
            return "break"
        self.widget_rune_press_root = None
        return "break"

    def _drag_widget(self, event):
        coupon_start = getattr(self, "widget_coupon_press_root", None)
        if coupon_start is not None:
            if abs(event.x_root - coupon_start[0]) <= 8 and abs(event.y_root - coupon_start[1]) <= 8:
                return "break"
            self.widget_coupon_press_root = None
        booster_start = getattr(self, "widget_booster_press_root", None)
        if booster_start is not None:
            if abs(event.x_root - booster_start[0]) <= 8 and abs(event.y_root - booster_start[1]) <= 8:
                return "break"
            self.widget_booster_press_root = None
        count_start = getattr(self, "widget_count_press_root", None)
        if count_start is not None:
            dx_abs = abs(event.x_root - count_start[0])
            dy_abs = abs(event.y_root - count_start[1])
            if dx_abs <= 8 and dy_abs <= 8:
                return "break"
            self.widget_count_press_root = None
        rune_start = getattr(self, "widget_rune_press_root", None)
        if rune_start is not None:
            dx_abs = abs(event.x_root - rune_start[0])
            dy_abs = abs(event.y_root - rune_start[1])
            if dx_abs <= 8 and dy_abs <= 8:
                return "break"
            self.widget_rune_press_root = None
        if self.widget is None:
            return "break"
        dx = event.x_root - self.widget_drag_start_x
        dy = event.y_root - self.widget_drag_start_y
        x = self.widget_window_start_x + dx
        y = self.widget_window_start_y + dy
        self.widget_position = (int(x), int(y))
        try:
            self.widget.geometry(f"{WIDGET_WIDTH}x{WIDGET_HEIGHT}+{x}+{y}")
        except tk.TclError:
            pass
        return "break"

    def _end_widget_drag(self, event):
        coupon_start = getattr(self, "widget_coupon_press_root", None)
        self.widget_coupon_press_root = None
        if coupon_start is not None:
            if (abs(event.x_root - coupon_start[0]) <= 8
                    and abs(event.y_root - coupon_start[1]) <= 8
                    and self._point_in_widget_coupon(event.x, event.y)):
                self._toggle_widget_halfhour()
            return "break"
        booster_start = getattr(self, "widget_booster_press_root", None)
        self.widget_booster_press_root = None
        if booster_start is not None:
            if (abs(event.x_root - booster_start[0]) <= 8
                    and abs(event.y_root - booster_start[1]) <= 8
                    and self._point_in_widget_booster(event.x, event.y)):
                self._toggle_booster()
            return "break"
        count_start = getattr(self, "widget_count_press_root", None)
        self.widget_count_press_root = None
        if count_start is not None:
            dx = abs(event.x_root - count_start[0])
            dy = abs(event.y_root - count_start[1])
            if dx <= 8 and dy <= 8 and self._point_in_widget_count(event.x, event.y):
                self._toggle_warning_countdown_pause()
            return "break"
        rune_start = getattr(self, "widget_rune_press_root", None)
        self.widget_rune_press_root = None
        if rune_start is not None:
            dx = abs(event.x_root - rune_start[0])
            dy = abs(event.y_root - rune_start[1])
            if dx <= 8 and dy <= 8 and self._point_in_widget_rune(event.x, event.y):
                self._handle_widget_rune_click()
            return "break"
        try:
            if self.widget is not None and self.widget.winfo_exists():
                self.widget_window_start_x = self.widget.winfo_x()
                self.widget_window_start_y = self.widget.winfo_y()
                self.widget_position = (int(self.widget_window_start_x), int(self.widget_window_start_y))
                self._save_settings()
        except tk.TclError:
            pass
        return "break"

    def _point_in_widget_restore(self, x, y):
        x1, y1, x2, y2 = getattr(self, "widget_restore_region", (0, 0, 0, 0))
        return x1 <= x <= x2 and y1 <= y <= y2

    def _point_in_widget_count(self, x, y):
        x1, y1, x2, y2 = getattr(self, "widget_count_region", (0, 0, 0, 0))
        return x1 <= x <= x2 and y1 <= y <= y2

    def _point_in_widget_rune(self, x, y):
        if not getattr(self, "offline_mode_enabled", False):
            return False
        x1, y1, x2, y2 = getattr(self, "widget_rune_region", (0, 0, 0, 0))
        return x1 <= x <= x2 and y1 <= y <= y2

    def _point_in_widget_booster(self, x, y):
        if not getattr(self, "booster_mode_enabled", False):
            return False
        x1, y1, x2, y2 = getattr(self, "widget_booster_region", (0, 0, 0, 0))
        return x1 <= x <= x2 and y1 <= y <= y2

    def _point_in_widget_coupon(self, x, y):
        if not getattr(self, "halfhour_enabled", False):
            return False
        x1, y1, x2, y2 = getattr(self, "widget_coupon_region", (0, 0, 0, 0))
        return x1 <= x <= x2 and y1 <= y <= y2

    def _update_widget_cursor(self, event):
        canvas = getattr(self, "widget_canvas", None)
        if canvas is None:
            return
        cursor = "hand2" if (
            self._point_in_widget_restore(event.x, event.y)
            or self._point_in_widget_count(event.x, event.y)
            or self._point_in_widget_rune(event.x, event.y)
            or self._point_in_widget_booster(event.x, event.y)
            or self._point_in_widget_coupon(event.x, event.y)
        ) else "arrow"
        try:
            canvas.configure(cursor=cursor)
        except tk.TclError:
            pass

    def _reset_widget_cursor(self, _event=None):
        canvas = getattr(self, "widget_canvas", None)
        if canvas is None:
            return
        try:
            canvas.configure(cursor="arrow")
        except tk.TclError:
            pass

    def _handle_widget_restore_click(self, _event=None):
        self._restore_from_widget_mode()
        return "break"

    def _handle_widget_rune_click(self, _event=None):
        if getattr(self, "offline_mode_enabled", False):
            self._reset_offline_rune_cycle()
        return "break"

    def _make_widget_background_image(self, width, height):
        image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        panel = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        pixels = panel.load()
        top = (1, 2, 5, 250)
        bottom = (5, 16, 39, 250)
        side = (9, 31, 64, 250)
        for y in range(height):
            vertical = y / max(1, height - 1)
            for x in range(width):
                horizontal = x / max(1, width - 1)
                t = max(0.0, min(1.0, vertical * 0.68 + horizontal * 0.24))
                base = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(4))
                edge = math.sin(horizontal * math.pi)
                color = tuple(int(base[i] * (1 - 0.10 * edge) + side[i] * 0.10 * edge) for i in range(4))
                pixels[x, y] = color

        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        glow_draw = ImageDraw.Draw(glow)
        glow_draw.ellipse((58, -54, 328, 104), fill=(18, 55, 105, 42))
        glow_draw.ellipse((194, 36, 424, 170), fill=(8, 42, 82, 32))
        glow_draw.rectangle((26, 8, width - 52, 30), fill=(18, 45, 80, 24))
        glow = glow.filter(ImageFilter.GaussianBlur(28))
        panel.alpha_composite(glow)

        mask = Image.new("L", (width, height), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle((1, 1, width - 2, height - 2), radius=32, fill=255)
        image.alpha_composite(Image.composite(panel, Image.new("RGBA", (width, height), (0, 0, 0, 0)), mask))

        return ImageTk.PhotoImage(image)

    def _draw_widget_restore_button(self, canvas):
        x2 = 384 - 11
        y1 = 11
        size = 27
        x1 = x2 - size
        y2 = y1 + size
        self.widget_restore_region = (x1, y1, x2, y2)
        self._canvas_rounded_rect(canvas, x1, y1, x2, y2, 5, fill="#1b2638", outline="#1b2638", width=1, tags=("widget_restore",))
        self._canvas_rounded_rect(canvas, x1 + 2, y1 + 2, x2 - 2, y2 - 2, 4, fill="#22283c", outline="#22283c", tags=("widget_restore",))
        back = (x1 + 11, y1 + 7, x1 + 22, y1 + 16)
        front = (x1 + 6, y1 + 12, x1 + 17, y1 + 21)
        self._canvas_rounded_rect(canvas, *back, 2, fill="#4a5873", outline="#aebbd3", width=2, tags=("widget_restore",))
        self._canvas_rounded_rect(canvas, *front, 2, fill="#354156", outline="#c2ccdc", width=2, tags=("widget_restore",))
        canvas.tag_bind("widget_restore", "<Button-1>", self._handle_widget_restore_click)

    def _draw_widget_mode(self, force=False):
        canvas = getattr(self, "widget_canvas", None)
        if canvas is None:
            return
        if not force and not getattr(self, "widget_mode_active", False):
            return
        c = self.colors
        canvas.delete("all")
        if getattr(self, "widget_background_photo", None) is None:
            self.widget_background_photo = self._make_widget_background_image(WIDGET_WIDTH, WIDGET_HEIGHT)
        canvas.create_image(0, 0, image=self.widget_background_photo, anchor="nw")

        self._draw_widget_restore_button(canvas)

        left_x = 112
        right_x = 274
        booster_enabled = bool(getattr(self, "booster_mode_enabled", False))
        coupon_enabled = bool(getattr(self, "halfhour_enabled", False))
        booster_x = 198
        coupon_x = 294
        self.widget_booster_region = (0, 0, 0, 0)
        self.widget_coupon_region = (0, 0, 0, 0)
        self.widget_coupon_text_item = None
        if booster_enabled:
            left_x, right_x = 88, 294
        if coupon_enabled:
            if booster_enabled:
                left_x, booster_x, right_x, coupon_x = 60, 150, 234, 316
            else:
                left_x, right_x, coupon_x = 88, 198, 294
        center_y = 68
        rune_y = 58

        rune_size = 17
        self.widget_rune_region = (left_x - 36, rune_y - 36, left_x + 36, rune_y + 36)
        blink_on = getattr(self, "rune_blink_on", True)
        if getattr(self, "rune_active_visual", False) and not blink_on:
            rune_fill = "#12382b"
        else:
            rune_fill = "#4af1ae"
        canvas.create_polygon(
            left_x, rune_y - rune_size,
            left_x + rune_size, rune_y,
            left_x, rune_y + rune_size,
            left_x - rune_size, rune_y,
            fill=rune_fill,
            outline="",
            width=0,
        )
        elapsed_minutes, total_minutes = self._rune_cooldown_display_pair()
        widget_value_font = self._settings_font(10, "bold")
        value_y = 94
        canvas.create_text(left_x, value_y, text=f"{elapsed_minutes} / {total_minutes}", fill="#eef3f4", font=widget_value_font, anchor="center")

        display_seconds = max(0, int(self._warning_remaining_float() + 0.999))
        number_fill = "#ffffff"
        self.widget_count_region = (right_x - 58, center_y - 38, right_x + 58, value_y + 22)
        if booster_enabled:
            self.widget_count_region = (right_x - 44, center_y - 38, right_x + 44, value_y + 22)
            self.widget_booster_region = (booster_x - 28, 40, booster_x + 28, 112)
            self._draw_booster_icon(canvas, booster_x, rune_y, rune_size)
            self.widget_booster_text_item = canvas.create_text(
                booster_x, value_y, text=str(getattr(self, "booster_remaining", 100)),
                fill="#ffffff",
                font=widget_value_font, anchor="center")
        if coupon_enabled:
            self.widget_count_region = (right_x - 32, 40, right_x + 32, value_y + 22)
            self.widget_coupon_region = (coupon_x - 32, 40, coupon_x + 32, value_y + 22)
            self._canvas_rounded_rect(canvas, coupon_x - 14, rune_y - 14,
                                      coupon_x + 14, rune_y + 14, 6,
                                      fill="#9ff7d2", outline="#9ff7d2", width=3,
                                      tags=("widget_coupon_icon",))
            self.widget_coupon_text_item = canvas.create_text(
                coupon_x, value_y,
                text=str(max(0, math.ceil(getattr(self, "halfhour_remaining", 1800) / 60))),
                fill="#ffffff", font=widget_value_font, anchor="center",
                tags=("widget_coupon_minutes",))
        # Show the available action; icon and number share a hit target.
        if not getattr(self, "warning_timer_paused", False):
            for offset in (-9, 3):
                canvas.create_rectangle(right_x + offset, rune_y - 14,
                                        right_x + offset + 6, rune_y + 14,
                                        fill="#e0fcf0", outline="", tags="widget_count_state")
        else:
            canvas.create_polygon(right_x - 10, rune_y - 16,
                                  right_x - 10, rune_y + 16,
                                  right_x + 16, rune_y,
                                  fill="#e0fcf0", outline="", tags="widget_count_state")
        self.widget_count_text_item = canvas.create_text(right_x, value_y, text=str(display_seconds), fill=number_fill, font=widget_value_font, anchor="center")

        if LOW_RES:
            factor = WIDGET_WIDTH / 384
            for item in canvas.find_all():
                if canvas.type(item) != "image":
                    canvas.scale(item, 0, 0, factor, factor)
            for name in ("widget_restore_region", "widget_count_region", "widget_rune_region", "widget_booster_region", "widget_coupon_region"):
                setattr(self, name, tuple(v * factor for v in getattr(self, name)))

    def _update_widget_timer_display_lightweight(self, now=None):
        if not getattr(self, "widget_mode_active", False):
            return
        canvas = getattr(self, "widget_canvas", None)
        if canvas is None:
            return
        item = getattr(self, "widget_count_text_item", None)
        if item is None:
            self._draw_widget_mode(force=True)
            return
        now = time.monotonic() if now is None else now
        display_seconds = max(0, int(self._warning_remaining_float(now) + 0.999))
        number_fill = "#ffffff"
        try:
            canvas.itemconfigure(item, text=str(display_seconds), fill=number_fill)
            if getattr(self, "halfhour_enabled", False):
                coupon_item = getattr(self, "widget_coupon_text_item", None)
                if coupon_item is not None:
                    canvas.itemconfigure(coupon_item,
                        text=str(max(0, math.ceil(getattr(self, "halfhour_remaining", 1800) / 60))),
                        fill="#ffffff")
            if getattr(self, "booster_mode_enabled", False):
                booster_item = getattr(self, "widget_booster_text_item", None)
                if booster_item is not None:
                    canvas.itemconfigure(booster_item,
                                         text=str(getattr(self, "booster_remaining", 100)),
                                         fill="#ffffff")
        except tk.TclError:
            self.widget_count_text_item = None
            self._draw_widget_mode(force=True)

    def _restore_borderless(self, _event=None):
        try:
            if self.root.state() == "normal":
                self.root.after(50, lambda: self._show_main_window(force_focus=True))
        except tk.TclError:
            pass

    def _toggle(self):
        self._stop() if self.running else self._start()

    def _start(self):
        self._sync_timer_rows_to_model()
        if hasattr(self, "session_var"):
            self.session_seconds = clamp_int(self.session_var.get(), self.session_seconds // 60, 1, 24*60) * 60
        now = time.monotonic()
        self.session_remaining = self.session_seconds
        self.session_deadline = now + self.session_seconds
        self.session_cycles = 0
        for timer in self.timers:
            timer.reset(now)
        self.running = True
        if hasattr(self, "start_button"):
            self.start_button.configure_style("■", self.colors["orange"], self.colors["surface"], self.colors["orange_hover"])
        self._save_settings()
        self._render()

    def _stop(self):
        self.running = False
        if hasattr(self, "start_button"):
            self.start_button.configure_style("시작", self.colors["blue"], self.colors["surface"], self.colors["blue_hover"])
        self._render()

    def _sound_loop(self):
        while True:
            item = self.sound_queue.get()
            if isinstance(item, tuple):
                if len(item) >= 3:
                    key, path, volume = item[:3]
                else:
                    key, path = item
                    volume = self._sound_volume_for_key(key)
            else:
                key = item
                path = self.sound_paths.get(key)
                volume = self._sound_volume_for_key(key)
            if path:
                try:
                    # A map change can mute an automatic rune alert after it
                    # was queued. Recheck immediately before playback.
                    if key == "rune" and not self._sound_enabled_for_key(key):
                        continue
                    if str(path).lower().endswith(".mp3"):
                        self._play_mp3(path, volume)
                    else:
                        winsound.PlaySound(str(path), winsound.SND_FILENAME)
                except Exception as exc:
                    log_error("sound_playback", exc)
                finally:
                    self.sound_queue.task_done()
            else:
                self.sound_queue.task_done()

    def _play(self, key):
        if not self._sound_enabled_for_key(key):
            return
        volume = self._sound_volume_for_key(key)
        if volume <= 0:
            return
        if key in ("rune", "warning"):
            self._clear_queued_sound(key)
        source = self._sound_source_path(key)
        self.sound_queue.put((key, self._volume_adjusted_sound_path(key, volume, source), volume))

    def _sound_source_path(self, key):
        if bool(getattr(self, "tts_sound_enabled", False)):
            if key == "warning":
                tts = self.sound_paths.get("warning_tts")
                if tts and Path(tts).exists():
                    return tts
            if key == "rune":
                tts = self.sound_paths.get("rune_tts")
                if tts and Path(tts).exists():
                    return tts
        return self.sound_paths.get(key)

    def _sound_enabled_for_key(self, key):
        if key == "warning":
            return bool(getattr(self, "warning_sound_enabled", True))
        if key == "rune":
            return bool(getattr(self, "rune_sound_enabled", True))
        return True

    def _sound_volume_for_key(self, key):
        if key == "warning":
            return int(getattr(self, "warning_volume", 100))
        if key == "rune":
            return int(getattr(self, "rune_volume", 100))
        return 100

    def _volume_adjusted_sound_path(self, key, volume, original=None):
        volume = int(max(0, min(100, volume)))
        original = original or self.sound_paths.get(key)
        if original is None or volume >= 100:
            return original
        if str(original).lower().endswith(".mp3"):
            return original
        cache_key = (key, str(original), volume)
        cached = self.sound_volume_cache.get(cache_key)
        if cached and cached.exists():
            return cached
        adjusted = SOUND_DIR / f"{Path(original).stem}_{key}_volume_{volume}.wav"
        try:
            with wave.open(str(original), "rb") as src:
                params = src.getparams()
                frames = src.readframes(src.getnframes())
            factor = volume / 100.0
            scaled = bytearray()
            for index in range(0, len(frames), 2):
                sample = struct.unpack("<h", frames[index:index + 2])[0]
                scaled.extend(struct.pack("<h", int(sample * factor)))
            with wave.open(str(adjusted), "wb") as dst:
                dst.setparams(params)
                dst.writeframes(scaled)
            self.sound_volume_cache[cache_key] = adjusted
            return adjusted
        except Exception:
            return original

    def _play_mp3(self, path, volume=100):
        if not sys.platform.startswith("win"):
            return
        safe_path = str(path).replace('"', "")
        alias = f"rune_timer_sound_{threading.get_ident()}_{int(time.time() * 1000)}"
        volume = int(max(0, min(1000, int(volume) * 10)))
        try:
            ctypes.windll.winmm.mciSendStringW(f'open "{safe_path}" type mpegvideo alias {alias}', None, 0, None)
            ctypes.windll.winmm.mciSendStringW(f"setaudio {alias} volume to {volume}", None, 0, None)
            ctypes.windll.winmm.mciSendStringW(f"play {alias} wait", None, 0, None)
        finally:
            try:
                ctypes.windll.winmm.mciSendStringW(f"close {alias}", None, 0, None)
            except Exception:
                pass

    def _clear_queued_sound(self, key):
        with self.sound_queue.mutex:
            kept = deque()
            removed = 0
            for queued_key in self.sound_queue.queue:
                queued_name = queued_key[0] if isinstance(queued_key, tuple) else queued_key
                if queued_name == key:
                    removed += 1
                else:
                    kept.append(queued_key)
            self.sound_queue.queue = kept
            if removed:
                self.sound_queue.unfinished_tasks = max(0, self.sound_queue.unfinished_tasks - removed)
                self.sound_queue.all_tasks_done.notify_all()

    def _select_region(self):
        RegionSelector(self.root, self._set_region, "전체 감지 영역을 드래그하세요 · Esc 취소")

    def _select_rune_region(self):
        self._hide_for_region_selection()
        RegionSelector(self.root, self._set_rune_region, "미니맵 전체와 흰 테두리 바깥 여백까지 넓게 드래그 · Esc 취소", self._restore_after_region_selection)

    def _hide_for_region_selection(self):
        try:
            self.app_position = self._current_safe_position()
            self._capture_restore_blur_image()
            self.root.overrideredirect(False)
            self.root.iconify()
        except tk.TclError:
            pass

    def _restore_after_region_selection(self):
        self.root.after(120, self._restore_region_selection_window)

    def _restore_region_selection_window(self):
        try:
            try:
                self.root.attributes("-alpha", 0.0)
            except tk.TclError:
                pass
            self._show_main_window(alpha=0.0, force_focus=True)
            self.root.update_idletasks()
            try:
                self.root.attributes("-alpha", 1.0)
            except tk.TclError:
                pass
            self.root.update_idletasks()
            self._capture_restore_blur_image()
            self._show_restore_blur_overlay()
        except tk.TclError:
            pass

    def _capture_restore_blur_image(self):
        self.restore_blur_pil = None
        try:
            self.root.update_idletasks()
            x = int(self.root.winfo_rootx())
            y = int(self.root.winfo_rooty())
            width = max(1, int(self.root.winfo_width()))
            height = max(1, int(self.root.winfo_height()))
            original = ImageGrab.grab(bbox=(x, y, x + width, y + height)).convert("RGBA")
            image = original.filter(ImageFilter.GaussianBlur(12))
            image.alpha_composite(Image.new("RGBA", image.size, (0, 0, 0, 42)))
            clear_top = min(height, RESTORE_BLUR_CLEAR_TOP)
            if clear_top > 0:
                image.paste(original.crop((0, 0, width, clear_top)), (0, 0))
            self.restore_blur_pil = self._clip_restore_blur_to_app_shape(image)
        except Exception:
            self.restore_blur_pil = self._make_restore_blur_fallback()

    def _clip_restore_blur_to_app_shape(self, image):
        width, height = image.size
        scale = 4
        mask = Image.new("L", (width * scale, height * scale), 0)
        mask_draw = ImageDraw.Draw(mask)
        mask_draw.rounded_rectangle(
            (8 * scale, 8 * scale, (width - 14) * scale, (height - 14) * scale),
            radius=28 * scale,
            fill=255,
        )
        mask = mask.resize((width, height), Image.Resampling.LANCZOS)
        # Tk's transparent-color path blends semi-transparent edge pixels against
        # the magenta key color, which can leave a purple rim during the blur fade.
        mask = mask.point(lambda value: 255 if value >= 128 else 0)
        clipped = Image.new("RGBA", image.size, (0, 0, 0, 0))
        clipped.alpha_composite(image)
        clipped.putalpha(ImageChops.multiply(clipped.getchannel("A"), mask))
        return clipped

    def _make_restore_blur_fallback(self):
        width = max(1, int(self.app_size[0] if self.app_size else APP_WIDTH))
        height = max(1, int(self.app_size[1] if self.app_size else APP_HEIGHT))
        image = Image.new("RGBA", (width, height), (0, 0, 0, 255))
        glow = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(glow)
        draw.ellipse((int(width * 0.22), int(height * 0.18), int(width * 0.82), int(height * 0.76)), fill=(19, 242, 174, 26))
        glow = glow.filter(ImageFilter.GaussianBlur(82))
        image.alpha_composite(glow)
        clear_top = min(height, RESTORE_BLUR_CLEAR_TOP)
        if clear_top > 0:
            ImageDraw.Draw(image).rectangle((0, 0, width, clear_top), fill=(18, 19, 20, 255))
        return self._clip_restore_blur_to_app_shape(image)

    def _show_restore_blur_overlay(self):
        self._destroy_restore_blur_overlay()
        try:
            width = max(1, int(self.root.winfo_width()))
            height = max(1, int(self.root.winfo_height()))
            x = int(self.root.winfo_x())
            y = int(self.root.winfo_y())
            image = getattr(self, "restore_blur_pil", None) or self._make_restore_blur_fallback()
            if image.size != (width, height):
                image = image.resize((width, height), Image.Resampling.LANCZOS)
            self.restore_blur_photo = ImageTk.PhotoImage(image)
            overlay = tk.Toplevel(self.root)
            overlay.overrideredirect(True)
            overlay.attributes("-topmost", True)
            overlay.attributes("-alpha", 0.96)
            overlay.geometry(f"{width}x{height}+{x}+{y}")
            overlay.configure(bg=TRANSPARENT)
            try:
                overlay.wm_attributes("-transparentcolor", TRANSPARENT)
            except tk.TclError:
                pass
            self._apply_rounded_window(overlay, width, height, 36)
            canvas = tk.Canvas(overlay, width=width, height=height, bg=TRANSPARENT, highlightthickness=0, bd=0)
            canvas.pack(fill="both", expand=True)
            canvas.create_image(0, 0, image=self.restore_blur_photo, anchor="nw")
            self.restore_blur_overlay = overlay
            overlay.lift()
            overlay.update_idletasks()
            self.root.after(10, self._raise_restore_blur_overlay)
            self.root.after(RESTORE_BLUR_HOLD_MS, lambda: self._fade_restore_blur_overlay(0.80))
        except tk.TclError:
            self._destroy_restore_blur_overlay()

    def _raise_restore_blur_overlay(self):
        overlay = getattr(self, "restore_blur_overlay", None)
        if overlay is None:
            return
        try:
            overlay.lift()
            overlay.attributes("-topmost", True)
        except tk.TclError:
            pass

    def _fade_restore_blur_overlay(self, alpha):
        overlay = getattr(self, "restore_blur_overlay", None)
        if overlay is None:
            return
        try:
            if alpha <= 0.05:
                self._destroy_restore_blur_overlay()
                return
            overlay.attributes("-alpha", alpha)
            self.root.after(
                RESTORE_BLUR_FADE_STEP_MS,
                lambda: self._fade_restore_blur_overlay(alpha - RESTORE_BLUR_FADE_STEP_ALPHA),
            )
        except tk.TclError:
            self._destroy_restore_blur_overlay()

    def _destroy_restore_blur_overlay(self):
        overlay = getattr(self, "restore_blur_overlay", None)
        if overlay is not None:
            try:
                overlay.destroy()
            except tk.TclError:
                pass
        self.restore_blur_overlay = None

    def _set_region(self, region):
        self.region = region
        self.last_capture = None
        self.last_blue_mask = None
        self.blue_baseline_score = None
        self.last_blue_damage_score = None
        self.blue_presence_seen = False
        self.blue_event_seen = False
        self.rune_baseline_score = None
        self.last_motion_at = time.monotonic()
        self.warning_timer_paused = True
        self.warning_paused_remaining = self.warning_loop_seconds
        self.stall_alert_latched = False
        self.rune_alert_latched = False
        self.last_stall_alert_at = self.last_motion_at
        self.last_rune_alert_at = 0.0
        self._clear_queued_sound("rune")
        self._set_rune_visual(False)
        self._save_settings()
        self._render_monitor_status()

    def _set_rune_region(self, region):
        self.rune_region = region
        self.last_rune_window_sync_at = 0.0
        self._set_rune_capture_active(not getattr(self, "offline_mode_enabled", False))
        self._bind_rune_region_to_maplestory_window()
        self.rune_score = 0.0
        self.rune_baseline_score = None
        self.rune_alert_latched = False
        self.last_rune_alert_at = 0.0
        self._clear_queued_sound("rune")
        self._set_rune_visual(False)
        self._save_settings()
        self._render_monitor_status()

    def _auto_detect_minimap_loop(self):
        if not self.auto_detect_enabled or getattr(self, "offline_mode_enabled", False):
            return
        self._start_auto_detect_worker(show_notice=True)
        self.root.after(self.auto_detect_interval_ms, self._auto_detect_minimap_loop)

    def _get_app_rect(self):
        try:
            self.root.update_idletasks()
            app_x1 = self.root.winfo_rootx()
            app_y1 = self.root.winfo_rooty()
            return (app_x1, app_y1, app_x1 + self.root.winfo_width(), app_y1 + self.root.winfo_height())
        except tk.TclError:
            return None

    def _start_auto_detect_worker(self, show_notice=False):
        if not self.auto_detect_enabled or getattr(self, "offline_mode_enabled", False):
            return
        if self.auto_detect_worker_running:
            return
        self.auto_detect_worker_running = True
        width = self.root.winfo_screenwidth()
        height = self.root.winfo_screenheight()
        app_rect = self._get_app_rect()
        old_region = self.rune_region
        threading.Thread(
            target=self._auto_detect_worker,
            args=(width, height, app_rect, old_region, show_notice),
            daemon=True,
        ).start()

    def _auto_detect_worker(self, width, height, app_rect, old_region, show_notice):
        result = {"show_notice": show_notice, "detected": None, "keeps_old": False, "error": False}
        try:
            screen = self._grab_screen_frame((width, height))
            if screen is None:
                result["error"] = True
            else:
                screen = self._mask_captured_region(screen, (0, 0, screen.size[0], screen.size[1]), app_rect)
                detected = self._find_minimap_region(screen)
                result["detected"] = detected
                if not detected and old_region:
                    result["keeps_old"] = self._region_still_looks_like_minimap(screen, old_region)
        except Exception:
            result["error"] = True
        self.worker_results.put(("auto_detect", result))

    def _auto_detect_minimap_region(self, show_notice=False):
        if getattr(self, "offline_mode_enabled", False):
            return
        try:
            screen = self._grab_screen_frame()
            if screen is None:
                self._set_auto_detect_status("화면 캡쳐 실패")
                return
            screen = self._mask_own_window(screen, (0, 0, screen.size[0], screen.size[1]))
            detected = self._find_minimap_region(screen)
            if detected:
                if self._region_changed(self.rune_region, detected):
                    self._set_rune_region(detected)
                self._set_rune_capture_active(True)
                self.last_auto_detect_region = detected
                self.auto_detect_notice_shown = False
                self._set_auto_detect_status("미니맵 자동탐지 완료")
            else:
                if self.rune_region and self._region_still_looks_like_minimap(screen, self.rune_region):
                    self._set_rune_capture_active(True)
                    self._set_auto_detect_status("기존 미니맵 영역 사용 중")
                    return
                self._set_rune_capture_active(False)
                self.rune_region = None
                self.rune_score = 0.0
                self.rune_alert_latched = False
                self.last_rune_alert_at = 0.0
                self._clear_queued_sound("rune")
                self._save_settings()
                self._set_auto_detect_status("룬영역을 지정해주세요")
                if show_notice and not self.auto_detect_notice_shown:
                    self.auto_detect_notice_shown = True
                    self.root.after(100, lambda: messagebox.showinfo(APP_NAME, "미니맵을 자동으로 찾지 못했습니다.\n룬영역을 지정해주세요."))
        except Exception:
            self._set_rune_capture_active(False)
            self._set_auto_detect_status("룬영역을 지정해주세요")

    def _set_auto_detect_status(self, text):
        display_text = text
        if text in ("미니맵 자동탐지 대기", "기존 미니맵 영역 사용 중", "룬영역을 지정해주세요"):
            display_text = "수동 지정 대기" if not self.rune_region else "수동 영역 사용 중"
        elif text == "미니맵 자동탐지 완료":
            display_text = "수동 영역 사용 중"
        elif text == "미니맵 다시 찾는 중":
            display_text = "미니맵 지정 필요"
        if self.auto_detect_status_var is not None:
            self.auto_detect_status_var.set(display_text)
        active = "룬이 등장" in text
        rune_cleared = (not active) and bool(getattr(self, "rune_active_visual", False)) and text == "기존 미니맵 영역 사용 중"
        self._set_rune_visual(active, rune_cleared=rune_cleared)
        if hasattr(self, "auto_detect_status_label"):
            self.auto_detect_status_label.configure(fg=self.colors["blue"] if active else self.colors["muted"])
            self._draw_rune_diamond(active=active)

    def _region_changed(self, old_region, new_region):
        if not old_region:
            return True
        if not new_region:
            return False
        return max(abs(int(a) - int(b)) for a, b in zip(old_region, new_region)) >= 18

    def _process_image_name(self, pid):
        if not sys.platform.startswith("win"):
            return ""
        handle = None
        try:
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, int(pid))
            if not handle:
                return ""
            buffer = ctypes.create_unicode_buffer(32768)
            size = wintypes.DWORD(len(buffer))
            if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return buffer.value
        except Exception:
            return ""
        finally:
            if handle:
                try:
                    ctypes.windll.kernel32.CloseHandle(handle)
                except Exception:
                    pass
        return ""

    def _window_rect(self, hwnd):
        if not sys.platform.startswith("win"):
            return None

        class Rect(ctypes.Structure):
            _fields_ = [
                ("left", ctypes.c_long),
                ("top", ctypes.c_long),
                ("right", ctypes.c_long),
                ("bottom", ctypes.c_long),
            ]

        rect = Rect()
        try:
            if ctypes.windll.dwmapi.DwmGetWindowAttribute(hwnd, 9, ctypes.byref(rect), ctypes.sizeof(rect)) == 0:
                if rect.right > rect.left and rect.bottom > rect.top:
                    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:
            pass
        try:
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                if rect.right > rect.left and rect.bottom > rect.top:
                    return (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        except Exception:
            pass
        return None

    def _find_maplestory_windows(self):
        if not sys.platform.startswith("win"):
            return []
        user32 = ctypes.windll.user32
        windows = []
        enum_proc_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

        def enum_proc(hwnd, _lparam):
            try:
                if not user32.IsWindowVisible(hwnd) or user32.IsIconic(hwnd):
                    return True
                pid = wintypes.DWORD()
                user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                process_path = self._process_image_name(pid.value)
                process_name = Path(process_path).name.lower() if process_path else ""
                title_len = user32.GetWindowTextLengthW(hwnd)
                title_buffer = ctypes.create_unicode_buffer(title_len + 1)
                user32.GetWindowTextW(hwnd, title_buffer, title_len + 1)
                title = title_buffer.value
                title_matches = "maplestory" in title.lower()
                if process_name not in MAPLE_PROCESS_NAMES and not title_matches:
                    return True
                rect = self._window_rect(hwnd)
                if not rect:
                    return True
                x1, y1, x2, y2 = rect
                if x2 - x1 < 320 or y2 - y1 < 240:
                    return True
                windows.append({
                    "hwnd": int(hwnd),
                    "pid": int(pid.value),
                    "process_name": process_name or "maplestory.exe",
                    "title": title,
                    "rect": rect,
                })
            except Exception:
                pass
            return True

        try:
            user32.EnumWindows(enum_proc_type(enum_proc), 0)
        except Exception:
            return []
        return windows

    def _find_maplestory_window_for_region(self, region=None):
        windows = self._find_maplestory_windows()
        if not windows:
            return None
        if not region:
            return windows[0]
        try:
            rx1, ry1, rx2, ry2 = [int(v) for v in region]
        except (TypeError, ValueError):
            return windows[0]
        center_x = (rx1 + rx2) / 2
        center_y = (ry1 + ry2) / 2

        def score(window):
            wx1, wy1, wx2, wy2 = window["rect"]
            overlap_w = max(0, min(rx2, wx2) - max(rx1, wx1))
            overlap_h = max(0, min(ry2, wy2) - max(ry1, wy1))
            overlap = overlap_w * overlap_h
            contains_center = wx1 <= center_x <= wx2 and wy1 <= center_y <= wy2
            area = max(1, (wx2 - wx1) * (wy2 - wy1))
            return (1 if contains_center else 0, overlap, -area)

        best = max(windows, key=score)
        return best if score(best)[0] or score(best)[1] > 0 else None

    def _bind_rune_region_to_maplestory_window(self):
        if not self.rune_region:
            self.rune_window_anchor = None
            return False
        window = self._find_maplestory_window_for_region(self.rune_region)
        if not window:
            self.rune_window_anchor = None
            return False
        wx1, wy1, wx2, wy2 = window["rect"]
        rx1, ry1, rx2, ry2 = [int(v) for v in self.rune_region]
        self.rune_window_anchor = {
            "pid": window["pid"],
            "process_name": window["process_name"],
            "window_rect": [wx1, wy1, wx2, wy2],
            "relative_region": [rx1 - wx1, ry1 - wy1, rx2 - wx1, ry2 - wy1],
        }
        return True

    def _sync_rune_region_to_maplestory_window(self):
        anchor = getattr(self, "rune_window_anchor", None)
        if not self.rune_region:
            return False
        if not anchor:
            if not self._bind_rune_region_to_maplestory_window():
                return False
            anchor = getattr(self, "rune_window_anchor", None)
            if not anchor:
                return False
        windows = self._find_maplestory_windows()
        if not windows:
            return False
        target_pid = int(anchor.get("pid") or 0)
        window = next((item for item in windows if item["pid"] == target_pid), None) or windows[0]
        base_rect = anchor.get("window_rect") or []
        relative_region = anchor.get("relative_region") or []
        if len(base_rect) != 4 or len(relative_region) != 4:
            return False
        base_w = max(1, int(base_rect[2]) - int(base_rect[0]))
        base_h = max(1, int(base_rect[3]) - int(base_rect[1]))
        wx1, wy1, wx2, wy2 = window["rect"]
        current_w = max(1, wx2 - wx1)
        current_h = max(1, wy2 - wy1)
        scale_x = current_w / base_w
        scale_y = current_h / base_h
        new_region = (
            int(round(wx1 + float(relative_region[0]) * scale_x)),
            int(round(wy1 + float(relative_region[1]) * scale_y)),
            int(round(wx1 + float(relative_region[2]) * scale_x)),
            int(round(wy1 + float(relative_region[3]) * scale_y)),
        )
        if new_region[2] - new_region[0] < 24 or new_region[3] - new_region[1] < 24:
            return False
        if max(abs(int(a) - int(b)) for a, b in zip(self.rune_region, new_region)) >= 2:
            self.rune_region = new_region
            self.last_capture = None
            self.rune_baseline_score = None
            self._draw_bottom_dock()
        return True

    def _region_still_looks_like_minimap(self, screen, region):
        try:
            x1, y1, x2, y2 = [int(v) for v in region]
            width, height = screen.size
            x1 = max(0, min(width - 1, x1))
            y1 = max(0, min(height - 1, y1))
            x2 = max(x1 + 1, min(width, x2))
            y2 = max(y1 + 1, min(height, y2))
            crop = screen.crop((x1, y1, x2, y2))
            return self._crop_minimap_view(crop) is not None
        except Exception:
            return False

    def _grab_screen_frame(self, size=None):
        if size is None:
            width = self.root.winfo_screenwidth()
            height = self.root.winfo_screenheight()
        else:
            width, height = size
        return self._grab_frame((0, 0, width, height))

    def _release_capture_camera_unlocked(self):
        """capture_lock을 이미 잡은 상태에서만 호출."""
        camera = self.capture_camera
        self.capture_camera = None
        if camera is None:
            return
        for method_name in ("stop", "release", "close"):
            method = getattr(camera, method_name, None)
            if callable(method):
                try:
                    method()
                except Exception as exc:
                    log_error(f"dxcam_{method_name}", exc)

    def _release_capture_camera(self):
        with self.capture_lock:
            self._release_capture_camera_unlocked()

    def _grab_frame(self, region):
        if getattr(self, "offline_mode_enabled", False):
            return None
        with self.capture_lock:
            if dxcam is not None:
                now = time.monotonic()
                retry_at = getattr(self, "_dxcam_retry_at", 0.0)
                try:
                    if self.capture_camera is None and now >= retry_at:
                        self.capture_camera = dxcam.create(output_color="RGB")
                        if self.capture_camera is None:
                            self._dxcam_retry_at = now + 10.0
                            log_error("dxcam_create_none")
                    if self.capture_camera is not None:
                        frame = self.capture_camera.grab(region=tuple(region))
                        if frame is not None:
                            expected_w = max(1, int(region[2] - region[0]))
                            expected_h = max(1, int(region[3] - region[1]))
                            if frame.shape[1] != expected_w or frame.shape[0] != expected_h:
                                raise RuntimeError("capture size changed")
                            return Image.fromarray(frame).convert("RGB")
                except Exception as exc:
                    log_error("dxcam_grab", exc)
                    self._release_capture_camera_unlocked()
                    self._dxcam_retry_at = now + 5.0
            return ImageGrab.grab(bbox=region).convert("RGB")

    def _find_minimap_region(self, image):
        width, height = image.size
        if width > 520 or height > 420:
            scale = min(520 / width, 420 / height)
            scaled_size = (max(1, int(width * scale)), max(1, int(height * scale)))
            scaled = image.resize(scaled_size, Image.Resampling.BILINEAR)
            detected = self._find_minimap_region(scaled)
            if not detected:
                return None
            x1, y1, x2, y2 = detected
            return (
                max(0, int(x1 / scale)),
                max(0, int(y1 / scale)),
                min(width, int(x2 / scale)),
                min(height, int(y2 / scale)),
            )
        if width < 120 or height < 90:
            return None
        pixels = image.load()
        min_run = max(42, int(width * 0.045))
        max_run = min(720, int(width * 0.90))
        runs = []
        for y in range(6, height - 6):
            x = 0
            while x < width:
                while x < width:
                    r, g, b = pixels[x, y]
                    neutral_white = r >= 198 and g >= 198 and b >= 198 and max(r, g, b) - min(r, g, b) <= 42
                    if neutral_white:
                        break
                    x += 1
                start = x
                while x < width:
                    r, g, b = pixels[x, y]
                    neutral_white = r >= 198 and g >= 198 and b >= 198 and max(r, g, b) - min(r, g, b) <= 42
                    if not neutral_white:
                        break
                    x += 1
                run_len = x - start
                if min_run <= run_len <= max_run and 4 < start < width - 8:
                    runs.append((y, start, x - 1, run_len))

        grouped_runs = []
        for y, x1, x2, run_len in runs:
            if grouped_runs:
                last = grouped_runs[-1]
                if y - last["last_y"] <= 3 and abs(x1 - last["x1"]) <= 10 and abs(x2 - last["x2"]) <= 10:
                    last["ys"].append(y)
                    last["x1"] = min(last["x1"], x1)
                    last["x2"] = max(last["x2"], x2)
                    last["last_y"] = y
                    last["run_len"] = max(last["run_len"], run_len)
                    continue
            grouped_runs.append({"ys": [y], "last_y": y, "x1": x1, "x2": x2, "run_len": run_len})
        runs = [
            (int(sum(group["ys"]) / len(group["ys"])), group["x1"], group["x2"], group["run_len"])
            for group in grouped_runs
            if len(group["ys"]) >= 1
        ]
        if len(runs) > 70:
            runs = sorted(runs, key=lambda run: run[3], reverse=True)[:70]
            runs.sort()

        best = None
        for i, top in enumerate(runs):
            y1, tx1, tx2, tlen = top
            for bottom in runs[i + 1:]:
                y2, bx1, bx2, blen = bottom
                box_h = y2 - y1
                if not (48 <= box_h <= 250):
                    continue
                x1 = max(tx1, bx1)
                x2 = min(tx2, bx2)
                box_w = x2 - x1 + 1
                if not (60 <= box_w <= max_run):
                    continue
                if abs(tx1 - bx1) + abs(tx2 - bx2) > max(46, box_w * 0.28):
                    continue
                aspect = box_w / box_h
                if not (1.15 <= aspect <= 4.8):
                    continue

                ix1 = max(0, x1 + 5)
                iy1 = max(0, y1 + 5)
                ix2 = min(width, x2 - 5)
                iy2 = min(height, y2 - 5)
                if ix2 <= ix1 or iy2 <= iy1:
                    continue
                crop = image.crop((ix1, iy1, ix2, iy2))
                total = crop.size[0] * crop.size[1]
                if total <= 0:
                    continue

                dark = saturated = muted_line = bright_noise = 0
                sum_luma = 0
                for r, g, b in crop.getdata():
                    luma = (r * 30 + g * 59 + b * 11) / 100
                    sum_luma += luma
                    if luma < 78 and max(r, g, b) < 150:
                        dark += 1
                    if max(r, g, b) - min(r, g, b) >= 60 and max(r, g, b) >= 120:
                        saturated += 1
                    if 70 <= luma <= 170 and max(r, g, b) - min(r, g, b) <= 55:
                        muted_line += 1
                    if luma > 210:
                        bright_noise += 1

                dark_ratio = dark / total
                saturated_ratio = saturated / total
                muted_ratio = muted_line / total
                bright_ratio = bright_noise / total
                avg_luma = sum_luma / total
                if dark_ratio < 0.26 or avg_luma > 138 or bright_ratio > 0.22:
                    continue

                top_bias = 1.0 - min(0.45, y1 / max(1, height)) * 0.35
                size_score = min(1.0, box_w / 180.0) * min(1.0, box_h / 90.0)
                darkness_score = min(1.0, dark_ratio / 0.48)
                icon_score = min(1.0, saturated_ratio / 0.012)
                line_score = min(1.0, muted_ratio / 0.20)
                aspect_score = 1.0 - min(0.55, abs(aspect - 2.25) / 3.0)
                score = 100.0 * top_bias * (0.35 * darkness_score + 0.25 * icon_score + 0.20 * line_score + 0.20 * aspect_score) * size_score

                region = (
                    max(0, x1 - 10),
                    max(0, y1 - 10),
                    min(width, x2 + 10),
                    min(height, y2 + 10),
                )
                if best is None or score > best[0]:
                    best = (score, region)

        if best and best[0] >= 28.0:
            return best[1]
        return None

    def _toggle_monitor(self):
        self.monitor_enabled = not self.monitor_enabled
        self.last_capture = None
        self.last_blue_mask = None
        self.blue_baseline_score = None
        self.last_blue_damage_score = None
        self.blue_presence_seen = False
        self.blue_event_seen = False
        self.rune_baseline_score = None
        self.last_motion_at = time.monotonic()
        self.stall_alert_latched = False
        self.rune_alert_latched = False
        self.last_stall_alert_at = self.last_motion_at
        self.last_rune_alert_at = 0.0
        self._clear_queued_sound("rune")
        self._save_settings()
        self._render_monitor_status()

    def _set_warning_sound_enabled(self, value):
        self.warning_sound_enabled = bool(value)
        if hasattr(self, "warning_sound_var"):
            self.warning_sound_var.set(self.warning_sound_enabled)
        if not self.warning_sound_enabled:
            self._clear_queued_sound("warning")
        self._save_settings()

    def _set_rune_sound_enabled(self, value):
        self.rune_sound_enabled = bool(value)
        if hasattr(self, "rune_sound_var"):
            self.rune_sound_var.set(self.rune_sound_enabled)
        if not self.rune_sound_enabled:
            self._clear_queued_sound("rune")
        self._save_settings()

    def _set_tts_sound_enabled(self, value):
        self.tts_sound_enabled = bool(value)
        if hasattr(self, "tts_sound_var"):
            self.tts_sound_var.set(self.tts_sound_enabled)
        self._clear_queued_sound("warning")
        self._clear_queued_sound("rune")
        self._save_settings()

    def _set_offline_mode_enabled(self, value):
        enabled = bool(value)
        self.offline_mode_enabled = enabled
        if hasattr(self, "offline_mode_var"):
            self.offline_mode_var.set(enabled)
        if enabled:
            self._enter_offline_mode()
        else:
            self._exit_offline_mode()
        self._save_settings()
        self._render_monitor_status()

    def _enter_offline_mode(self):
        self._release_capture_camera()
        self._set_rune_capture_active(False)
        self.rune_score = 0.0
        self.rune_baseline_score = None
        self.rune_alert_latched = False
        self.last_rune_alert_at = 0.0
        self._clear_queued_sound("rune")
        self._clear_queued_sound("rune_offline_tts")
        self._reset_offline_rune_cycle(save=False)
        self._refresh_rune_progress_visuals(force=True)

    def _exit_offline_mode(self):
        self.offline_rune_due = False
        self.offline_rune_alert_count = 0
        self.offline_rune_next_alert_at = 0.0
        self._clear_queued_sound("rune")
        self._clear_queued_sound("rune_offline_tts")
        self._set_rune_visual(False)
        self._set_rune_capture_active(False)

    def _set_warning_volume(self, value):
        self.warning_volume = int(max(0, min(100, value)))
        self._save_settings()

    def _set_rune_volume(self, value):
        self.rune_volume = int(max(0, min(100, value)))
        self._save_settings()

    def _set_halfhour_volume(self, value):
        self.halfhour_volume = int(max(0, min(100, value)))
        self._save_settings()

    def _set_rune_cooldown_minutes(self, value):
        self.rune_cooldown_minutes = normalize_rune_cooldown_minutes(value, self.rune_cooldown_minutes)
        if hasattr(self, "rune_cooldown_control"):
            self.rune_cooldown_control.set_value(self.rune_cooldown_minutes)
        self._save_settings()
        if self._monitor_ui_visible():
            self._draw_rune_status_bar()
        if getattr(self, "widget_mode_active", False):
            self._draw_widget_mode(force=True)

    def _apply_monitor_config(self):
        self.warning_loop_seconds = clamp_float(self.stall_var.get(), self.warning_loop_seconds, 10.0, 600.0)
        self.monitor_threshold = float(clamp_int(self.threshold_var.get(), int(self.monitor_threshold), 1, 100))
        self.rune_threshold = clamp_float(self.rune_threshold_var.get(), self.rune_threshold, 1.0, 100.0)
        self.warning_timer_paused = True
        self.warning_paused_remaining = self.warning_loop_seconds
        self.last_stall_alert_at = time.monotonic()
        self.rune_alert_latched = False
        self.last_rune_alert_at = 0.0
        self._clear_queued_sound("rune")
        self._save_settings()
        self._render_monitor_status()
        self._switch_page_with_blur("monitor")

    def _score_blue_damage(self, image):
        width, height = image.size
        total = width * height
        raw_mask = bytearray()
        for r, g, b in image.getdata():
            bright_enough = b >= 125 and (r + g + b) >= 220
            blue_dominant = b >= r + 35 and b >= g + 4
            cyan_blue = b >= 150 and g >= 80 and r <= 120 and b >= g - 18
            if bright_enough and (blue_dominant or cyan_blue):
                raw_mask.append(1)
            else:
                raw_mask.append(0)

        seen = bytearray(total)
        filtered = bytearray(total)
        digit_count = 0
        for start in range(total):
            if not raw_mask[start] or seen[start]:
                continue
            stack = [start]
            seen[start] = 1
            points = []
            min_x = width
            min_y = height
            max_x = 0
            max_y = 0
            while stack:
                pos = stack.pop()
                points.append(pos)
                x = pos % width
                y = pos // width
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
                if x > 0:
                    n = pos - 1
                    if raw_mask[n] and not seen[n]:
                        seen[n] = 1
                        stack.append(n)
                if x < width - 1:
                    n = pos + 1
                    if raw_mask[n] and not seen[n]:
                        seen[n] = 1
                        stack.append(n)
                if y > 0:
                    n = pos - width
                    if raw_mask[n] and not seen[n]:
                        seen[n] = 1
                        stack.append(n)
                if y < height - 1:
                    n = pos + width
                    if raw_mask[n] and not seen[n]:
                        seen[n] = 1
                        stack.append(n)

            area = len(points)
            box_w = max_x - min_x + 1
            box_h = max_y - min_y + 1
            if box_w <= 0 or box_h <= 0:
                continue
            density = area / (box_w * box_h)
            aspect = box_w / box_h
            lower_scene = height * 0.20 <= min_y <= height * 0.98
            digit_like = (
                6 <= area <= 360
                and 2 <= box_w <= 54
                and 4 <= box_h <= 42
                and 0.12 <= aspect <= 5.5
                and 0.10 <= density <= 0.90
            )
            if lower_scene and digit_like:
                digit_count += 1
                for pos in points:
                    filtered[pos] = 1

        if digit_count < 2:
            return 0.0, bytes(bytearray(total))
        score = float(digit_count)
        return score, bytes(filtered)

    def _score_rune(self, image, already_cropped=False):
        if not already_cropped:
            image = self._crop_minimap_view(image)
        if image is None:
            return 0.0
        image = image.convert("RGB")
        width, height = image.size
        total = width * height
        mask = bytearray(total)
        for index, (r, g, b) in enumerate(image.getdata()):
            y = index // width
            if y > height * 0.90:
                continue
            rune_purple = r >= 85 and b >= 125 and g <= 170 and b >= r + 8 and b >= g + 35
            deep_violet = b >= 150 and r >= 60 and g <= 150 and b >= r + 12 and b >= g + 45
            rune_magenta = r >= 185 and b >= 85 and g <= 100 and r >= b + 45 and r >= g + 90
            if rune_purple or deep_violet or rune_magenta:
                mask[index] = 1

        seen = bytearray(total)
        best_score = 0.0
        for start in range(total):
            if not mask[start] or seen[start]:
                continue
            stack = [start]
            seen[start] = 1
            points = []
            area = 0
            min_x = width
            min_y = height
            max_x = 0
            max_y = 0
            while stack:
                pos = stack.pop()
                points.append(pos)
                area += 1
                x = pos % width
                y = pos // width
                min_x = min(min_x, x)
                min_y = min(min_y, y)
                max_x = max(max_x, x)
                max_y = max(max_y, y)
                for dx, dy in ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)):
                    nx = x + dx
                    ny = y + dy
                    if 0 <= nx < width and 0 <= ny < height:
                        n = ny * width + nx
                        if mask[n] and not seen[n]:
                            seen[n] = 1
                            stack.append(n)

            box_w = max_x - min_x + 1
            box_h = max_y - min_y + 1
            if box_w <= 0 or box_h <= 0:
                continue
            density = area / (box_w * box_h)
            aspect = box_w / box_h
            scale_base = max(1.0, min(width, height) / 120.0)
            max_box = max(16, int(18 * scale_base))
            min_box = max(4, int(3 * scale_base))
            max_area = max(110, int(145 * scale_base * scale_base))
            min_area = max(8, int(8 * scale_base * scale_base))
            if not (min_area <= area <= max_area and min_box <= box_w <= max_box and min_box <= box_h <= max_box):
                continue
            if not (0.65 <= aspect <= 1.45 and 0.24 <= density <= 0.72):
                continue

            center_x = (min_x + max_x) / 2
            center_y = (min_y + max_y) / 2
            top = bottom = left = right = 0
            bright = 0
            rune_color_pixels = 0
            sum_r = sum_g = sum_b = 0
            for pos in points:
                x = pos % width
                y = pos // width
                if y < center_y:
                    top += 1
                else:
                    bottom += 1
                if x < center_x:
                    left += 1
                else:
                    right += 1
                r, g, b = image.getpixel((x, y))
                sum_r += r
                sum_g += g
                sum_b += b
                if r + b >= 230 and max(r, b) >= 125:
                    bright += 1
                strong_purple = r >= 150 and b >= 175 and 65 <= g <= 175 and b >= r + 2 and b >= g + 35
                strong_magenta = r >= 185 and b >= 85 and g <= 100 and r >= b + 45 and r >= g + 90
                if strong_purple or strong_magenta:
                    rune_color_pixels += 1

            balance = min(top, bottom, left, right) / max(1, max(top, bottom, left, right))
            if balance < 0.32:
                continue
            bright_ratio = bright / max(1, area)
            if bright_ratio < 0.42:
                continue
            color_ratio = rune_color_pixels / max(1, area)
            if color_ratio < 0.60:
                continue
            avg_r = sum_r / area
            avg_g = sum_g / area
            avg_b = sum_b / area
            purple_average = avg_r >= 150 and 70 <= avg_g <= 170 and avg_b >= 185 and avg_b >= avg_r + 4
            magenta_average = avg_r >= 185 and avg_g <= 100 and avg_b >= 85 and avg_r >= avg_b + 45
            if not (purple_average or magenta_average):
                continue

            size_score = min(1.0, area / 32.0)
            shape_score = min(1.0, balance / 0.62)
            fill_score = 1.0 - min(1.0, abs(density - 0.48) / 0.20)
            bright_score = min(1.0, bright_ratio / 0.60)
            color_score = min(1.0, color_ratio / 0.85)
            best_score = max(best_score, 100.0 * size_score * shape_score * fill_score * bright_score * color_score)
        return best_score

    def _crop_minimap_view(self, image):
        width, height = image.size
        if width < 80 or height < 60:
            return image
        runs = []
        pixels = image.load()
        min_run = max(70, int(width * 0.30))
        for y in range(height):
            x = 0
            while x < width:
                while x < width:
                    r, g, b = pixels[x, y]
                    if r >= 205 and g >= 205 and b >= 205:
                        break
                    x += 1
                start = x
                while x < width:
                    r, g, b = pixels[x, y]
                    if not (r >= 205 and g >= 205 and b >= 205):
                        break
                    x += 1
                if y > 5 and y < height - 5 and start > 3 and x < width - 3 and x - start >= min_run:
                    runs.append((y, start, x - 1, x - start))
        best = None
        for top in runs:
            for bottom in runs:
                y1, x1a, x2a, len_a = top
                y2, x1b, x2b, len_b = bottom
                box_h = y2 - y1
                if not (45 <= box_h <= min(260, height - 4)):
                    continue
                x1 = max(x1a, x1b)
                x2 = min(x2a, x2b)
                box_w = x2 - x1 + 1
                if box_w < min_run:
                    continue
                x_similarity = abs(x1a - x1b) + abs(x2a - x2b)
                score = box_w * box_h - x_similarity * 8
                if best is None or score > best[0]:
                    best = (score, x1, y1, x2, y2)
        if best is None:
            return None
        _score, x1, y1, x2, y2 = best
        pad = 4
        x1 = max(0, x1 + pad)
        y1 = max(0, y1 + pad)
        x2 = min(width, x2 - pad)
        y2 = min(height, y2 - pad)
        if x2 - x1 < 40 or y2 - y1 < 30:
            return None
        return image.crop((x1, y1, x2, y2))

    def _mask_own_window(self, captured, region=None):
        region = region or self.region
        if not region:
            return captured
        app_rect = self._get_app_rect()
        return self._mask_captured_region(captured, region, app_rect)

    def _mask_captured_region(self, captured, region, app_rect):
        if not app_rect:
            return captured
        app_x1, app_y1, app_x2, app_y2 = app_rect
        region_x1, region_y1, region_x2, region_y2 = region
        x1 = max(region_x1, app_x1) - region_x1
        y1 = max(region_y1, app_y1) - region_y1
        x2 = min(region_x2, app_x2) - region_x1
        y2 = min(region_y2, app_y2) - region_y1
        if x2 > x1 and y2 > y1:
            captured = captured.copy()
            captured.paste((0, 0, 0), (x1, y1, x2, y2))
        return captured

    def _overlaps_region(self, region=None):
        region = region or self.region
        if not region:
            return False
        try:
            self.root.update_idletasks()
            app_x1 = self.root.winfo_rootx()
            app_y1 = self.root.winfo_rooty()
            app_x2 = app_x1 + self.root.winfo_width()
            app_y2 = app_y1 + self.root.winfo_height()
        except tk.TclError:
            return False
        region_x1, region_y1, region_x2, region_y2 = region
        return min(app_x2, region_x2) > max(app_x1, region_x1) and min(app_y2, region_y2) > max(app_y1, region_y1)

    def _avoid_region_overlap(self, region=None):
        region = region or self.region
        if not region or not self._overlaps_region(region):
            return False
        self.root.update_idletasks()
        width = self.root.winfo_width()
        height = self.root.winfo_height()
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        region_x1, region_y1, region_x2, region_y2 = region
        margin = 14
        candidates = [
            (region_x2 + margin, region_y1),
            (region_x1 - width - margin, region_y1),
            (region_x1, region_y2 + margin),
            (region_x1, region_y1 - height - margin),
            (screen_w - width - margin, margin),
        ]
        for x, y in candidates:
            x = max(margin, min(screen_w - width - margin, x))
            y = max(margin, min(screen_h - height - margin, y))
            if not (min(x + width, region_x2) > max(x, region_x1) and min(y + height, region_y2) > max(y, region_y1)):
                self.root.geometry(f"+{int(x)}+{int(y)}")
                self.root.update()
                return True
        return False

    def _grab_region_without_self(self, region=None):
        region = region or self.region
        if not region:
            return None
        captured = self._grab_region_frame(region)
        return self._mask_own_window(captured, region)

    def _grab_region_frame(self, region):
        return self._grab_frame(region)

    def _monitor_tick(self):
        try:
            self._monitor_tick_body()
        except Exception as exc:
            log_error("monitor_tick", exc)
        finally:
            self.root.after(self.monitor_interval_ms, self._monitor_tick)

    def _monitor_tick_body(self):
            now = time.monotonic()
            if self.monitor_enabled and not getattr(self, "warning_timer_paused", False) and now - self.last_stall_alert_at >= self.warning_loop_seconds:
                self._play("warning")
                self.last_stall_alert_at = now
                self.stall_alert_latched = True
            if getattr(self, "offline_mode_enabled", False):
                self._offline_rune_tick(now)
                self._set_rune_capture_active(False)
                self._render_monitor_status()
                return
            if self.rune_region and not self._maplestory_process_is_running():
                self._set_rune_capture_active(False)
                self.rune_score = 0.0
                self.rune_alert_latched = False
                self.last_rune_alert_at = 0.0
                self._clear_queued_sound("rune")
                self._set_rune_visual(False)
                self._set_auto_detect_status("메이플 실행 대기")
                self._render_monitor_status()
                return
            if self.rune_region and now - getattr(self, "last_rune_window_sync_at", 0.0) >= RUNE_WINDOW_SYNC_INTERVAL_SECONDS:
                self.last_rune_window_sync_at = now
                self._sync_rune_region_to_maplestory_window()
            if self.monitor_enabled and self.rune_region:
                self._start_monitor_worker()
            else:
                self._set_rune_capture_active(False)
                self.rune_score = 0.0
                self.rune_alert_latched = False
                self.last_rune_alert_at = 0.0
                self._clear_queued_sound("rune")
                self._set_rune_visual(False)
            self._render_monitor_status()

    def _start_monitor_worker(self):
        if self.monitor_worker_running or not self.rune_region or getattr(self, "offline_mode_enabled", False):
            return
        self.monitor_worker_running = True
        rune_region = tuple(self.rune_region)
        app_rect = self._get_app_rect()
        threading.Thread(target=self._monitor_worker, args=(rune_region, app_rect), daemon=True).start()

    def _monitor_worker(self, rune_region, app_rect):
        result = {"score": 0.0, "captured": None, "error": False, "minimap_ok": False}
        try:
            rune_captured = self._grab_region_frame(rune_region)
            rune_captured = self._mask_captured_region(rune_captured, rune_region, app_rect)
            minimap_view = self._crop_minimap_view(rune_captured)
            result["minimap_ok"] = minimap_view is not None
            result["score"] = self._score_rune(minimap_view, already_cropped=True) if minimap_view is not None else 0.0
            result["captured"] = rune_captured
        except Exception:
            result["error"] = True
        self.worker_results.put(("monitor", result))

    def _process_worker_results(self):
        try:
            while True:
                kind, result = self.worker_results.get_nowait()
                try:
                    if kind == "monitor":
                        self.monitor_worker_running = False
                        self._apply_monitor_result(result)
                    elif kind == "auto_detect":
                        self.auto_detect_worker_running = False
                        self._apply_auto_detect_result(result)
                except Exception as exc:
                    log_error(f"apply_{kind}", exc)
                finally:
                    self.worker_results.task_done()
        except queue.Empty:
            pass
        except Exception as exc:
            log_error("worker_results", exc)
        finally:
            self.root.after(100, self._process_worker_results)

    def _apply_monitor_result(self, result):
        if getattr(self, "offline_mode_enabled", False):
            return
        if self.rune_region and not self._maplestory_process_is_running():
            self._set_rune_capture_active(False)
            self.rune_score = 0.0
            self.rune_alert_latched = False
            self.last_rune_alert_at = 0.0
            self._clear_queued_sound("rune")
            self.last_capture = None
            self._set_rune_visual(False)
            self._set_auto_detect_status("메이플 실행 대기")
            return
        if result.get("error"):
            self._set_rune_capture_active(False)
            self.rune_score = 0.0
            self.rune_alert_latched = False
            self.last_rune_alert_at = 0.0
            self._clear_queued_sound("rune")
            self.last_capture = None
            self._set_auto_detect_status("화면 캡쳐 실패")
            return
        if not result.get("minimap_ok"):
            self._sync_rune_region_to_maplestory_window()
            if self.rune_region:
                self._set_rune_capture_active(True)
                self.rune_score = 0.0
                self.rune_baseline_score = None
                self.rune_alert_latched = False
                self.last_rune_alert_at = 0.0
                self._clear_queued_sound("rune")
                status = "미니맵 위치 확인 중" if self.rune_window_anchor else "기존 미니맵 영역 사용 중"
                self._set_auto_detect_status(status)
                return
            self.rune_region = None
            self.rune_window_anchor = None
            self.rune_score = 0.0
            self.rune_baseline_score = None
            self.rune_alert_latched = False
            self.last_rune_alert_at = 0.0
            self._clear_queued_sound("rune")
            self._save_settings()
            self._set_auto_detect_status("룬영역을 지정해주세요")
            return
        now = time.monotonic()
        self._set_rune_capture_active(True)
        self.rune_score = float(result.get("score") or 0.0)
        if self.rune_baseline_score is None:
            self.rune_baseline_score = self.rune_score
        rune_active = self.rune_score >= self.rune_threshold
        if rune_active:
            if now - self.last_rune_alert_at >= self.rune_alert_interval:
                self._play("rune")
                self.last_rune_alert_at = now
            self.rune_alert_latched = True
            self._set_auto_detect_status("룬이 등장했습니다")
        else:
            self.rune_alert_latched = False
            self.last_rune_alert_at = 0.0
            self._clear_queued_sound("rune")
            self.rune_baseline_score = min(self.rune_baseline_score, self.rune_score)
            self._set_auto_detect_status("기존 미니맵 영역 사용 중")
        self.last_capture = result.get("captured")

    def _apply_auto_detect_result(self, result):
        if getattr(self, "offline_mode_enabled", False):
            return
        if not self.auto_detect_enabled:
            return
        if result.get("error"):
            self._set_rune_capture_active(False)
            self._set_auto_detect_status("화면 캡쳐 실패")
            return
        detected = result.get("detected")
        if detected:
            if self._region_changed(self.rune_region, detected):
                self._set_rune_region(detected)
            self._set_rune_capture_active(True)
            self.last_auto_detect_region = detected
            self.auto_detect_notice_shown = False
            self._set_auto_detect_status("미니맵 자동탐지 완료")
            return
        if result.get("keeps_old") and self.rune_region:
            self._set_rune_capture_active(True)
            self._set_auto_detect_status("기존 미니맵 영역 사용 중")
            return
        self._set_rune_capture_active(False)
        self.rune_region = None
        self.rune_score = 0.0
        self.rune_alert_latched = False
        self.last_rune_alert_at = 0.0
        self._clear_queued_sound("rune")
        self._save_settings()
        self._set_auto_detect_status("룬영역을 지정해주세요")
        if result.get("show_notice") and not self.auto_detect_notice_shown:
            self.auto_detect_notice_shown = True
            self.root.after(100, lambda: messagebox.showinfo(APP_NAME, "미니맵을 자동으로 찾지 못했습니다.\n룬영역을 지정해주세요."))

    def _render_monitor_status(self):
        now = time.monotonic()
        remaining = max(0, int(self._warning_remaining_float(now) + 0.999))
        self.countdown_remaining = remaining
        if hasattr(self, "countdown_canvas"):
            self._update_countdown_display_lightweight(now)
        elif hasattr(self, "countdown_number"):
            self.countdown_number.configure(text=str(remaining))
        if hasattr(self, "monitor_button"):
            on = self.monitor_enabled
            self.monitor_button.configure_style("■" if on else "▶", "#ffffff", self.colors["text"], "#f7f7f7", "#ffffff")
        if getattr(self, "widget_mode_active", False):
            self._update_widget_timer_display_lightweight(now)

    def _export_preset(self):
        self._sync_timer_rows_to_model()
        self._save_settings()
        path = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("JSON", "*.json")], initialfile="maple-timer-preset.json")
        if path:
            Path(path).write_text(SETTINGS_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    def _import_preset(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if not path:
            return
        try:
            SETTINGS_PATH.write_text(Path(path).read_text(encoding="utf-8"), encoding="utf-8")
            self._load_settings()
            self.session_var.set(str(self.session_seconds // 60))
            self._rebuild_timer_rows()
            self._render()
            self._render_monitor_status()
        except OSError as exc:
            messagebox.showerror(APP_NAME, f"프리셋을 불러오지 못했습니다.\n{exc}")

    def _reset_defaults(self):
        self.session_seconds = DEFAULT_SESSION_SECONDS
        self.timers = self._default_timers()
        for timer in self.timers:
            timer.reset()
        self.session_var.set(str(self.session_seconds // 60))
        self._rebuild_timer_rows()
        self._save_settings()
        self._render()

    def _tick(self):
        try:
            now = time.monotonic()
            if self.running:
                self.session_remaining = max(0, int(self.session_deadline - now + 0.999))
                for timer in self.timers:
                    if timer.tick(now):
                        self._play("skill")
                if self.session_remaining <= 0:
                    self._play("done")
                    self._stop()
            self._render()
        except Exception as exc:
            log_error("tick", exc)
        finally:
            self.root.after(150, self._tick)

    def _render(self):
        if not hasattr(self, "session_time_label"):
            return
        self.session_time_label.configure(text=fmt(self.session_remaining))
        self.session_label.configure(text="세션 진행 중" if self.running else "세션 대기")
        self.progress.delete("all")
        width, height = max(1, self.progress.winfo_width()), max(1, self.progress.winfo_height())
        ratio = 0 if self.session_seconds <= 0 else 1 - (self.session_remaining / self.session_seconds)
        self.progress.create_rectangle(0,0,width,height,fill=self.colors["surface_alt"],outline="")
        self.progress.create_rectangle(0,0,int(width*max(0,min(1,ratio))),height,fill=self.colors["blue"],outline="")
        for row in self.timer_rows:
            timer = row["timer"]
            row["countdown"].configure(text=fmt(timer.remaining or timer.seconds))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    MapleTimerApp().run()
