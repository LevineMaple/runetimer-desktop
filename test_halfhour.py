"""Deterministic, silent tests for the fixed thirty-minute reminder."""
import unittest
from unittest.mock import Mock, patch

from pc_halfhour import HalfHourClock, HalfHourMixin
from pc_booster import BoosterClock, BoosterMixin


class HalfHourClockTests(unittest.TestCase):
    def setUp(self):
        self.now = 0.0
        self.clock = HalfHourClock(clock=lambda: self.now)

    def test_launch_stopped_and_full_thirty_minutes(self):
        self.assertFalse(self.clock.running)
        self.assertEqual(self.clock.remaining, 1800)
        self.now = 1790
        self.assertFalse(self.clock.poll())

    def test_alert_at_29m50_once_does_not_restart_countdown(self):
        self.clock.start()
        self.now = 1789.999
        self.assertFalse(self.clock.poll())
        self.now = 1790
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.remaining, 10)
        self.assertFalse(self.clock.poll())
        self.now = 1799
        self.assertEqual(self.clock.remaining, 1)
        self.assertFalse(self.clock.poll())

    def test_boundary_resets_1800_and_next_alert_at_3590(self):
        self.clock.start()
        self.now = 1790
        self.assertTrue(self.clock.poll())
        self.now = 1800
        self.assertFalse(self.clock.poll())
        self.assertEqual(self.clock.remaining, 1800)
        self.now = 3580
        self.assertFalse(self.clock.poll())
        self.now = 3589.999
        self.assertFalse(self.clock.poll())
        self.now = 3590
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.remaining, 10)
        self.assertFalse(self.clock.poll())

    def test_late_callback_keeps_original_cycle_phase(self):
        self.clock.start()
        self.now = 1797.5
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.remaining, 3)
        self.now = 1804
        self.assertFalse(self.clock.poll())
        self.assertEqual(self.clock.remaining, 1796)
        self.now = 3590
        self.assertTrue(self.clock.poll())

    def test_sleep_past_old_cycles_skips_stale_alerts(self):
        self.clock.start()
        self.now = 7201
        self.assertFalse(self.clock.poll())
        self.assertEqual(self.clock.remaining, 1799)
        self.now = 8990
        self.assertTrue(self.clock.poll())
        self.assertFalse(self.clock.poll())
        self.assertFalse(self.clock.poll())

    def test_sleep_into_current_alert_window_emits_only_once(self):
        self.clock.start()
        self.now = 8995
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.remaining, 5)
        for _ in range(5):
            self.assertFalse(self.clock.poll())

    def test_stop_and_restart_waits_full_new_cycle(self):
        self.clock.start()
        self.now = 1790
        self.assertTrue(self.clock.poll())
        self.clock.stop()
        self.assertEqual(self.clock.remaining, 1800)
        self.now = 4000
        self.assertFalse(self.clock.poll())
        self.clock.start()
        self.assertEqual(self.clock.remaining, 1800)
        self.now = 5789.999
        self.assertFalse(self.clock.poll())
        self.now = 5790
        self.assertTrue(self.clock.poll())

    def test_pause_freezes_value_and_restart_begins_full_cycle(self):
        self.clock.start()
        self.now = 61.25
        self.clock.pause()
        self.assertFalse(self.clock.running)
        self.assertEqual(self.clock.remaining, 1739)
        self.now = 6000
        self.assertEqual(self.clock.remaining, 1739)
        self.assertFalse(self.clock.poll())
        self.clock.start()
        self.assertEqual(self.clock.remaining, 1800)
        self.now = 7789.999
        self.assertFalse(self.clock.poll())
        self.now = 7790
        self.assertTrue(self.clock.poll())

    def test_stop_clears_a_paused_value(self):
        self.clock.start()
        self.now = 60
        self.clock.pause()
        self.clock.stop()
        self.assertEqual(self.clock.remaining, 1800)


class TimerHarness(HalfHourMixin, BoosterMixin):
    def __init__(self):
        self.now = 0.0
        self.root = Mock()
        self._draw_countdown_display = Mock()
        self._update_countdown_display_lightweight = Mock()
        self._draw_bottom_dock = Mock()
        self._draw_widget_mode = Mock()
        self._update_widget_timer_display_lightweight = Mock()
        self._save_settings = Mock()
        resource = lambda *parts: '/'.join(parts)
        with patch('pc_halfhour.BoosterAudio') as half_audio:
            self._init_halfhour(resource, Mock())
            self.half_audio_constructor = half_audio
        with patch('pc_booster.BoosterAudio') as booster_audio:
            self._init_booster(resource, Mock())
            self.booster_audio_constructor = booster_audio
        self._halfhour_clock = HalfHourClock(clock=lambda: self.now)
        self._booster_clock = BoosterClock(clock=lambda: self.now)


class HalfHourIntegrationTests(unittest.TestCase):
    def test_coupon_audio_uses_own_live_volume(self):
        app = TimerHarness()
        volume = app.half_audio_constructor.call_args.kwargs['volume']
        self.assertEqual(volume(), 100)
        app.warning_volume = 83
        app.rune_volume = 91
        for value in (0, 37, 100):
            app.halfhour_volume = value
            self.assertEqual(volume(), value)
            self.assertEqual(app.warning_volume, 83)
            self.assertEqual(app.rune_volume, 91)

    def test_widget_click_freezes_then_restarts_with_fresh_full_time(self):
        app = TimerHarness()
        app._add_halfhour()
        app._toggle_widget_halfhour()
        app.now = 61
        app._toggle_widget_halfhour()
        self.assertFalse(app.halfhour_running)
        self.assertEqual(app.halfhour_remaining, 1739)
        app._halfhour_audio.stop.assert_called_once()
        app.now = 2000
        app._halfhour_tick()
        self.assertEqual(app.halfhour_remaining, 1739)
        app._halfhour_audio.play_three.assert_not_called()
        app._toggle_widget_halfhour()
        self.assertTrue(app.halfhour_running)
        self.assertEqual(app.halfhour_remaining, 1800)
        app.now = 3790
        app._halfhour_tick()
        app._halfhour_audio.play_three.assert_called_once()

    def test_widget_visibility_and_value_are_refreshed(self):
        app = TimerHarness()
        app._add_halfhour()
        app._draw_widget_mode.assert_called_with(force=True)
        app._toggle_widget_halfhour()
        app.now = 60
        app._halfhour_tick()
        app._update_widget_timer_display_lightweight.assert_called_once()
        app._remove_halfhour()
        self.assertFalse(app.halfhour_enabled)
        self.assertEqual(app.halfhour_remaining, 1800)
        app._draw_widget_mode.assert_called_with(force=True)
        app._toggle_widget_halfhour()
        self.assertFalse(app.halfhour_running)

    def test_add_displays_stopped_timer_and_does_not_play(self):
        app = TimerHarness()
        app._add_halfhour()
        self.assertTrue(app.halfhour_enabled)
        self.assertFalse(app.halfhour_running)
        self.assertEqual(app.halfhour_remaining, 1800)
        app.now = 1790
        app._halfhour_tick()
        app._halfhour_audio.play_three.assert_not_called()
        app._save_settings.assert_called_once()

    def test_restored_visibility_never_restores_running_countdown(self):
        app = TimerHarness()
        app.halfhour_enabled = True  # persisted visibility only
        app.now = 7190
        app._halfhour_tick()
        self.assertFalse(app.halfhour_running)
        self.assertEqual(app.halfhour_remaining, 1800)
        app._halfhour_audio.play_three.assert_not_called()

    def test_three_play_alert_once_then_full_boundary_without_second_alert(self):
        app = TimerHarness()
        app._add_halfhour()
        app._toggle_halfhour()
        app.now = 1790
        app._halfhour_tick()
        app._halfhour_tick()
        app._halfhour_audio.play_three.assert_called_once()
        self.assertEqual(app.halfhour_remaining, 10)
        app.now = 1800
        app._halfhour_tick()
        self.assertEqual(app.halfhour_remaining, 1800)
        app._halfhour_audio.play_three.assert_called_once()

    def test_stop_halfhour_does_not_stop_or_reset_booster(self):
        app = TimerHarness()
        app._add_halfhour()
        app._toggle_halfhour()
        app._set_booster_mode_enabled(True)
        app._toggle_booster()
        app.now = 10
        app._toggle_halfhour()
        app._halfhour_audio.stop.assert_called_once()
        app._booster_audio.stop.assert_not_called()
        self.assertTrue(app._booster_clock.running)
        self.assertEqual(app._booster_clock.remaining, 90)
        self.assertEqual(app.halfhour_remaining, 1800)

    def test_simultaneous_alerts_use_separate_players_and_assets(self):
        app = TimerHarness()
        self.assertIsNot(app._halfhour_audio, app._booster_audio)
        self.assertEqual(app.half_audio_constructor.call_args.args[0],
                         'assets/sounds/tts_halfhour.mp3')
        self.assertEqual(app.booster_audio_constructor.call_args.args[0],
                         'assets/sounds/tts_booster.mp3')
        app._add_halfhour()
        app._toggle_halfhour()
        app.now = 1693  # Booster's 97-second alert coincides with the 1790-second half-hour alert.
        app._set_booster_mode_enabled(True)
        app._toggle_booster()
        app.now = 1790
        app._halfhour_tick()
        app._booster_tick()
        app._halfhour_audio.play_three.assert_called_once()
        app._booster_audio.play_three.assert_called_once()

    def test_shutdown_suppresses_alert_and_rearming(self):
        app = TimerHarness()
        app._add_halfhour()
        app._toggle_halfhour()
        app.now = 1790
        app.shutting_down = True
        app._halfhour_tick()
        app.root.after.assert_not_called()
        app._halfhour_audio.play_three.assert_not_called()


if __name__ == '__main__':
    unittest.main()
