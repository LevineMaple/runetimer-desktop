"""Exercise Janus values and controls in the real desktop widget canvas."""
import itertools
import unittest
from unittest.mock import patch

import test_booster_ui as fixture
from pc_janus import JanusSample

pc = fixture.pc_app


class JanusWidgetTests(unittest.TestCase):
    def setUp(self):
        with patch.object(pc.PcTimerApp, "_show_startup_splash"), \
                patch.object(pc.PcTimerApp, "_sound_loop"), \
                patch.object(pc.PcTimerApp, "_start_monitor_worker"):
            self.app = pc.PcTimerApp()
        self.addCleanup(self.close_app)
        app = self.app
        app._ensure_widget_window()
        app.widget_mode_active = True
        app.widget.geometry(f"{pc.base.WIDGET_WIDTH}x{pc.base.WIDGET_HEIGHT}+60+60")
        app.widget.deiconify()
        app.root.update_idletasks()

    def close_app(self):
        app = self.app
        app.shutting_down = True
        app._janus_settings_changed()
        app._booster_audio.stop()
        app._halfhour_audio.stop()
        for callback in app.root.tk.call("after", "info"):
            app.root.after_cancel(callback)
        app.root.destroy()

    def test_layout_combinations_and_visible_values(self):
        app = self.app
        canvas = app.widget_canvas
        for booster, coupon, janus in itertools.product((False, True), repeat=3):
            with self.subTest(booster=booster, coupon=coupon, janus=janus):
                app.booster_mode_enabled, app.halfhour_enabled, app.janus_enabled = booster, coupon, janus
                with patch.object(app, "_janus_widget_text", return_value="4:59"):
                    app._draw_widget_mode(force=True)
                    app._update_widget_timer_display_lightweight()
                self.assertEqual(bool(canvas.find_withtag("widget_janus_icon")), janus)
                self.assertEqual(app.widget_janus_text_item is not None, janus)
                if not janus:
                    continue
                text = app.widget_janus_text_item
                self.assertEqual(canvas.itemcget(text, "text"), "4:59")
                for item in (text, "widget_janus_icon"):
                    x1, y1, x2, y2 = canvas.bbox(item)
                    self.assertGreaterEqual(x1, 0)
                    self.assertGreaterEqual(y1, 0)
                    self.assertLessEqual(x2, pc.base.WIDGET_WIDTH)
                    self.assertLessEqual(y2, pc.base.WIDGET_HEIGHT)
                    for name, enabled in (("restore", True), ("rune", True), ("count", True),
                                          ("booster", booster), ("coupon", coupon)):
                        if enabled:
                            left, top, right, bottom = getattr(app, f"widget_{name}_region")
                            self.assertTrue(x2 <= left or right <= x1 or y2 <= top or bottom <= y1,
                                            f"Janus overlaps {name}")
                for other in canvas.find_all():
                    if other == text or canvas.type(other) != "text":
                        continue
                    left, _, right, _ = canvas.bbox(other)
                    x1, _, x2, _ = canvas.bbox(text)
                    self.assertTrue(x2 <= left or right <= x1)

    def test_detected_time_extension_and_loss(self):
        app = self.app
        app.janus_enabled = True
        app.janus_region = (10, 10, 70, 70)
        app.janus_client_size = (1920, 1080)
        app._draw_widget_mode(force=True)
        canvas = app.widget_canvas
        def display(at):
            app._update_widget_timer_display_lightweight(at)
            return canvas.itemcget(app.widget_janus_text_item, "text")
        self.assertEqual(display(99), "--:--")
        for at, seconds in ((100, 81), (101, 80), (102, 79), (103, 120), (104, 119)):
            app._apply_janus_sample(JanusSample(seconds, "read", at, 12, True, True))
            if at in (101, 102, 104):
                self.assertEqual(display(at), f"{seconds // 60}:{seconds % 60:02d}")
        app._apply_janus_sample(JanusSample(None, "covered window", 105, 12, False, False))
        self.assertEqual(display(105), "--:--")
