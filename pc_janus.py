"""Read only the selected MapleStory icon on the local Windows desktop."""
import ctypes
import time
from ctypes import wintypes as W
from dataclasses import dataclass
from PIL import Image

import pc_capture as cap
from pc_janus_reader import MAX_REGION_WIDTH, MAX_REGION_HEIGHT, read_observation

# Explicit handle-sized return types are necessary on 64-bit Windows.
_gdi = ctypes.WinDLL('gdi32', use_last_error=True)
_user = ctypes.WinDLL('user32', use_last_error=True)


def _api(lib, name, result, *arguments):
    function = getattr(lib, name)
    function.restype, function.argtypes = result, arguments
    return function


_get_dc = _api(_user, 'GetDC', W.HDC, W.HWND)
_release_dc = _api(_user, 'ReleaseDC', ctypes.c_int, W.HWND, W.HDC)
_memory_dc = _api(_gdi, 'CreateCompatibleDC', W.HDC, W.HDC)
_bitmap = _api(_gdi, 'CreateDIBSection', W.HANDLE, W.HDC, ctypes.c_void_p,
               W.UINT, ctypes.POINTER(ctypes.c_void_p), W.HANDLE, W.DWORD)
_select = _api(_gdi, 'SelectObject', W.HANDLE, W.HDC, W.HANDLE)
_blit = _api(_gdi, 'BitBlt', W.BOOL, W.HDC, ctypes.c_int, ctypes.c_int,
             ctypes.c_int, ctypes.c_int, W.HDC, ctypes.c_int, ctypes.c_int, W.DWORD)
_flush = _api(_gdi, 'GdiFlush', W.BOOL)
_delete_bitmap = _api(_gdi, 'DeleteObject', W.BOOL, W.HANDLE)
_delete_dc = _api(_gdi, 'DeleteDC', W.BOOL, W.HDC)
_window_at = _api(_user, 'WindowFromPoint', W.HWND, W.POINT)
_root_of = _api(_user, 'GetAncestor', W.HWND, W.HWND, W.UINT)


class BitmapHeader(ctypes.Structure):
    _fields_ = [('size', W.DWORD), ('width', W.LONG), ('height', W.LONG),
                ('planes', W.WORD), ('bits', W.WORD), ('compression', W.DWORD),
                ('image_size', W.DWORD), ('x_res', W.LONG), ('y_res', W.LONG),
                ('used_colors', W.DWORD), ('important_colors', W.DWORD)]


def valid_skill_region(width, height):
    return 8 <= width <= MAX_REGION_WIDTH and 8 <= height <= MAX_REGION_HEIGHT


def grab_icon(region):
    """BitBlt copies just the requested pixels, including negative desktop origins."""
    x, y, right, bottom = region
    width, height = right - x, bottom - y
    if not valid_skill_region(width, height):
        raise ValueError('스킬 아이콘 영역은 가로 2048, 세로 512픽셀 이내로 지정해 주세요.')
    header = BitmapHeader(ctypes.sizeof(BitmapHeader), width, -height, 1, 32)
    bits = ctypes.c_void_p()
    screen = _get_dc(None)
    memory = bitmap = previous = None
    try:
        if screen:
            memory = _memory_dc(screen)
        if memory:
            bitmap = _bitmap(screen, ctypes.byref(header), 0, ctypes.byref(bits), None, 0)
        if bitmap:
            previous = _select(memory, bitmap)
        if not previous or previous == ctypes.c_void_p(-1).value or not bits.value:
            raise OSError('아이콘 캡처 준비 실패')
        if not _blit(memory, 0, 0, width, height, screen, x, y, 0x40CC0020) or not _flush():
            raise OSError('아이콘 캡처 실패')
        return Image.frombytes('RGB', (width, height),
                               ctypes.string_at(bits, width * height * 4), 'raw', 'BGRX')
    finally:
        if previous and previous != ctypes.c_void_p(-1).value:
            _select(memory, previous)
        if bitmap:
            _delete_bitmap(bitmap)
        if memory:
            _delete_dc(memory)
        if screen:
            _release_dc(None, screen)


def visible_game_region(hwnd, region):
    x, y, r, b = region
    points = ((x, y), (r-1, y), (x, b-1), (r-1, b-1), ((r+x)//2, (b+y)//2))
    return all(_root_of(_window_at(W.POINT(px, py)), 2) == hwnd for px, py in points)


@dataclass(frozen=True)
class JanusSample:
    seconds: int | None
    status: str
    captured: float
    hwnd: int | None = None
    icon_present: bool = False
    region_observed: bool = False


def sample_janus(region, client_size, cancelled):
    if cancelled.is_set():
        return None
    games = cap.maple_windows()
    if not games:
        return JanusSample(None, '게임 창 대기', time.monotonic())
    game = games[0]
    x, y, r, b = game['rect']
    if (r-x, b-y) != client_size:
        return JanusSample(None, '게임 크기가 바뀌었어요 · 아이콘을 다시 지정하세요', time.monotonic())
    try:
        rect = cap.translate_region(region, game['rect'])
    except ValueError:
        return JanusSample(None, '영역이 화면 밖에 있어요', time.monotonic())
    hwnd = game['hwnd']
    if not visible_game_region(hwnd, rect):
        return JanusSample(None, '아이콘이 가려져 있어요', time.monotonic(), hwnd)
    if cancelled.is_set():
        return None
    captured = time.monotonic()
    frame = grab_icon(rect)
    if cancelled.is_set():
        return None
    present, seconds = read_observation(frame)
    if seconds is not None:
        status = f'{seconds//60}:{seconds%60:02d}'
    else:
        status = '아이콘 확인 · 숫자 대기' if present else '야누스 아이콘 대기'
    return JanusSample(seconds, status, captured, hwnd, present, region_observed=True)
