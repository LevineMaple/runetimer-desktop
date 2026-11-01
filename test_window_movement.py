"""Real Tk regression checks for moving the live main window."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Reuse the isolated settings and disabled sounds from the UI test fixture.
from test_booster_ui import pc_app


class WindowMovementTests(unittest.TestCase):
    def test_settings_remain_reachable_in_small_window(self):
        with patch.object(pc_app.PcTimerApp, '_show_startup_splash'):
            app = pc_app.PcTimerApp()
        try:
            app._show_main_window()
            app.root.update()
            app._show_page('settings')
            app.root.update_idletasks()
            app._resize_main_window_nomove(pc_app.base.APP_MIN_WIDTH, pc_app.base.APP_MIN_HEIGHT)
            app._refresh_resize_surface()
            app.root.update_idletasks()
            viewport = app.settings_viewport
            self.assertLessEqual(app.settings_stack.winfo_reqwidth(), viewport.winfo_width())
            bbox = viewport.bbox(app.settings_stack_item)
            self.assertGreaterEqual(bbox[0], 0)
            self.assertLessEqual(bbox[2], viewport.winfo_width())
            viewport.yview_moveto(0)
            self.assertAlmostEqual(viewport.yview()[0], 0)
            if app.settings_stack.winfo_reqheight() > viewport.winfo_height():
                self.assertFalse(any(isinstance(child, pc_app.tk.Scrollbar)
                                     for child in viewport.master.winfo_children()))
                app._scroll_settings(SimpleNamespace(delta=-120, num=None))
                self.assertGreater(viewport.yview()[0], 0)
                viewport.yview_moveto(1)
                self.assertAlmostEqual(viewport.yview()[1], 1)
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            for after_id in app.root.tk.call('after', 'info'):
                app.root.after_cancel(after_id)
            app.root.destroy()

    def test_reset_size_centers_timer_on_first_click(self):
        with patch.object(pc_app.PcTimerApp, '_show_startup_splash'):
            app = pc_app.PcTimerApp()
        try:
            app._show_main_window(force_focus=True)
            app.root.update()
            default = pc_app.base.DEFAULT_APP_SIZE
            for factor in (0.8, 1.15):
                app.app_size = pc_app.base.nearest_app_size(
                    int(default[0] * factor), int(default[1] * factor))
                app._resize_main_window_nomove(*app.app_size)
                app._refresh_resize_surface()
                app.root.update_idletasks()
                app._reset_app_size()
                app.root.update_idletasks()
                first = app.countdown_card_metrics
                self.assertAlmostEqual(first[0] + first[2] / 2,
                                       app.countdown_canvas.winfo_width() / 2, delta=1)
                size = app.root.winfo_width(), app.root.winfo_height()
                self.assertEqual(size, default)
                app._reset_app_size()
                app.root.update_idletasks()
                self.assertEqual(app.countdown_card_metrics, first)
                self.assertEqual((app.root.winfo_width(), app.root.winfo_height()), size)
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            for after_id in app.root.tk.call('after', 'info'):
                app.root.after_cancel(after_id)
            app.root.destroy()

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
            for after_id in app.root.tk.call('after', 'info'):
                app.root.after_cancel(after_id)
            app.root.destroy()


if __name__ == '__main__':
    unittest.main()
