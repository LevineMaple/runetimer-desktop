"""Isolated settings persistence and real-Tk coupon volume slider checks."""
import json
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_booster_ui as fixture

appmod = fixture.pc_app


class CouponVolumeUITests(unittest.TestCase):
    def test_slider_persistence_and_visible_settings(self):
        with patch.object(appmod.PcTimerApp, '_show_startup_splash'), \
                patch.object(appmod.PcTimerApp, '_sound_loop'), \
                patch.object(appmod.PcTimerApp, '_start_monitor_worker'):
            app = appmod.PcTimerApp()
        try:
            self.assertEqual(app.halfhour_volume, 100)
            app._show_page('settings')
            app._show_main_window(alpha=1.0, force_focus=True)
            backdrop = appmod.tk.Toplevel(app.root)
            backdrop.overrideredirect(True)
            backdrop.configure(bg='#101416')
            backdrop.geometry(f'{app.root.winfo_screenwidth()}x{app.root.winfo_screenheight()}+0+0')
            backdrop.lower(app.root)
            app.root.geometry('+900+150')
            app.root.attributes('-topmost', True)
            until = time.monotonic() + .7
            while time.monotonic() < until:
                app.root.update()
                time.sleep(.02)

            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)

            label = next(w for w in descendants(app.settings_stack)
                         if isinstance(w, appmod.tk.Label) and w.cget('text') == '30분 쿠폰 볼륨')
            slider = next(w for w in label.master.winfo_children()
                          if isinstance(w, appmod.base.VolumeSlider))
            other_volumes = (app.warning_volume, app.rune_volume)
            for value in (0, 37, 100):
                slider._set_from_event(SimpleNamespace(x=8 + (slider.width-62)*value/100))
                self.assertEqual(app.halfhour_volume, value)
                self.assertEqual(slider.value, value)
                saved = json.loads(appmod.base.SETTINGS_PATH.read_text(encoding='utf-8'))
                self.assertEqual(saved['halfhour_volume'], value)
                app.halfhour_volume = -1
                app._load_settings()
                self.assertEqual(app.halfhour_volume, value)
                self.assertEqual((app.warning_volume, app.rune_volume), other_volumes)

            for raw, expected in ((-10, 0), (150, 100), ('invalid', 100), (None, 100)):
                saved['halfhour_volume'] = raw
                appmod.base.SETTINGS_PATH.write_text(json.dumps(saved), encoding='utf-8')
                app._load_settings()
                self.assertEqual(app.halfhour_volume, expected)
            saved.pop('halfhour_volume')
            appmod.base.SETTINGS_PATH.write_text(json.dumps(saved), encoding='utf-8')
            app._load_settings()
            self.assertEqual(app.halfhour_volume, 100)
            app._set_halfhour_volume(100)
            app.root.update()
            viewport = app.settings_viewport
            self.assertLessEqual(app.settings_stack.winfo_reqwidth(), viewport.winfo_width())
            self.assertLessEqual(app.settings_stack.winfo_reqheight(), viewport.winfo_height())
            vx, vy = viewport.winfo_rootx(), viewport.winfo_rooty()
            for control in descendants(app.settings_stack):
                if isinstance(control, appmod.tk.Frame):
                    continue
                self.assertTrue(control.winfo_ismapped())
                self.assertGreaterEqual(control.winfo_rootx(), vx)
                self.assertGreaterEqual(control.winfo_rooty(), vy)
                self.assertLessEqual(control.winfo_rootx()+control.winfo_width(), vx+viewport.winfo_width())
                self.assertLessEqual(control.winfo_rooty()+control.winfo_height(), vy+viewport.winfo_height())
            self.assertEqual(tuple(viewport.yview()), (0.0, 1.0))
            fixture.BoosterUITests().snapshot(app.root, 'settings-coupon-volume')
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            app._halfhour_audio.stop()
            app.root.destroy()


if __name__ == '__main__':
    unittest.main()
