"""Local Windows screen capture. GPL-3.0-or-later. Modified 2026-09-27."""
import ctypes
from ctypes import wintypes as W
from pathlib import Path
from PIL import ImageGrab

U = ctypes.WinDLL('user32', use_last_error=True)
K = ctypes.WinDLL('kernel32', use_last_error=True)

def enable_dpi():
    # Set before Tk creation; no OS or game settings are changed.
    try:
        U.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        U.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
    except (AttributeError, OSError):
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except (AttributeError, OSError):
            U.SetProcessDPIAware()

U.GetClientRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
U.ClientToScreen.argtypes = [W.HWND, ctypes.POINTER(W.POINT)]
U.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
U.GetWindowTextLengthW.argtypes = [W.HWND]
U.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
U.IsWindowVisible.argtypes = [W.HWND]
U.IsIconic.argtypes = [W.HWND]
K.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
K.OpenProcess.restype = W.HANDLE
K.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
K.CloseHandle.argtypes = [W.HANDLE]
ENUMPROC = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
U.EnumWindows.argtypes = [ENUMPROC, W.LPARAM]

def expose_obs_widget(widget):
    """Keep Tk's borderless/transparent window, but allow OBS enumeration.

    Tk marks override-redirect windows as tool windows when mapping them.
    Apply this after each Map event, to the native wrapper rather than the
    child HWND returned by winfo_id(). Do not force a taskbar button.
    """
    U.GetAncestor.argtypes = [W.HWND, W.UINT]
    U.GetAncestor.restype = W.HWND
    U.GetWindowLongW.argtypes = [W.HWND, ctypes.c_int]
    U.GetWindowLongW.restype = W.LONG
    U.SetWindowLongW.argtypes = [W.HWND, ctypes.c_int, W.LONG]
    U.SetWindowLongW.restype = W.LONG
    U.SetWindowPos.argtypes = [W.HWND, W.HWND, ctypes.c_int, ctypes.c_int,
                               ctypes.c_int, ctypes.c_int, W.UINT]
    hwnd = U.GetAncestor(widget.winfo_id(), 2)  # GA_ROOT
    if not hwnd:
        raise ctypes.WinError()
    style = U.GetWindowLongW(hwnd, -20)  # GWL_EXSTYLE
    if style & 0x80:  # WS_EX_TOOLWINDOW, explicitly excluded by OBS
        ctypes.set_last_error(0)
        previous = U.SetWindowLongW(hwnd, -20, style & ~0x80)
        if not previous and ctypes.get_last_error():
            raise ctypes.WinError(ctypes.get_last_error())
        # FRAMECHANGED | NOMOVE | NOSIZE | NOZORDER | NOACTIVATE
        if not U.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37):
            raise ctypes.WinError()

def desktop_bounds():
    x,y,w,h = (U.GetSystemMetrics(i) for i in (76,77,78,79))
    return x,y,x+w,y+h

def maple_windows():
    result = []
    @ENUMPROC
    def visit(hwnd, _):
        if not U.IsWindowVisible(hwnd) or U.IsIconic(hwnd):
            return True
        title = ctypes.create_unicode_buffer(U.GetWindowTextLengthW(hwnd)+1)
        U.GetWindowTextW(hwnd,title,len(title))
        if title.value.casefold() != 'maplestory':
            return True
        pid=W.DWORD(); U.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
        name=''
        handle=K.OpenProcess(0x1000,False,pid.value)
        if handle:
            try:
                path=ctypes.create_unicode_buffer(32768); size=W.DWORD(len(path))
                if K.QueryFullProcessImageNameW(handle,0,path,ctypes.byref(size)):
                    name=Path(path.value).name.lower()
            finally:
                K.CloseHandle(handle)
        if name and name != 'maplestory.exe':
            return True
        rect=W.RECT(); origin=W.POINT(0,0)
        if U.GetClientRect(hwnd,ctypes.byref(rect)) and U.ClientToScreen(hwnd,ctypes.byref(origin)):
            if rect.right>=320 and rect.bottom>=240:
                result.append(dict(hwnd=int(hwnd),pid=pid.value,process_name=name or 'maplestory.exe',
                                   title=title.value,rect=(origin.x,origin.y,origin.x+rect.right,origin.y+rect.bottom)))
        return True
    U.EnumWindows(visit,0)
    return rank_game_windows(result,desktop_bounds())

def rank_game_windows(windows,bounds):
    left,top,right,bottom=bounds
    def rank(w):
        x1,y1,x2,y2=w['rect']
        visible=max(0,min(right,x2)-max(left,x1))*max(0,min(bottom,y2)-max(top,y1))
        area=(x2-x1)*(y2-y1)
        return (visible,area)
    # Maple also exposes a same-title/same-PID auxiliary window at the bottom
    # of this PC's desktop. Enumeration order is NOT the game-window order.
    return sorted([w for w in windows if rank(w)[0]>=320*200],key=rank,reverse=True)

def validate_region(region, bounds=None):
    x1,y1,x2,y2=map(int,region)
    left,top,right,bottom=bounds or desktop_bounds()
    if x2<=x1 or y2<=y1 or x1<left or y1<top or x2>right or y2>bottom:
        raise ValueError(f'capture region={region}, desktop={(left,top,right,bottom)}')
    return x1,y1,x2,y2

def grab(region):
    region=validate_region(region)
    # GDI/Pillow with global physical coordinates; supports secondary displays
    # and negative desktop origins. No dxcam output-index assumptions.
    im=ImageGrab.grab(bbox=region,all_screens=True).convert('RGB')
    if im.size != (region[2]-region[0],region[3]-region[1]):
        raise RuntimeError(f'capture size={im.size}, region={region}')
    return im

def translate_region(relative, client_rect):
    x,y,right,bottom=client_rect
    region=tuple(int(v) for v in (x+relative[0],y+relative[1],x+relative[2],y+relative[3]))
    if region[0]<x or region[1]<y or region[2]>right or region[3]>bottom:
        raise ValueError('Game client resized; select the minimap again.')
    return validate_region(region)
