"""Real Tk integration: settings, shared state, hit targets and drag gestures."""
import json
import os
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

_data = tempfile.TemporaryDirectory(prefix='booster-ui-')
profile = os.environ.get('BOOSTER_TEST_PROFILE', 'high')
os.environ['RUNE_TIMER_PC_DATA'] = _data.name
for name in ('settings.json', 'settings-low.json'):
    Path(_data.name, name).write_text(json.dumps({'disclaimer_accepted': True,
        'disclaimer_version': 1, 'warning_sound_enabled': False, 'rune_sound_enabled': False}))
Path(_data.name, 'ui-profile.json').write_text(json.dumps(profile))
import pc_app


class BoosterUITests(unittest.TestCase):
    def test_settings_dock_widget_and_drag(self):
        with patch.object(pc_app.PcTimerApp, '_show_startup_splash'):
            app = pc_app.PcTimerApp()
        try:
            app._show_main_window(force_focus=True)
            app.root.update()
            app._draw_bottom_dock()
            self.assertFalse(app.booster_mode_enabled)
            self.assertNotIn('booster', app.bottom_dock_regions)
            app._set_booster_mode_enabled(True)
            self.assertFalse(app.booster_running)
            self.assertEqual(list(app.bottom_dock_regions), ['scan', 'rune', 'booster', 'settings'])
            r = app.bottom_dock_regions['booster']
            app._handle_bottom_dock_click(SimpleNamespace(x=(r[0]+r[2])/2, y=(r[1]+r[3])/2))
            self.assertTrue(app.booster_running)
            app.root.update()
            self.snapshot(app.root, 'main')
            app._ensure_widget_window()
            app.widget_mode_active = True
            app.widget.geometry(f'{pc_app.base.WIDGET_WIDTH}x{pc_app.base.WIDGET_HEIGHT}+60+60')
            app.widget.deiconify()
            app.widget.attributes('-alpha', 1.0)
            app._draw_widget_mode(force=True)
            app.root.update()
            self.snapshot(app.widget, 'widget')
            canvas = app.widget_canvas
            def assert_state(paused):
                items = canvas.find_withtag('widget_count_state')
                self.assertEqual(len(items), 1 if paused else 2)
                self.assertTrue(all(canvas.type(item) == ('polygon' if paused else 'rectangle') for item in items))
                self.assertTrue(all(canvas.itemcget(item, 'fill') == '#e0fcf0' for item in items))
            def click_item(tag):
                x1,y1,x2,y2 = canvas.bbox(tag)
                x,y = int((x1+x2)/2),int((y1+y2)/2)
                canvas.event_generate('<ButtonPress-1>', x=x, y=y)
                canvas.event_generate('<ButtonRelease-1>', x=x, y=y)
                app.root.update()
            self.assertTrue(app.warning_timer_paused)
            assert_state(True)
            click_item('widget_count_state')
            self.assertFalse(app.warning_timer_paused)
            assert_state(False)
            now = time.monotonic()
            self.assertLess(app._warning_remaining_float(now+1), app._warning_remaining_float(now))
            self.snapshot(app.widget, 'widget-running')
            click_item(app.widget_count_text_item)
            self.assertTrue(app.warning_timer_paused)
            assert_state(True)
            self.assertEqual(app._warning_remaining_float(now+20), app._warning_remaining_float(now))
            self.snapshot(app.widget, 'widget-paused')
            x1,y1,x2,y2 = canvas.bbox('widget_count_state')
            x,y = int((x1+x2)/2),int((y1+y2)/2)
            canvas.event_generate('<ButtonPress-1>', x=x, y=y)
            canvas.event_generate('<B1-Motion>', x=x+20, y=y)
            canvas.event_generate('<ButtonRelease-1>', x=x+20, y=y)
            app.root.update()
            self.assertTrue(app.warning_timer_paused, 'count icon drag must not resume')
            assert_state(True)
            self.assertEqual(app.widget_canvas.itemcget(app.widget_count_text_item, 'fill'), '#ffffff')
            self.assertEqual(app.widget_canvas.itemcget(app.widget_booster_text_item, 'text'), str(app.booster_remaining))
            app.booster_remaining = 3
            app._update_widget_timer_display_lightweight()
            self.assertEqual(app.widget_canvas.itemcget(app.widget_booster_text_item, 'text'), '3')
            app.booster_remaining = 100
            r = app.widget_booster_region
            count = app.widget_count_region
            self.assertLess(app.widget_rune_region[2], r[0])
            self.assertLess(r[2], count[0])
            self.assertLess(count[2], app.widget_restore_region[0])
            event = SimpleNamespace(x=(r[0]+r[2])/2, y=(r[1]+r[3])/2, x_root=240, y_root=140)
            app._start_widget_drag(event)
            app._end_widget_drag(event)
            self.assertFalse(app.booster_running)
            app._start_widget_drag(event)
            moved = SimpleNamespace(x=event.x+20, y=event.y, x_root=260, y_root=140)
            app._drag_widget(moved)
            app._end_widget_drag(moved)
            self.assertFalse(app.booster_running, 'drag must not start booster')
            app._toggle_booster()
            self.assertTrue(app.booster_running)
            app._set_booster_mode_enabled(False)
            self.assertFalse(app.booster_running)
            self.assertNotIn('booster', app.bottom_dock_regions)
            self.assertFalse(app._point_in_widget_booster(event.x, event.y))
            app._set_booster_mode_enabled(True)
            app._toggle_booster()
            app._save_settings()
            saved = json.loads(pc_app.base.SETTINGS_PATH.read_text(encoding='utf-8'))
            self.assertTrue(saved['booster_mode_enabled'])
            self.assertNotIn('booster_running', saved)
            app.widget.withdraw()
            app.widget_mode_active = False
            app._show_page('settings')
            app._show_main_window(alpha=1.0, force_focus=True)
            until = time.monotonic() + 1.0
            while time.monotonic() < until:
                app.root.update()
                time.sleep(.02)
            app.root.attributes('-alpha', 1.0)
            app.root.lift()
            app.root.update()
            def descendants(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descendants(child)
            label = next(w for w in descendants(app.settings_stack)
                         if isinstance(w, pc_app.tk.Label) and w.cget('text') == '부스터 모드')
            switch = next(w for w in label.master.winfo_children() if isinstance(w, pc_app.base.ToggleSwitch))
            switch.set_value(True)
            switch._toggle()
            self.assertFalse(app.booster_mode_enabled)
            self.assertFalse(app.booster_running)
            switch._toggle()
            self.assertTrue(app.booster_mode_enabled)
            self.assertFalse(app.booster_running)
            app.booster_use_count_var.set('5')
            app.booster_use_count_apply_button.invoke()
            self.assertEqual(app.booster_use_count, 5)
            saved = json.loads(pc_app.base.SETTINGS_PATH.read_text(encoding='utf-8'))
            self.assertEqual(saved['booster_use_count'], 5)
            app.booster_use_count_var.set('0')
            app.booster_use_count_apply_button.invoke()
            self.assertEqual(app.booster_use_count, 5)
            app.booster_use_count_var.set('5')
            app.booster_use_count_apply_button.invoke()
            app.root.update()
            viewport = app.settings_viewport
            self.assertLessEqual(app.settings_stack.winfo_reqwidth(), viewport.winfo_width())
            self.assertLessEqual(app.settings_stack.winfo_reqheight(), viewport.winfo_height())
            vx, vy = viewport.winfo_rootx(), viewport.winfo_rooty()
            for control in descendants(app.settings_stack):
                if isinstance(control, pc_app.tk.Frame):
                    continue
                self.assertTrue(control.winfo_ismapped(), str(control))
                self.assertGreaterEqual(control.winfo_rootx(), vx, str(control))
                self.assertGreaterEqual(control.winfo_rooty(), vy, str(control))
                self.assertLessEqual(control.winfo_rootx() + control.winfo_width(), vx + viewport.winfo_width(), str(control))
                self.assertLessEqual(control.winfo_rooty() + control.winfo_height(), vy + viewport.winfo_height(), str(control))
            self.assertEqual(tuple(viewport.yview()), (0.0, 1.0))
            self.snapshot(app.root, 'settings')
        finally:
            app.shutting_down = True
            app._booster_audio.stop()
            app.root.destroy()

    def snapshot(self, window, name):
        destination = os.environ.get('BOOSTER_SCREENSHOTS')
        if not destination:
            return
        from PIL import ImageGrab
        folder = Path(destination)
        folder.mkdir(parents=True, exist_ok=True)
        window.lift()
        until = time.monotonic() + .25
        while time.monotonic() < until:
            window.update()
            time.sleep(.02)
        x, y = window.winfo_rootx(), window.winfo_rooty()
        ImageGrab.grab(bbox=(x,y,x+window.winfo_width(),y+window.winfo_height())).save(folder/f'{profile}-{name}.png')


if __name__ == '__main__':
    unittest.main()
