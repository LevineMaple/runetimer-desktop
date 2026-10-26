"""Isolated actual-Tk checks for coupon layout, minute display and clicks."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

import test_booster_ui as fixture

appmod = fixture.pc_app


class CouponWidgetTests(unittest.TestCase):
    snapshot = fixture.BoosterUITests.snapshot

    def test_layout_minutes_pause_restart_and_drag(self):
        with patch.object(appmod.PcTimerApp, '_show_startup_splash'):
            app = appmod.PcTimerApp()
        try:
            app._ensure_widget_window()
            app.widget_mode_active = True
            app.widget.geometry(f'{appmod.base.WIDGET_WIDTH}x{appmod.base.WIDGET_HEIGHT}+60+60')
            app.widget.deiconify()
            app.widget.attributes('-alpha', 1.0)
            app._set_booster_mode_enabled(False)
            app._draw_widget_mode(force=True)
            app.root.update()
            self.assertIsNone(app.widget_coupon_text_item)
            self.assertFalse(app._point_in_widget_coupon(0, 0))
            app._add_halfhour()
            for booster in (False, True):
                with self.subTest(booster=booster):
                    app._set_booster_mode_enabled(booster)
                    app.root.update()
                    names = ['rune', 'booster', 'count', 'coupon'] if booster else ['rune', 'count', 'coupon']
                    regions = [getattr(app, f'widget_{name}_region') for name in names]
                    for left, right in zip(regions, regions[1:]):
                        self.assertLess(left[2], right[0])
                    for region in regions:
                        self.assertGreaterEqual(region[0], 0)
                        self.assertLessEqual(region[2], appmod.base.WIDGET_WIDTH)
                    self.assertGreater(app.widget_coupon_region[1], app.widget_restore_region[3])
                    self.assertTrue(app.widget_canvas.find_withtag('widget_coupon_icon'))
                    self.assertFalse(app.widget_canvas.find_withtag('widget_coupon_exp'))
                    self.assertFalse(app.widget_canvas.find_withtag('widget_coupon_leaf'))
                    self.assertEqual(app.widget_canvas.itemcget(app.widget_coupon_text_item, 'text'), '30')
                    self.snapshot(app.widget, 'coupon-booster-on' if booster else 'coupon-booster-off')

            now = [0.0]
            app._halfhour_clock.clock = lambda: now[0]
            app._halfhour_audio = Mock()
            # Both rendered icon and text route only to the coupon timer.
            app._toggle_booster = Mock()
            app._toggle_warning_countdown_pause = Mock()
            def click_tag(tag):
                bounds = app.widget_canvas.bbox(tag)
                x, y = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
                event = SimpleNamespace(x=x, y=y, x_root=60+x, y_root=60+y)
                app._start_widget_drag(event)
                app._end_widget_drag(event)
            click_tag('widget_coupon_icon')
            self.assertTrue(app.halfhour_running)
            for at, expected in ((0, '30'), (59.999, '30'), (60, '29'), (120, '28')):
                now[0] = at
                app._refresh_halfhour(redraw=False)
                app._update_widget_timer_display_lightweight()
                self.assertEqual(app.widget_canvas.itemcget(app.widget_coupon_text_item, 'text'), expected)
            click_tag('widget_coupon_minutes')
            self.assertFalse(app.halfhour_running)
            now[0] = 500
            app._refresh_halfhour(redraw=False)
            app._update_widget_timer_display_lightweight()
            self.assertEqual(app.widget_canvas.itemcget(app.widget_coupon_text_item, 'text'), '28')
            click_tag('widget_coupon_minutes')
            self.assertTrue(app.halfhour_running)
            self.assertEqual(app.halfhour_remaining, 1800)
            self.assertEqual(app.widget_canvas.itemcget(app.widget_coupon_text_item, 'text'), '30')

            r = app.widget_coupon_region
            start = SimpleNamespace(x=(r[0]+r[2])/2, y=(r[1]+r[3])/2, x_root=300, y_root=100)
            moved = SimpleNamespace(x=start.x+20, y=start.y, x_root=320, y_root=100)
            app._start_widget_drag(start)
            app._drag_widget(moved)
            app._end_widget_drag(moved)
            self.assertTrue(app.halfhour_running, 'drag must not stop coupon timer')
            app._toggle_booster.assert_not_called()
            app._toggle_warning_countdown_pause.assert_not_called()
            app._remove_halfhour()
            self.assertIsNone(app.widget_coupon_text_item)
            self.assertFalse(app.widget_canvas.find_withtag('widget_coupon_icon'))
            self.assertFalse(app.widget_canvas.find_withtag('widget_coupon_leaf'))
            self.assertFalse(app.widget_canvas.find_withtag('widget_coupon_exp'))
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            app._halfhour_audio.stop()
            app.root.destroy()


if __name__ == '__main__':
    unittest.main()
