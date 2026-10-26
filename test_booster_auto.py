"""Silent, deterministic tests of rune-disappearance booster sessions."""
import unittest
from unittest.mock import Mock, patch

from pc_booster import BoosterClock, BoosterMixin


class Harness(BoosterMixin):
    def __init__(self, uses=3):
        self.now = 0.0
        self.root = Mock()
        self._draw_bottom_dock = Mock()
        self._draw_widget_mode = Mock()
        self._update_widget_timer_display_lightweight = Mock()
        self._save_settings = Mock()
        with patch('pc_booster.BoosterAudio'):
            self._init_booster(lambda *p: '/'.join(p), Mock())
        self._booster_clock = BoosterClock(clock=lambda: self.now)
        self.booster_use_count = uses
        self._set_booster_mode_enabled(True)

    def detection(self, at, present, valid=True, generation=1):
        self.now = at
        self._booster_detection_update(present, valid, generation)

    def tick(self, at):
        self.now = at
        self._booster_tick()

    def arm(self, at=0):
        self.detection(at, True)
        self.detection(at + 1, False)

    def auto_start(self, at=0):
        self.arm(at)
        self.detection(at + 2, False)
        self.tick(at + 2)


class AutomaticStartTests(unittest.TestCase):
    def test_absence_without_observed_rune_never_starts(self):
        app = Harness()
        for at in (0, 1, 5, 10, 100):
            app.detection(at, False)
            app.tick(at)
        self.assertFalse(app.booster_running)
        app._booster_audio.play_once.assert_not_called()
        app._booster_audio.play_three.assert_not_called()

    def test_disappearance_waits_exactly_one_second_then_one_initial_utterance(self):
        app = Harness()
        app.arm()
        app.detection(1.5, False)
        app.tick(1.999)
        app._booster_audio.play_once.assert_not_called()
        app._booster_audio.play_three.assert_not_called()
        app.tick(2)
        app._booster_audio.play_once.assert_called_once()
        app._booster_audio.play_three.assert_not_called()
        self.assertTrue(app.booster_running)
        self.assertEqual(app.booster_remaining, 100)
        self.assertEqual(app._booster_auto_session['alerts'], 1)

    def test_reacquisition_cancels_previous_deadline(self):
        app = Harness()
        app.arm()
        app.detection(2, True)
        app.tick(3)
        app._booster_audio.play_once.assert_not_called()
        app._booster_audio.play_three.assert_not_called()
        app.detection(7, False)
        app.detection(7.5, False)
        app.tick(7.999)
        app._booster_audio.play_once.assert_not_called()
        app._booster_audio.play_three.assert_not_called()
        app.tick(8)
        app._booster_audio.play_once.assert_called_once()
        app._booster_audio.play_three.assert_not_called()

    def test_invalid_or_changed_capture_generation_cancels(self):
        for cause in ('invalid', 'generation', 'invalidate'):
            with self.subTest(cause=cause):
                app = Harness()
                app.arm()
                if cause == 'invalid':
                    app.detection(2, False, valid=False)
                elif cause == 'generation':
                    app.detection(2, False, generation=2)
                else:
                    app._booster_detection_invalidated()
                app.tick(3)
                self.assertFalse(app.booster_running)
                app._booster_audio.play_once.assert_not_called()
                app._booster_audio.play_three.assert_not_called()

    def test_stale_frame_over_2p5_seconds_cancels_not_delays(self):
        app = Harness()
        app.arm()
        app.tick(3.501)
        app._booster_audio.play_once.assert_not_called()
        app._booster_audio.play_three.assert_not_called()
        app.detection(7, False)
        app.tick(9)
        app._booster_audio.play_once.assert_not_called()
        app._booster_audio.play_three.assert_not_called()

    def test_frame_exactly_2p5_seconds_old_is_allowed(self):
        app = Harness()
        app.arm()
        app.tick(3.5)
        app._booster_audio.play_once.assert_called_once()
        app._booster_audio.play_three.assert_not_called()

    def test_mode_off_cancels_pending_and_reenable_does_not_resurrect(self):
        app = Harness()
        app.arm()
        app._set_booster_mode_enabled(False)
        app.detection(2, False)
        app.tick(3)
        app._set_booster_mode_enabled(True)
        app.detection(7, False)
        app.tick(9)
        app._booster_audio.play_once.assert_not_called()
        app._booster_audio.play_three.assert_not_called()

    def test_offline_and_excluded_map_cancel_pending(self):
        for flag in ('offline_mode_enabled', 'pc_map_audio_muted'):
            with self.subTest(flag=flag):
                app = Harness()
                app.arm()
                setattr(app, flag, True)
                app.detection(2, False)
                app.tick(3)
                app._booster_audio.play_once.assert_not_called()
                app._booster_audio.play_three.assert_not_called()


class SessionQuotaTests(unittest.TestCase):
    def test_one_use_is_only_initial_utterance_and_stops_after100(self):
        app = Harness(uses=1)
        app.auto_start()
        self.assertEqual(app._booster_auto_session['uses'], 1)
        app._booster_audio.play_once.assert_called_once()
        app.tick(99)
        self.assertEqual(app._booster_audio.play_three.call_count, 0)
        app.tick(102)
        self.assertFalse(app.booster_running)
        app._booster_audio.stop.assert_called_once()

    def test_five_uses_continue_past270_seconds_and_stop_after500(self):
        app = Harness(uses=5)
        app.auto_start()
        for elapsed, total in ((97, 2), (197, 3), (270, 3), (297, 4), (397, 5)):
            with self.subTest(elapsed=elapsed):
                app.tick(2 + elapsed)
                self.assertTrue(app.booster_running)
                self.assertEqual(app._booster_audio.play_three.call_count, total - 1)
        app.tick(499)  # +497 must not create an extra batch
        self.assertEqual(app._booster_audio.play_three.call_count, 4)
        app.tick(502)
        self.assertFalse(app.booster_running)

    def test_count_above270_is_not_clamped_or_treated_as_time_limit(self):
        app = Harness(uses=271)
        app.auto_start()
        self.assertEqual(app._booster_auto_session['uses'], 271)
        for cycle in range(270):
            app.tick(2 + cycle * 100 + 97)
        self.assertEqual(app._booster_audio.play_three.call_count, 270)
        self.assertTrue(app.booster_running)
        app.tick(2 + 271 * 100)
        self.assertFalse(app.booster_running)

    def test_missing_or_invalid_count_falls_back_to_three(self):
        invalid = (None, 0, -1, True, False, 2.5, 5.0, float('inf'),
                   float('nan'), '5', 'nonsense', [], {})
        for value in invalid:
            with self.subTest(value=value):
                app = Harness(uses=value)
                app.auto_start()
                self.assertEqual(app._booster_auto_session['uses'], 3)
                app.tick(99)
                app.tick(199)
                app.tick(299)
                self.assertEqual(app._booster_audio.play_three.call_count, 2)
                app.tick(302)
                self.assertFalse(app.booster_running)
        app = Harness()
        del app.booster_use_count
        app.auto_start()
        self.assertEqual(app._booster_auto_session['uses'], 3)

    def test_two_uses_means_initial_once_then_one_triple_batch(self):
        app = Harness(uses=2)
        app.auto_start()  # starts at2
        app._booster_audio.play_once.assert_called_once()
        app.tick(98.999)
        self.assertEqual(app._booster_audio.play_three.call_count, 0)
        app.tick(99)  # +97
        self.assertEqual(app.booster_remaining, 3)
        self.assertEqual(app._booster_audio.play_three.call_count, 1)
        app.tick(102)  # +100 rollover
        self.assertEqual(app.booster_remaining, 100)
        app.tick(199)  # +197, quota exhausted
        self.assertEqual(app._booster_audio.play_three.call_count, 1)
        app.tick(202)
        self.assertFalse(app.booster_running)
        app._booster_audio.stop.assert_called_once()

    def test_three_uses_adds_batch_at197_not_a_fourth_at297(self):
        app = Harness(uses=3)
        app.auto_start()
        app._booster_audio.play_once.assert_called_once()
        app._booster_audio.play_three.assert_not_called()
        app.tick(98.999)
        app._booster_audio.play_three.assert_not_called()
        app.tick(99)
        app._booster_audio.play_three.assert_called_once()
        app.tick(199)
        self.assertEqual(app._booster_audio.play_three.call_count, 2)
        app.tick(199)
        app.tick(299)
        self.assertEqual(app._booster_audio.play_three.call_count, 2)
        app.tick(302)
        self.assertFalse(app.booster_running)
        app._booster_audio.play_once.assert_called_once()

    def test_setting_change_applies_next_session_only(self):
        app = Harness(uses=3)
        app.auto_start()
        app.booster_use_count = 2
        app.tick(99)
        app.tick(199)
        self.assertEqual(app._booster_audio.play_three.call_count, 2)
        app.tick(302)
        app.auto_start(at=310)
        self.assertEqual(app._booster_auto_session['uses'], 2)
        app.tick(409)
        app.tick(509)
        self.assertEqual(app._booster_audio.play_three.call_count, 3)

    def test_sleep_skips_expired_quota_windows_without_catchup(self):
        app = Harness(uses=3)
        app.auto_start()
        app.tick(253)
        app.tick(299)
        self.assertEqual(app._booster_audio.play_three.call_count, 0)
        app.tick(497)
        self.assertFalse(app.booster_running)
        self.assertEqual(app._booster_audio.play_three.call_count, 0)

    def test_manual_start_stop_clears_pending_automatic_work(self):
        app = Harness()
        app.arm()
        app._toggle_booster()
        app._toggle_booster()
        app.detection(5, False)
        app.tick(3)
        app._booster_audio.play_once.assert_not_called()
        app._booster_audio.play_three.assert_not_called()
        self.assertFalse(app.booster_running)
        app._booster_audio.stop.assert_called_once()

    def test_rune_transitions_during_session_do_not_queue_next_session(self):
        app = Harness(uses=2)
        app.auto_start()
        app.detection(10, True)
        app.detection(11, False)
        app.tick(99)
        app.tick(202)
        app.detection(207, False)
        app.tick(209)
        self.assertFalse(app.booster_running)
        self.assertEqual(app._booster_audio.play_three.call_count, 1)


if __name__ == '__main__':
    unittest.main()
