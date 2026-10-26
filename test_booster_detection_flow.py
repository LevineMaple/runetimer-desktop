"""Real detector-result routing into automatic booster reminders; silent."""
import unittest
from unittest.mock import Mock
import test_pc as fixture
from pc_booster import BoosterClock


class DetectionBoosterTests(unittest.TestCase):
    def setUp(self):
        self.now = 0
        self.app = fixture.RegressionTests().app_stub()
        p = self.app
        p._init_booster(lambda *parts: '/'.join(parts), Mock())
        p._booster_clock = BoosterClock(clock=lambda: self.now)
        p._booster_audio = Mock()
        p.booster_mode_enabled = True
        p.booster_use_count = 4
        p.root = Mock()
        p._draw_bottom_dock = Mock()
        p._draw_widget_mode = Mock()
        p._update_widget_timer_display_lightweight = Mock()

    def result(self, score, **extra):
        data = dict(generation=self.app.capture_generation, minimap_ok=True,
                    score=score, error=False, map_audio_muted=False)
        data.update(extra)
        self.app._apply_monitor_result(data)

    def disappear(self):
        self.result(88)
        self.result(88)
        self.now = 2
        self.result(0)
        self.result(0)
        self.assertEqual(self.app._booster_pending_at, 3)

    def test_detector_clear_starts_after_one_second_then_uses_preference(self):
        self.disappear()
        self.now = 2.999
        self.result(0)
        self.app._booster_tick()
        self.app._booster_audio.play_once.assert_not_called()
        self.app._booster_audio.play_three.assert_not_called()
        self.now = 3
        self.app._booster_tick()
        self.app._booster_audio.play_once.assert_called_once()
        self.app._booster_audio.play_three.assert_not_called()
        self.assertEqual(self.app._booster_auto_session['uses'], 4)
        self.assertEqual(self.app.booster_remaining, 100)

    def test_failed_capture_cannot_be_a_rune_clear(self):
        self.disappear()
        self.now = 3
        self.result(0, error='capture failure')
        self.now = 4
        self.app._booster_tick()
        self.app._booster_audio.play_once.assert_not_called()
        self.app._booster_audio.play_three.assert_not_called()

    def test_muted_map_cancels_pending_start(self):
        self.disappear()
        self.now = 3
        self.result(0, map_audio_muted=True)
        self.now = 4
        self.app._booster_tick()
        self.app._booster_audio.play_once.assert_not_called()
        self.app._booster_audio.play_three.assert_not_called()

    def test_new_capture_generation_does_not_inherit_pending_start(self):
        self.disappear()
        self.app.capture_generation += 1
        self.now = 3
        self.result(0)
        self.now = 4
        self.app._booster_tick()
        self.app._booster_audio.play_once.assert_not_called()
        self.app._booster_audio.play_three.assert_not_called()


    def test_new_rune_resets_running_booster_then_rearms_after_clear(self):
        self.disappear()
        self.now = 4
        self.result(0)
        self.app._booster_tick()
        self.assertTrue(self.app.booster_running)
        self.now = 22
        self.result(88)
        self.assertTrue(self.app.booster_running)  # One candidate is insufficient.
        self.result(88)
        self.assertFalse(self.app.booster_running)
        self.assertEqual(self.app.booster_remaining, 100)
        self.assertIsNone(self.app._booster_auto_session)
        self.app._booster_audio.stop.reset_mock()
        self.result(88)
        self.result(88)
        self.app._booster_audio.stop.assert_not_called()  # Same rune repeats.
        self.now = 30
        self.result(0)
        self.result(0)
        self.assertEqual(self.app._booster_pending_at, 31)
        self.now = 31
        self.result(0)
        self.app._booster_tick()
        self.assertTrue(self.app.booster_running)
        self.assertEqual(self.app._booster_auto_session['alerts'], 1)
        self.assertEqual(self.app._booster_auto_session['uses'], 4)

    def test_muted_new_rune_does_not_reset_running_booster(self):
        self.app._toggle_booster()
        self.result(88, map_audio_muted=True)
        self.result(88, map_audio_muted=True)
        self.assertTrue(self.app.booster_running)


if __name__ == '__main__':
    unittest.main()
