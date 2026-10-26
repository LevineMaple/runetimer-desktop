"""Silent deterministic regressions for the independent booster reminder."""
import unittest
from unittest.mock import Mock, patch

from pc_booster import BoosterAudio, BoosterClock, BoosterMixin


class ClockTests(unittest.TestCase):
    def setUp(self):
        self.now = 10.0
        self.clock = BoosterClock(clock=lambda: self.now)

    def test_first_alert_at_97_seconds_with_three_seconds_remaining(self):
        self.clock.start()
        self.assertEqual(self.clock.remaining, 100)
        self.now = 106.999
        self.assertFalse(self.clock.poll())
        self.assertEqual(self.clock.remaining, 4)
        self.now = 107.0
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.remaining, 3)
        self.assertEqual(self.clock.deadline, 110)
        self.assertFalse(self.clock.poll())

    def test_100_second_rollover_and_197_second_next_alert(self):
        self.clock.start()
        self.now = 107
        self.assertTrue(self.clock.poll())
        self.now = 109
        self.assertEqual(self.clock.remaining, 1)
        self.assertFalse(self.clock.poll())
        self.now = 110
        self.assertFalse(self.clock.poll())
        self.assertEqual(self.clock.remaining, 100)
        self.now = 206  # just before the next scheduled alert
        self.assertFalse(self.clock.poll())
        self.now = 207
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.remaining, 3)

    def test_late_callback_preserves_original_cadence(self):
        self.clock.start()
        self.now = 109.0
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.deadline, 110.0)
        self.now = 114
        self.assertFalse(self.clock.poll())
        self.assertEqual(self.clock.remaining, 96)
        self.now = 207.0
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.deadline, 210.0)

    def test_sleep_skips_missed_periods_without_burst(self):
        self.clock.start()
        self.now = 1000.0
        self.assertFalse(self.clock.poll())
        self.assertEqual(self.clock.remaining, 10)
        self.now = 1007
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.deadline, 1010.0)
        self.assertFalse(self.clock.poll())
        self.assertFalse(self.clock.poll())

    def test_stop_and_restart_gets_fresh_full_interval(self):
        self.clock.start()
        self.now = 60.0
        self.clock.stop()
        self.now = 200.0
        self.assertFalse(self.clock.poll())
        self.assertEqual(self.clock.remaining, 100)
        self.clock.start()
        self.assertEqual(self.clock.deadline, 300.0)
        self.now = 296.999
        self.assertFalse(self.clock.poll())
        self.now = 297.0
        self.assertTrue(self.clock.poll())
        self.assertEqual(self.clock.remaining, 3)


class ImmediateEvent:
    """Cooperative fake event: never sleeps and can cancel during playback."""
    def __init__(self, on_wait=None):
        self.cancelled = False
        self.on_wait = on_wait

    def set(self):
        self.cancelled = True

    def is_set(self):
        return self.cancelled

    def wait(self, timeout):
        if self.on_wait:
            callback, self.on_wait = self.on_wait, None
            callback()
        return self.cancelled


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.commands = []
        self.audio = BoosterAudio('nonexistent-test-audio.mp3', on_error=Mock())

        def command(value, output=False):
            self.commands.append(value)
            return 'stopped' if output else ''

        self.audio._command = Mock(side_effect=command)

    def plays(self):
        return [c for c in self.commands if c.startswith('play ')]

    def test_three_sequential_utterances_close_only_own_alias(self):
        event = ImmediateEvent()
        self.audio._cancel = event
        self.audio._run(event)
        self.assertEqual(len(self.plays()), 3)
        alias = self.plays()[0].split()[1]
        self.assertTrue(alias.startswith('booster_'))
        self.assertEqual(self.commands[1:-2],
                         [c for _ in range(3) for c in
                          (f'seek {alias} to start', f'play {alias}', f'status {alias} mode')])
        self.assertEqual(self.commands[-2:], [f'stop {alias}', f'close {alias}'])
        self.audio.on_error.assert_not_called()

    def test_stop_during_first_utterance_prevents_other_two(self):
        event = ImmediateEvent(on_wait=self.audio.stop)
        self.audio._cancel = event
        self.audio._run(event)
        self.assertEqual(len(self.plays()), 1)
        self.assertTrue(event.is_set())
        self.assertIsNone(self.audio._alias)
        self.audio.on_error.assert_not_called()

    def test_half_second_gap_only_between_utterances(self):
        self.audio.repeat_gap = .5
        event = ImmediateEvent()
        event.wait = Mock(return_value=False)
        self.audio._run(event)
        self.assertEqual(len(self.plays()), 3)
        self.assertEqual([c.args[0] for c in event.wait.call_args_list], [.03, .5, .03, .5, .03])

    def test_play_once_plays_one_utterance_without_repeat_gap(self):
        self.audio.repeat_gap = .5
        pending = []

        def fake_thread(target, args, daemon):
            return Mock(start=lambda: pending.append((target, args)))

        with patch('pc_booster.threading.Thread', side_effect=fake_thread):
            self.audio.play_once()
            with patch.object(self.audio._cancel, 'wait', return_value=False) as wait:
                pending[0][0](*pending[0][1])
        self.assertEqual(len(self.plays()), 1)
        self.assertEqual([c.args[0] for c in wait.call_args_list], [.03])
        self.assertTrue(self.commands[-1].startswith('close booster_'))
        self.audio.on_error.assert_not_called()

    def test_live_volume_provider_applied_before_each_play(self):
        self.audio.volume = Mock(side_effect=[100, 25, 0])
        self.audio._run(ImmediateEvent())
        volumes = [c.rsplit(' ', 1)[-1] for c in self.commands if c.startswith('setaudio ')]
        self.assertEqual(volumes, ['1000', '250', '0'])
        for index, command in enumerate(self.commands):
            if command.startswith('play '):
                self.assertTrue(self.commands[index-2].startswith('setaudio '))

    def test_cancel_during_gap_prevents_next_utterance(self):
        self.audio.repeat_gap = .5
        event = ImmediateEvent()
        event.wait = Mock(side_effect=lambda seconds: seconds == .5)
        self.audio._run(event)
        self.assertEqual(len(self.plays()), 1)
        self.assertIsNone(self.audio._alias)

    def test_pending_old_generation_cannot_play_after_restart(self):
        pending = []

        def fake_thread(target, args, daemon):
            return Mock(start=lambda: pending.append((target, args)))

        with patch('pc_booster.threading.Thread', side_effect=fake_thread):
            self.audio.play_three()
            first_event = self.audio._cancel
            self.audio.stop()
            self.audio.play_three()
            self.assertTrue(first_event.is_set())
            self.assertIsNot(first_event, self.audio._cancel)
            pending[0][0](*pending[0][1])
            self.assertEqual(self.commands, [])
            # Replace the fresh event's wait only, to avoid real elapsed time.
            with patch.object(self.audio._cancel, 'wait', return_value=False):
                pending[1][0](*pending[1][1])
        self.assertEqual(len(self.plays()), 3)

    def test_decoder_failure_reports_once_and_closes_alias(self):
        original = self.audio._command.side_effect

        def fail_play(command, output=False):
            if command.startswith('play '):
                raise OSError('fake decoder failure')
            return original(command, output)

        self.audio._command.side_effect = fail_play
        self.audio._run(ImmediateEvent())
        self.audio.on_error.assert_called_once()
        self.assertIsNone(self.audio._alias)
        self.assertTrue(self.commands[-1].startswith('close booster_'))


class MixinHarness(BoosterMixin):
    def __init__(self):
        self.now = 0.0
        self._booster_clock = BoosterClock(clock=lambda: self.now)
        self._booster_audio = Mock()
        self.booster_mode_enabled = False
        self.booster_running = False
        self.booster_remaining = 100
        self._booster_after_id = None
        self.root = Mock()
        self._draw_bottom_dock = Mock()
        self._draw_widget_mode = Mock()
        self._update_widget_timer_display_lightweight = Mock()
        self._save_settings = Mock()


class MixinTests(unittest.TestCase):
    def test_off_does_not_start_or_alert(self):
        app = MixinHarness()
        app._toggle_booster()
        app.now = 1000
        app._booster_tick()
        self.assertFalse(app.booster_running)
        app._booster_audio.play_three.assert_not_called()

    def test_disable_cancels_running_audio_and_fresh_restart(self):
        app = MixinHarness()
        app._set_booster_mode_enabled(True)
        app._toggle_booster()
        app.now = 97
        app._booster_tick()
        app._booster_audio.play_three.assert_called_once()
        app._set_booster_mode_enabled(False)
        app._booster_audio.stop.assert_called_once()
        app.now = 200
        app._booster_tick()
        app._booster_audio.play_three.assert_called_once()
        app._set_booster_mode_enabled(True)
        app._toggle_booster()
        self.assertEqual(app.booster_remaining, 100)
        self.assertEqual(app._booster_clock.deadline, 300)

    def test_booster_independent_of_rune_warning_and_map_audio_mutes(self):
        app = MixinHarness()
        flags = dict(rune_sound_enabled=False, warning_sound_enabled=False,
                     monitor_enabled=False, offline_mode_enabled=True,
                     pc_map_audio_muted=True)
        for name, value in flags.items():
            setattr(app, name, value)
        app._set_booster_mode_enabled(True)
        app._toggle_booster()
        app.now = 97
        app._booster_tick()
        app._booster_audio.play_three.assert_called_once()
        self.assertEqual({name: getattr(app, name) for name in flags}, flags)

    def test_shutdown_tick_never_plays_or_reschedules(self):
        app = MixinHarness()
        app._set_booster_mode_enabled(True)
        app._toggle_booster()
        app.now = 97
        app.shutting_down = True
        app._booster_tick()
        app._booster_audio.play_three.assert_not_called()
        app.root.after.assert_not_called()


if __name__ == '__main__':
    unittest.main()
