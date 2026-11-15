"""Exercise the Janus switch, dock hit targets and persisted game-relative region."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_booster_ui as fixture


class JanusUITests(unittest.TestCase):
    def test_capture_button_and_saved_selection(self):
        pc = fixture.pc_app
        with patch.object(pc.PcTimerApp, '_show_startup_splash'), \
                patch.object(pc.PcTimerApp, '_sound_loop'), \
                patch.object(pc.PcTimerApp, '_start_monitor_worker'):
            app = pc.PcTimerApp()
        try:
            app._show_main_window(force_focus=True)
            app.root.update()
            self.assertFalse(app.janus_enabled)
            self.assertNotIn('janus', app.bottom_dock_regions)
            controls = []
            def collect(widget):
                if isinstance(widget, pc.base.ToggleSwitch):
                    controls.append(widget)
                for child in widget.winfo_children():
                    collect(child)
            collect(app.settings_stack)
            switch = next(control for control in controls if control.command == app._set_janus_enabled)
            switch.event_generate('<Button-1>')
            app.root.update()
            self.assertTrue(app.janus_enabled)
            for booster in (False, True):
                app._set_booster_mode_enabled(booster)
                app._draw_bottom_dock()
                regions = list(app.bottom_dock_regions.values())
                self.assertEqual(len(regions), 5 if booster else 4)
                for left, right in zip(regions, regions[1:]):
                    self.assertLess(left[2], right[0])
                self.assertGreaterEqual(regions[0][0], 0)
                self.assertLessEqual(regions[-1][2], app.bottom_dock.winfo_width())
                x1,y1,x2,y2 = app.bottom_dock_regions['janus']
                with patch.object(app, '_select_janus_region', create=True) as select:
                    app._handle_bottom_dock_click(SimpleNamespace(x=(x1+x2)//2, y=(y1+y2)//2))
                    select.assert_called_once_with()
            app.janus_region = (20, 10, 55, 45)
            app.janus_client_size = (1920, 1080)
            app._save_settings()
            app.janus_enabled = False
            app.janus_region = app.janus_client_size = None
            app._load_settings()
            self.assertTrue(app.janus_enabled)
            self.assertEqual(app.janus_region, (20, 10, 55, 45))
            self.assertEqual(app.janus_client_size, (1920, 1080))
            switch.event_generate('<Button-1>')
            self.assertFalse(app.janus_enabled)
            self.assertNotIn('janus', app.bottom_dock_regions)
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            app._halfhour_audio.stop()
            for after_id in app.root.tk.call('after', 'info'):
                app.root.after_cancel(after_id)
            app.root.destroy()
