"""Exercise the real Tk widget against OBS's Windows enumeration criteria."""
import os
import tempfile
from pathlib import Path
import unittest
import ctypes
from unittest.mock import Mock

_data = tempfile.TemporaryDirectory(prefix='rune-obs-test-')
os.environ['RUNE_TIMER_PC_DATA'] = _data.name
for _name in ('settings.json', 'settings-low.json'):
    (Path(_data.name) / _name).write_text('{}', encoding='utf-8')
(Path(_data.name) / 'ui-profile.json').write_text('"high"', encoding='utf-8')
import pc_app as app
from ctypes import wintypes as W


class ObsWidgetTests(unittest.TestCase):
    def test_widget_is_enumerable_after_each_show(self):
        root = app.tk.Tk()
        root.withdraw()
        timer = app.PcTimerApp.__new__(app.PcTimerApp)
        timer.root = root
        timer.widget = timer.widget_canvas = None
        timer._draw_widget_mode = Mock()
        timer._apply_window_icon = Mock()
        u = ctypes.WinDLL('user32', use_last_error=True)
        u.GetAncestor.argtypes = [W.HWND, W.UINT]
        u.GetAncestor.restype = W.HWND
        u.GetWindowLongW.argtypes = [W.HWND, ctypes.c_int]
        u.GetWindowLongW.restype = W.LONG
        u.GetClientRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
        u.IsWindowVisible.argtypes = [W.HWND]
        callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        u.EnumWindows.argtypes = [callback_type, W.LPARAM]
        try:
            self.assertTrue(timer._ensure_widget_window())
            for cycle in range(3):
                timer.widget.geometry('384x138+40+40')
                timer.widget.deiconify()
                timer.widget.attributes('-alpha', 1.0)
                root.update()
                hwnd = u.GetAncestor(timer.widget.winfo_id(), 2)
                windows = []
                callback = callback_type(lambda h, _: windows.append(h) or True)
                self.assertTrue(u.EnumWindows(callback, 0))
                self.assertIn(hwnd, windows)
                self.assertTrue(u.IsWindowVisible(hwnd))
                self.assertFalse(u.GetWindowLongW(hwnd, -20) & 0x80,
                                 'OBS excludes WS_EX_TOOLWINDOW')
                self.assertFalse(u.GetWindowLongW(hwnd, -16) & 0x40000000)
                rect = W.RECT()
                self.assertTrue(u.GetClientRect(hwnd, ctypes.byref(rect)))
                self.assertGreater(rect.right, 0)
                self.assertGreater(rect.bottom, 0)
                self.assertEqual(timer.widget.title(), 'RuneTimer OBS Widget')
                self.assertTrue(timer.widget.overrideredirect())
                self.assertEqual(timer.widget.wm_attributes('-transparentcolor'), app.base.TRANSPARENT)
                timer.widget.withdraw()
                root.update()
        finally:
            root.destroy()


if __name__ == '__main__':
    unittest.main()
