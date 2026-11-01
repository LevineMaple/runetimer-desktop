"""Real Tk regression checks for moving the live main window."""
import unittest
from types import SimpleNamespace
from unittest.mock import patch

# Reuse the isolated settings and disabled sounds from the UI test fixture.
from test_booster_ui import pc_app


class WindowMovementTests(unittest.TestCase):
    def test_settings_transition_preserves_actual_main_bounds(self):
        with patch.object(pc_app.PcTimerApp, '_show_startup_splash'):
            app = pc_app.PcTimerApp()
        try:
            app._show_main_window()
            app.root.update()
            app._reset_app_size()
            app.root.update_idletasks()
            bounds = (app.root.winfo_x(), app.root.winfo_y(),
                      app.root.winfo_width(), app.root.winfo_height())
            with patch.object(app, '_capture_restore_blur_image'), patch.object(app, '_show_restore_blur_overlay'):
                for name in ('settings', 'monitor', 'settings'):
                    app._switch_page_with_blur(name)
                    settled = pc_app.tk.BooleanVar(app.root, False)
                    app.root.after(300, lambda: settled.set(True))
                    app.root.wait_variable(settled)
                    self.assertEqual((app.root.winfo_x(), app.root.winfo_y(),
                                      app.root.winfo_width(), app.root.winfo_height()), bounds)
                    canvas = app.settings_backdrop if name == 'settings' else app.monitor_backdrop
                    coords = canvas.coords(canvas.find_withtag('resize_grip')[0])
                    sx = canvas.winfo_rootx() + int((coords[0] + coords[2]) / 2)
                    sy = canvas.winfo_rooty() + int((coords[1] + coords[3]) / 2)
                    image = pc_app.base.ImageGrab.grab(bbox=(sx-3, sy-3, sx+4, sy+4)).convert('RGB')
                    self.assertTrue(any(65 <= min(rgb) <= max(rgb) <= 120 and max(rgb)-min(rgb) < 20
                                        for rgb in [image.getpixel((x,y)) for x in range(7) for y in range(7)]))
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            for after_id in app.root.tk.call('after', 'info'):
                app.root.after_cancel(after_id)
            app.root.destroy()

    def test_settings_grip_matches_monitor_on_first_entry(self):
        with patch.object(pc_app.PcTimerApp, '_show_startup_splash'):
            app = pc_app.PcTimerApp()
        try:
            app._show_main_window()
            app.root.update()
            def position(canvas):
                line = canvas.find_withtag('resize_grip')[0]
                x, y = canvas.coords(line)[:2]
                return (x - canvas.canvasx(0) + canvas.winfo_rootx() - app.root.winfo_rootx(),
                        y - canvas.canvasy(0) + canvas.winfo_rooty() - app.root.winfo_rooty())
            expected = position(app.monitor_backdrop)
            app._show_page('settings')
            app.root.update_idletasks()
            self.assertEqual(position(app.settings_backdrop), expected)
            self.assertEqual((app.settings_backdrop.winfo_width(), app.settings_backdrop.winfo_height()),
                             (app.monitor_backdrop.winfo_width(), app.monitor_backdrop.winfo_height()))
            app._scroll_settings(SimpleNamespace(delta=-120, num=None))
            app.root.update_idletasks()
            self.assertEqual(position(app.settings_backdrop), expected)
            app._show_page('monitor')
            app.root.update_idletasks()
            self.assertEqual(position(app.monitor_backdrop), expected)
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            for after_id in app.root.tk.call('after', 'info'):
                app.root.after_cancel(after_id)
            app.root.destroy()

    def test_main_resize_lines_are_uncovered_at_every_size(self):
        with patch.object(pc_app.PcTimerApp, '_show_startup_splash'):
            app = pc_app.PcTimerApp()
        try:
            app._show_main_window()
            app.root.update()
            for width, height in pc_app.base.APP_SIZE_PRESETS:
                if width > app.root.winfo_screenwidth() or height > app.root.winfo_screenheight():
                    continue
                app.app_size = width, height
                app._resize_main_window_nomove(width, height)
                app._refresh_resize_surface()
                app.root.update_idletasks()
                canvas = app.monitor_backdrop
                items = canvas.find_withtag('resize_grip')
                self.assertEqual(len(items), 3)
                coords = canvas.coords(items[0])
                x, y = (coords[0] + coords[2]) / 2, (coords[1] + coords[3]) / 2
                # Inspect the rendered pixels, not just Canvas item existence.
                app._move_main_window(40, 40)
                app.root.update()
                settled = pc_app.tk.BooleanVar(app.root, False)
                app.root.after(120, lambda: settled.set(True))
                app.root.wait_variable(settled)
                coords = canvas.coords(canvas.find_withtag('resize_grip')[0])
                x, y = (coords[0] + coords[2]) / 2, (coords[1] + coords[3]) / 2
                self.assertGreaterEqual(x, 0)
                self.assertGreaterEqual(y, 0)
                self.assertLess(x, canvas.winfo_width())
                self.assertLess(y, canvas.winfo_height())
                sx, sy = canvas.winfo_rootx() + int(x), canvas.winfo_rooty() + int(y)
                pixels = pc_app.base.ImageGrab.grab(bbox=(sx-3, sy-3, sx+4, sy+4)).convert('RGB')
                self.assertTrue(any(65 <= min(rgb) <= max(rgb) <= 120 and max(rgb)-min(rgb) < 20
                                    for rgb in [pixels.getpixel((px, py)) for py in range(7) for px in range(7)]),
                              f'resize lines are not visible at {width}x{height}')
                dock = app.bottom_dock
                self.assertFalse(dock.winfo_x() <= x <= dock.winfo_x() + dock.winfo_width()
                                 and dock.winfo_y() <= y <= dock.winfo_y() + dock.winfo_height(),
                                 f'dock covers resize lines at {width}x{height}')
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            for after_id in app.root.tk.call('after', 'info'):
                app.root.after_cancel(after_id)
            app.root.destroy()

    def test_resize_lines_without_separate_widget(self):
        with patch.object(pc_app.PcTimerApp, '_show_startup_splash'):
            app = pc_app.PcTimerApp()
        save_patch = patch.object(app, '_save_settings')
        save_patch.start()
        self.addCleanup(save_patch.stop)
        try:
            app._show_main_window()
            app.root.update()
            self.assertFalse(hasattr(app, 'resize_grip'))
            for name in ('monitor', 'settings'):
                app._reset_app_size()
                app._show_page(name)
                app.root.update_idletasks()
                canvas = app.monitor_backdrop if name == 'monitor' else app.settings_backdrop
                items = canvas.find_withtag('resize_grip')
                self.assertEqual(len(items), 3)
                self.assertTrue(all(canvas.type(item) == 'line' for item in items))
                coords = canvas.coords(items[0])
                x = int((coords[0] + coords[2]) / 2 - canvas.canvasx(0))
                y = int((coords[1] + coords[3]) / 2 - canvas.canvasy(0))
                before = app.root.winfo_width(), app.root.winfo_height()
                canvas.event_generate('<Motion>', x=x, y=y)
                canvas.event_generate('<ButtonPress-1>', x=x, y=y)
                self.assertTrue(app.resizing_main_window)
                canvas.event_generate('<B1-Motion>', x=x-80, y=y-100)
                canvas.event_generate('<ButtonRelease-1>', x=x-80, y=y-100)
                app.root.update_idletasks()
                self.assertFalse(app.resizing_main_window)
                self.assertNotEqual((app.root.winfo_width(), app.root.winfo_height()), before)
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            for after_id in app.root.tk.call('after', 'info'):
                app.root.after_cancel(after_id)
            app.root.destroy()

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
