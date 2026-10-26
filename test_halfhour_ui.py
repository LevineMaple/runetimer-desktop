"""Actual Tk click routing, horizontal square layout and restart persistence."""
import json
import time
from unittest.mock import patch
import unittest
import test_booster_ui as fixture

appmod = fixture.pc_app


class HalfHourUITests(unittest.TestCase):
    snapshot = fixture.BoosterUITests.snapshot

    def assert_control_above_cards(self, app, region, tag):
        self.assertGreaterEqual(region[1], 0)
        for card in app.halfhour_card_regions:
            self.assertLess(region[3], card[1], 'control hit area must be above every card')
        bounds = app.countdown_canvas.bbox(tag)
        self.assertIsNotNone(bounds)
        self.assertLess(bounds[3], min(card[1] for card in app.halfhour_card_regions))
        for item in app.countdown_canvas.find_withtag(tag):
            tags = app.countdown_canvas.gettags(item)
            self.assertNotIn('countdown_card', tags)
            self.assertNotIn('halfhour_card_0', tags)
            self.assertNotIn('halfhour_card_1', tags)

    def click(self, app, region):
        delayed = region in (app.halfhour_add_region, app.halfhour_remove_region)
        before = app.halfhour_enabled
        x, y = int((region[0]+region[2])/2), int((region[1]+region[3])/2)
        canvas = app.countdown_canvas
        def event_click():
            canvas.event_generate('<Motion>', x=x, y=y)
            canvas.event_generate('<ButtonPress-1>', x=x, y=y)
            canvas.event_generate('<ButtonRelease-1>', x=x, y=y)
            app.root.update()
        if delayed:
            # Capture only the control's scheduled callback: live screen capture
            # can stall Tk for >300ms and make a wall-clock assertion flaky.
            original_after = app.root.after
            callbacks = []
            def schedule(ms, callback=None, *args):
                if callback is not None and getattr(callback, '__name__', '') == 'apply_delayed':
                    self.assertEqual(ms, 300)
                    callbacks.append(callback)
                    return 'test-control-delay'
                return original_after(ms, callback, *args)
            with patch.object(app.root, 'after', side_effect=schedule):
                event_click()
                self.assertEqual(app.halfhour_enabled, before, 'plus/minus must not apply immediately')
                pending = app._halfhour_control_after_id
                self.assertIsNotNone(pending)
                event_click()
                self.assertEqual(app._halfhour_control_after_id, pending, 'duplicate click must reuse pending action')
                self.assertEqual(len(callbacks), 1)
                self.assertEqual(app.halfhour_enabled, before)
            callbacks[0]()
            app.root.update()
            self.assertNotEqual(app.halfhour_enabled, before)
            self.assertIsNone(app._halfhour_control_after_id)
        else:
            event_click()

    def test_two_cards_and_relaunch_stopped(self):
        with patch.object(appmod.PcTimerApp, '_show_startup_splash'):
            app = appmod.PcTimerApp()
        try:
            app._show_main_window(alpha=1, force_focus=True)
            app.root.update()
            app._set_booster_mode_enabled(True)
            self.assertFalse(app.halfhour_enabled)
            self.assert_control_above_cards(app, app.halfhour_add_region, 'halfhour_add')
            self.snapshot(app.root, 'single-plus')
            self.click(app, app.halfhour_add_region)
            self.assertTrue(app.halfhour_enabled)
            self.assertTrue(app.warning_timer_paused, 'plus must not start primary')
            self.assertFalse(app._halfhour_clock.running)
            self.assertEqual(app._halfhour_clock.remaining, 1800)
            self.assertIsNone(app.halfhour_add_region)
            self.assert_control_above_cards(app, app.halfhour_remove_region, 'halfhour_remove')
            for items in app._halfhour_ui_items:
                self.assertEqual(app.countdown_canvas.itemcget(items[0], 'fill'), '#8a9094')
            first, second = app.halfhour_card_regions
            self.assertLess(first[2], second[0])
            for r in (first, second):
                self.assertEqual(r[2]-r[0], r[3]-r[1])
            self.click(app, second)
            self.assertTrue(app._halfhour_clock.running)
            self.assertTrue(app.warning_timer_paused)
            self.click(app, first)
            self.assertFalse(app.warning_timer_paused)
            self.assertTrue(app._halfhour_clock.running)
            for items in app._halfhour_ui_items:
                self.assertEqual(app.countdown_canvas.itemcget(items[0], 'fill'), '#ffffff')
            self.snapshot(app.root, 'two-counters')
            self.click(app, second)
            self.assertFalse(app._halfhour_clock.running)
            self.assertEqual(app._halfhour_clock.remaining, 1800)
            second_number = app._halfhour_ui_items[1][0]
            self.assertEqual(app.countdown_canvas.itemcget(second_number, 'fill'), '#8a9094')
            self.snapshot(app.root, 'mixed-counters')
            self.assertFalse(app.warning_timer_paused)
            app._save_settings()
            data = json.loads(appmod.base.SETTINGS_PATH.read_text(encoding='utf-8'))
            self.assertTrue(data['halfhour_enabled'])
            self.assertNotIn('halfhour_running', data)
        finally:
            app.shutting_down = True
            app._halfhour_audio.stop()
            app._booster_audio.stop()
            app.root.destroy()
        with patch.object(appmod.PcTimerApp, '_show_startup_splash'):
            restored = appmod.PcTimerApp()
        try:
            self.assertTrue(restored.halfhour_enabled)
            self.assertFalse(restored._halfhour_clock.running)
            self.assertEqual(restored._halfhour_clock.remaining, 1800)
            restored._show_main_window(alpha=1, force_focus=True)
            restored.root.update()
            restored._toggle_halfhour()
            restored._toggle_warning_countdown_pause()
            with patch.object(restored._halfhour_audio, 'stop') as stop:
                self.click(restored, restored.halfhour_remove_region)
                stop.assert_called_once()
            self.assertFalse(restored.halfhour_enabled)
            self.assertFalse(restored._halfhour_clock.running)
            self.assertFalse(restored.warning_timer_paused, 'remove must preserve primary state')
            self.assertEqual(len(restored.halfhour_card_regions), 1)
            self.assertIsNotNone(restored.halfhour_add_region)
            self.assert_control_above_cards(restored, restored.halfhour_add_region, 'halfhour_add')
            self.assertEqual(restored.countdown_canvas.itemcget(restored.countdown_number_item, 'fill'), '#ffffff')
            restored._toggle_warning_countdown_pause()
            self.assertEqual(restored.countdown_canvas.itemcget(restored.countdown_number_item, 'fill'), '#8a9094')
            saved = json.loads(appmod.base.SETTINGS_PATH.read_text(encoding='utf-8'))
            self.assertFalse(saved['halfhour_enabled'])
            self.click(restored, restored.halfhour_add_region)
            self.assertTrue(restored.halfhour_enabled)
            self.assertFalse(restored._halfhour_clock.running)
            self.assertEqual(restored._halfhour_clock.remaining, 1800)
        finally:
            restored.shutting_down = True
            restored.root.destroy()


if __name__ == '__main__':
    unittest.main()
