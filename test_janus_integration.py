"""Janus capture, scheduling and expiry cues without a live game window."""
from concurrent.futures import Future
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

_profile = tempfile.TemporaryDirectory(prefix='janus-integration-')
os.environ['RUNE_TIMER_PC_DATA'] = _profile.name
for name in ('settings.json', 'settings-low.json'):
    Path(_profile.name, name).write_text(json.dumps({'disclaimer_accepted': True,
                                                    'disclaimer_version': 1}))
import pc_app
import pc_janus


class JanusCaptureTests(unittest.TestCase):
    game = {'hwnd': 12, 'rect': (200, 400, 1200, 1000)}
    region = (8, 30, 48, 70)

    def observe(self, game, visible, *, cancelled=False, size=(1000, 600)):
        event = threading.Event()
        if cancelled:
            event.set()
        with patch.object(pc_janus.cap, 'maple_windows', return_value=[game] if game else []), \
                patch.object(pc_janus, 'visible_game_region', return_value=visible), \
                patch.object(pc_janus, 'grab_icon') as grab, \
                patch.object(pc_janus, 'read_observation', return_value=(True, None)):
            sample = pc_janus.sample_janus(self.region, size, event)
        return sample, grab

    def test_icon_only_and_no_pixels_if_target_invalid(self):
        sample, grab = self.observe(self.game, True)
        grab.assert_called_once_with((208, 430, 248, 470))
        self.assertTrue(sample.icon_present)
        self.assertIsNone(sample.seconds)
        for game, visible, size in ((None, False, (1000, 600)),
                                    (self.game, False, (1000, 600)),
                                    (self.game, True, (800, 500))):
            sample, grab = self.observe(game, visible, size=size)
            grab.assert_not_called()
            self.assertFalse(sample.icon_present)
        sample, grab = self.observe(self.game, True, cancelled=True)
        grab.assert_not_called()
        self.assertIsNone(sample)


class JanusIntegrationTests(unittest.TestCase):
    def setUp(self):
        app = self.app = object.__new__(pc_app.PcTimerApp)
        app.janus_enabled = app.main_app_started = True
        app.pc_selecting = app.offline_mode_enabled = app.shutting_down = False
        app.janus_region, app.janus_client_size = (8, 30, 48, 70), (1000, 600)
        app._janus_tracker = pc_app.JanusTracker()
        app._janus_after = app._janus_future = app._janus_hwnd = None
        app._janus_cancel = threading.Event()
        app._janus_next_sample = 0
        app._janus_audio = Mock()
        app._janus_executor = Mock()
        app.janus_volume = 100
        app.janus_sound_path = ""
        app.root = Mock()

    def stream(self, start, observations):
        for elapsed, (seconds, present) in enumerate(observations):
            self.app._apply_janus_sample(pc_janus.JanusSample(
                seconds, 'sample', start+elapsed, 123, present))

    def test_widget_time_follows_capture_extension_and_expiry(self):
        label = self.app._janus_widget_text
        self.assertEqual(label(0), '--:--')
        self.stream(0, [(80, True), (79, True)])
        self.assertEqual(label(1), '1:19')
        self.stream(2, [(120, True), (119, True)])
        self.assertEqual(label(3), '1:59')
        self.stream(115, [(7, True), (6, True), (None, True)])
        self.assertEqual(label(117), '0:05')
        self.assertEqual(label(122), '--:--')
        self.stream(123, [(80, True), (79, True), (None, False)])
        self.assertEqual(label(125), '--:--')

    def test_digitless_tail_extension_and_covered_region(self):
        # A known countdown reaches the five-second deadline with a visible,
        # digitless icon. Subsequent frames do not replay the same cue.
        self.stream(0, [(9, True), (8, True), (7, True), (6, True), (None, True),
                        (None, True)])
        self.app._janus_audio.play_once.assert_called_once()
        # Server's newly extended countdown is observed and then reaches 5.
        self.stream(6, [(10, True), (9, True), (8, True), (7, True), (6, True),
                        (5, True), (None, True)])
        self.assertEqual(self.app._janus_audio.play_once.call_count, 2)
        self.stream(13, [(10, True), (9, True), (8, True), (7, True), (6, True),
                         (None, False), (None, False), (None, True)])
        self.assertEqual(self.app._janus_audio.play_once.call_count, 2)

    def test_observed_game_region_loses_icon_near_expiry(self):
        self.stream(0, [(13, True), (12, True), (11, True)])
        for now in range(3, 16):
            self.app._apply_janus_sample(pc_janus.JanusSample(
                None, 'empty HUD slot', now, 123, False, region_observed=True))
            self.assertEqual(self.app._janus_audio.play_once.call_count, int(now >= 8))

    def test_disabled_offline_and_reselect_discard_inflight_result(self):
        for flag, value in [('janus_enabled', False), ('offline_mode_enabled', True),
                            ('pc_selecting', True), ('shutting_down', True)]:
            with self.subTest(flag=flag):
                app = self.app
                app.janus_enabled, app.offline_mode_enabled = True, False
                app.pc_selecting, app.shutting_down = False, False
                setattr(app, flag, value)
                cancel = app._janus_cancel = threading.Event()
                stale = app._janus_future = Future()
                stale.set_running_or_notify_cancel()
                app._janus_after = 'pending'
                app.root.reset_mock()
                app._janus_settings_changed()
                self.assertTrue(cancel.is_set())
                self.assertIsNone(app._janus_future)
                stale.set_result(pc_janus.JanusSample(5, 'stale', 999, 123, True))
                app._janus_tick()
                app._janus_audio.play_once.assert_not_called()
                app.root.after.assert_not_called()
                app._janus_executor.submit.assert_not_called()

    def test_wide_skill_bar_saves_and_samples_same_rectangle(self):
        app = self.app
        game = JanusCaptureTests.game
        app._save_settings = Mock()
        app._janus_settings_changed = Mock()
        selection = (230, 450, 1100, 540)
        with patch.object(app, '_choose_game', return_value=game):
            app._set_janus_region(game, selection)
        app._save_settings.assert_called_once()
        self.assertEqual(app.janus_region, (30, 50, 900, 140))
        with patch.object(pc_janus.cap, 'maple_windows', return_value=[game]), \
                patch.object(pc_janus, 'visible_game_region', return_value=True), \
                patch.object(pc_janus, 'grab_icon') as grab, \
                patch.object(pc_janus, 'read_observation', return_value=(True, 35)):
            sample = pc_janus.sample_janus(app.janus_region, app.janus_client_size, threading.Event())
        grab.assert_called_once_with(selection)
        self.assertEqual(sample.seconds, 35)

    def test_region_coordinates_saved_relative_and_cancel_preserves_selection(self):
        app = self.app
        game = JanusCaptureTests.game
        app._save_settings = Mock()
        app._janus_settings_changed = Mock()
        with patch.object(app, '_choose_game', return_value=game):
            app._set_janus_region(game, (230, 450, 268, 488))
        self.assertEqual(app.janus_region, (30, 50, 68, 88))
        self.assertEqual(app.janus_client_size, (1000, 600))
        app._save_settings.assert_called_once()
        with patch.object(app, '_choose_game', return_value=game), \
                patch.object(pc_app.messagebox, 'showinfo') as message:
            app._set_janus_region(game, (0, 0, 32, 32))
            message.assert_called_once()
        app._save_settings.assert_called_once()
        self.assertEqual(app.janus_region, (30, 50, 68, 88))


if __name__ == '__main__':
    unittest.main()
