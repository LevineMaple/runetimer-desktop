"""Map-specific automatic rune audio regression tests; no actual playback."""
import queue
import unittest
from unittest.mock import Mock, patch
import test_pc
import pc_app as a
from pathlib import Path
from PIL import Image, ImageDraw


class MapAudioFlowTests(unittest.TestCase):
    def app(self):
        p = test_pc.RegressionTests().app_stub()
        p.pc_map_audio_muted = False
        p.rune_sound_enabled = True
        p.warning_sound_enabled = True
        p._set_rune_capture_active = Mock()
        return p

    def result(self, muted, **extra):
        return dict(generation=1, minimap_ok=True, score=55.78, error=False,
                    region=(494, 483, 698, 579), map_audio_muted=muted, **extra)

    def test_target_silent_then_other_map_requires_two_fresh_hits(self):
        p = self.app()
        for _ in range(4):
            p._apply_monitor_result(self.result(True))
        self.assertTrue(p.pc_map_audio_muted)
        p._play.assert_not_called()
        self.assertIn('알림음 자동 끔', p.pc_status)
        p._apply_monitor_result(self.result(False))
        self.assertFalse(p.pc_map_audio_muted)
        p._play.assert_not_called()
        p._apply_monitor_result(self.result(False))
        p._play.assert_called_once_with('rune')

    def test_manual_sound_setting_is_preserved_and_other_sounds_work(self):
        p = self.app()
        p.rune_sound_enabled = False
        p._set_map_audio_muted(True)
        self.assertFalse(p._sound_enabled_for_key('rune'))
        for key in ('warning', 'skill', 'done', 'test_rune'):
            self.assertTrue(p._sound_enabled_for_key(key))
        p._set_map_audio_muted(False)
        self.assertFalse(p.rune_sound_enabled)
        self.assertFalse(p._sound_enabled_for_key('rune'))

    def test_stale_or_selecting_result_cannot_change_mute(self):
        p = self.app()
        p._set_map_audio_muted(True)
        result = self.result(False)
        result['generation'] = 0
        p._apply_monitor_result(result)
        self.assertTrue(p.pc_map_audio_muted)
        p.pc_selecting = True
        p._apply_monitor_result(self.result(False))
        self.assertTrue(p.pc_map_audio_muted)

    def test_capture_error_resets_detection_and_does_not_play(self):
        p = self.app()
        p._set_map_audio_muted(True)
        p._apply_monitor_result(dict(generation=1, error='capture failed'))
        self.assertFalse(p.rune_alert_latched)
        self.assertFalse(p.pc_map_audio_muted)
        p._play.assert_not_called()

    def test_manual_mode_does_not_keep_stale_map_mute(self):
        p = self.app()
        p._set_map_audio_muted(True)
        p.offline_mode_enabled = True
        self.assertTrue(p._sound_enabled_for_key('rune'))
        p.rune_sound_enabled = False
        self.assertFalse(p._sound_enabled_for_key('rune'))

    def test_entering_mute_removes_pending_runes_only(self):
        p = self.app()
        p.sound_queue = queue.Queue()
        p._clear_queued_sound = a.base.MapleTimerApp._clear_queued_sound.__get__(p)
        for key in ('rune', 'warning', 'test_rune', 'skill'):
            p.sound_queue.put((key, key + '.wav', 30))
        p._set_map_audio_muted(True)
        self.assertEqual([item[0] for item in p.sound_queue.queue],
                         ['warning', 'test_rune', 'skill'])
        self.assertEqual(p.sound_queue.unfinished_tasks, 3)

    def test_audio_worker_rechecks_mute_before_playback(self):
        p = self.app()
        p.pc_map_audio_muted = True
        p.sound_queue = Mock()
        p.sound_queue.get.side_effect = [
            ('rune', 'rune.wav', 30), ('warning', 'warning.wav', 30), KeyboardInterrupt]
        with patch.object(a.base.winsound, 'PlaySound') as play:
            with self.assertRaises(KeyboardInterrupt):
                p._sound_loop()
            play.assert_called_once_with('warning.wav', a.base.winsound.SND_FILENAME)
        self.assertEqual(p.sound_queue.task_done.call_count, 2)

    def test_real_capture_through_worker_then_title_change_resumes_audio(self):
        saved = Path(__file__).parent / 'tests/fixtures/four_seasons_capture.png'
        p = self.app()
        p.root = Mock()
        p.root.winfo_viewable.return_value = False
        p._get_app_rect = Mock(return_value=(144,184,450,390))
        p.pc_diag = p.widget = None
        p.monitor_worker_running = False
        p.rune_region = (146,195,366,374)
        p.pc_selected_window = dict(rect=(144,184,2064,1264))
        p.pc_map_matcher = a.MapAudioMatcher()
        p.worker_results = queue.Queue()
        combined = Image.new('RGB', (540,190), 'black')
        combined.paste(Image.open(saved).convert('RGB'), (2,11))
        p._grab_frame = Mock(return_value=combined)

        def immediate_thread(*, target, daemon):
            return Mock(start=target)

        with patch.object(a.threading, 'Thread', side_effect=immediate_thread):
            for muted in (True, True, False, False):
                if not muted:
                    # Change only the map-name area. The actual false-positive
                    # minimap remains unchanged at its original score.
                    ImageDraw.Draw(combined).rectangle((46,30,175,65),fill='black')
                p.monitor_worker_running = False
                p._start_monitor_worker()
                _, result = p.worker_results.get_nowait()
                self.assertFalse(result['error'])
                self.assertTrue(result['minimap_ok'])
                self.assertEqual(result['map_audio_muted'], muted)
                self.assertAlmostEqual(result['score'], 55.779569892473134)
                p._apply_monitor_result(result)
            p._play.assert_called_once_with('rune')
        self.assertEqual(p._grab_frame.call_count, 4)
        p._grab_frame.assert_called_with((144,184,684,374))


if __name__ == '__main__':
    unittest.main(verbosity=2)
