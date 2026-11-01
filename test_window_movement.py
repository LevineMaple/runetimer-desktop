"""Real Tk regression checks for moving the live main window."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Reuse the isolated settings and disabled sounds from the UI test fixture.
from test_booster_ui import pc_app


class WindowMovementTests(unittest.TestCase):
    def test_drag_moves_live_window_without_capture_or_surface_swap(self):
        with patch.object(pc_app.PcTimerApp, '_show_startup_splash'):
            app = pc_app.PcTimerApp()
        try:
            app._show_main_window(force_focus=True)
            app.root.update()
            x, y = app.root.winfo_x(), app.root.winfo_y()
            size = app.root.winfo_width(), app.root.winfo_height()
            alpha = app.root.attributes('-alpha')

            def event(dx, dy):
                return SimpleNamespace(widget=app.backdrop, x=40, y=40,
                                       x_root=x + 40 + dx, y_root=y + 40 + dy)

            with patch.object(pc_app.base.ImageGrab, 'grab', side_effect=AssertionError('drag captured desktop')), \
                    patch.object(app, '_save_settings') as save, \
                    patch.object(app, '_schedule_surface_refresh') as refresh:
                app._start_drag(event(0, 0))
                for dx, dy in ((12, 8), (24, 16), (36, 24)):
                    app._drag(event(dx, dy))
                    app.root.update_idletasks()
                    self.assertEqual((app.root.winfo_x(), app.root.winfo_y()), (x + dx, y + dy))
                    self.assertIsNone(app.drag_proxy)
                    self.assertEqual(app.root.attributes('-alpha'), alpha)
                    self.assertEqual((app.root.winfo_width(), app.root.winfo_height()), size)
                    save.assert_not_called()
                # Release can be newer than the last motion event.
                app._end_drag(event(42, 30))
                app.root.update_idletasks()
                self.assertEqual((app.root.winfo_x(), app.root.winfo_y()), (x + 42, y + 30))
                self.assertFalse(app.dragging_main_window)
                save.assert_called_once()
                refresh.assert_not_called()
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            app.root.destroy()


if __name__ == '__main__':
    unittest.main()
