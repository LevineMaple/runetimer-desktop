"""Real Windows/Tk selectors over simulated multi-monitor rectangles."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from PIL import Image
import test_booster_ui as fixture

pc = fixture.pc_app


class MultiMonitorSelectorTests(unittest.TestCase):
    def setUp(self):
        self.root = pc.tk.Tk()
        self.root.withdraw()
        self.addCleanup(self.root.destroy)

    def make_selector(self, bounds, **kwargs):
        x, y, r, b = bounds
        callback, closed = Mock(), Mock()
        frame = Image.new('RGB', (r-x, b-y), '#15252a')
        with patch.object(pc.cap, 'desktop_bounds', return_value=bounds), \
                patch.object(pc.cap, 'grab', return_value=frame) as grab:
            selector = pc.ScreenSelector(self.root, callback, closed, **kwargs)
        grab.assert_called_once_with(bounds)
        self.addCleanup(lambda: selector.close() if selector.winfo_exists() else None)
        return selector, callback, closed

    def test_native_placement_and_physical_selection_across_layouts(self):
        layouts = (
            (0, -420, 3000, 1500),       # Right portrait extends upward.
            (-1920, 0, 2560, 1600),     # Landscape left of primary.
            (-1080, -420, 1920, 1500),  # Portrait left and above.
            (0, 0, 4480, 1600),        # Wider than Tk's default maxsize.
            (0, -1080, 2560, 1600),    # Monitor above primary.
            (100, 100, 1380, 820),     # Positive physical origin.
        )
        for bounds in layouts:
            with self.subTest(bounds=bounds):
                selector, callback, closed = self.make_selector(bounds)
                selector.update()
                x, y, r, b = bounds
                canvas = selector.canvas
                self.assertEqual((canvas.winfo_rootx(), canvas.winfo_rooty(),
                                  canvas.winfo_width(), canvas.winfo_height()),
                                 (x, y, r-x, b-y))
                self.assertEqual((selector.photo.width(), selector.photo.height()), (r-x, b-y))
                self.assertGreaterEqual(selector.maxsize()[0], r-x)
                self.assertGreaterEqual(selector.maxsize()[1], b-y)
                for event, px, py in (('<ButtonPress-1>', 310, 240),
                                       ('<B1-Motion>', 120, 135),
                                       ('<ButtonRelease-1>', 120, 135)):
                    canvas.event_generate(event, x=px, y=py)
                callback.assert_called_once_with((x+120, y+135, x+310, y+240))
                closed.assert_called_once()
                selector.close()
                closed.assert_called_once()

    def test_janus_small_selection_and_cancel(self):
        selector, callback, closed = self.make_selector((-1080, -420, 1920, 1500), min_size=(8, 8))
        selector.begin(SimpleNamespace(x=30, y=50))
        selector.finish(SimpleNamespace(x=35, y=55))
        callback.assert_not_called()
        self.assertTrue(selector.winfo_exists())
        selector.finish(SimpleNamespace(x=64, y=84))
        callback.assert_called_once_with((-1050, -370, -1016, -336))
        closed.assert_called_once()
        selector, callback, closed = self.make_selector((0, 0, 1920, 1080))
        selector.close()
        callback.assert_not_called()
        closed.assert_called_once()

    def test_failed_native_placement_does_not_leave_overlay(self):
        with patch.object(pc.cap, 'desktop_bounds', return_value=(0, -420, 3000, 1500)), \
                patch.object(pc.cap, 'grab', return_value=Image.new('RGB', (3000, 1920))), \
                patch.object(pc.cap, 'place_selection_window', side_effect=OSError('test')):
            with self.assertRaises(OSError):
                pc.ScreenSelector(self.root, Mock(), Mock())
        self.assertEqual(self.root.winfo_children(), [])


if __name__ == '__main__':
    unittest.main()
