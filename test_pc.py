"""Regression checks for the same-PID auxiliary-window failure and alert flow."""
import os
import tempfile
from pathlib import Path
_test_data = tempfile.TemporaryDirectory(prefix='runetimer-tests-')
os.environ['RUNE_TIMER_PC_DATA'] = _test_data.name
for _name in ('settings.json', 'settings-low.json'):
    (Path(_test_data.name) / _name).write_text('{}', encoding='utf-8')
(Path(_test_data.name) / 'ui-profile.json').write_text('"high"', encoding='utf-8')
import unittest
from unittest.mock import Mock, patch
from PIL import Image,ImageDraw
import pc_app as a
import pc_capture as c

class RegressionTests(unittest.TestCase):
    def test_same_pid_auxiliary_is_never_selected(self):
        # Exact rectangles observed on the user's PC (same title and process).
        aux=dict(hwnd=1969474,pid=20392,rect=(2110,1594,2520,2400))
        game=dict(hwnd=1182570,pid=20392,rect=(494,425,2414,1505))
        for candidates in ([aux,game],[game,aux]):
            self.assertEqual(c.rank_game_windows(candidates,(0,0,2560,1600)),[game])

    def test_move_follows_client_origin_without_wrong_scaling(self):
        with patch.object(c,'desktop_bounds',return_value=(-1920,0,2560,1600)):
            self.assertEqual(c.translate_region((0,58,204,154),(-1920,0,0,1080)),(-1920,58,-1716,154))
            self.assertEqual(c.translate_region((0,58,204,154),(494,425,2414,1505)),(494,483,698,579))
            with self.assertRaises(ValueError):c.translate_region((0,58,204,154),(0,0,180,1080))

    def test_invalid_regions_fail_before_capture(self):
        with self.assertRaises(ValueError):c.validate_region((2112,1594,2179,1786),(0,0,2560,1600))
        with self.assertRaises(ValueError):c.validate_region((5,5,5,20),(0,0,2560,1600))

    def app_stub(self):
        p=a.PcTimerApp.__new__(a.PcTimerApp)
        for key,value in dict(capture_generation=1,pc_selecting=False,offline_mode_enabled=False,pc_anchor_error=None,
            pc_hit_count=0,pc_miss_count=0,rune_alert_latched=False,rune_threshold=50.,rune_score=0.,last_rune_alert_at=0.,rune_alert_interval=3.,
            rune_region=(494,483,698,579)).items():setattr(p,key,value)
        for name in ('_sync_rune_region_to_maplestory_window','_play','_clear_queued_sound','_set_rune_visual','_set_rune_capture_active','_set_auto_detect_status','_refresh_diagnostics','_log_status'):
            setattr(p,name,Mock())
        return p

    def test_confirm_alert_clear_and_reject_stale_result(self):
        p=self.app_stub()
        hit=dict(generation=1,minimap_ok=True,score=88,error=False,region=p.rune_region)
        p._apply_monitor_result(hit)
        p._play.assert_not_called()
        p._apply_monitor_result(hit)
        p._play.assert_called_once_with('rune');self.assertTrue(p.rune_alert_latched)
        p._apply_monitor_result(dict(hit,score=0))
        self.assertTrue(p.rune_alert_latched)
        p._apply_monitor_result(dict(hit,score=0))
        self.assertFalse(p.rune_alert_latched)
        p._play.reset_mock()
        p._apply_monitor_result(dict(hit,generation=0));p._play.assert_not_called()
        p.offline_mode_enabled=True
        p._apply_monitor_result(hit);p._play.assert_not_called()

    def test_capture_failure_clears_alert_and_records_details(self):
        p=self.app_stub();p.rune_alert_latched=True
        p._apply_monitor_result(dict(generation=1,error='test failure',region=p.rune_region))
        self.assertFalse(p.rune_alert_latched);p._clear_queued_sound.assert_called_with('rune')
        self.assertIn('region=',p._log_status.call_args.args[1])

    def test_original_detector_positive_and_negative(self):
        # Synthetic minimap distinguishes a purple hollow diamond from player dots.
        p=a.PcTimerApp.__new__(a.PcTimerApp)
        im=Image.new('RGB',(204,110),(10,14,18));d=ImageDraw.Draw(im)
        d.rectangle((8,10,196,100),outline=(240,240,240),width=2)
        d.ellipse((40,45,47,52),fill=(255,230,0))
        d.ellipse((125,45,132,52),fill=(245,90,130))
        cropped=p._crop_minimap_view(im)
        self.assertIsNotNone(cropped);self.assertLess(p._score_rune(cropped,True),50)
        d.polygon([(85,45),(91,51),(85,57),(79,51)],fill=(200,120,255))
        d.polygon([(85,49),(87,51),(85,53),(83,51)],fill=(10,14,18))
        self.assertGreaterEqual(p._score_rune(p._crop_minimap_view(im),True),50)

if __name__=='__main__':unittest.main(verbosity=2)
