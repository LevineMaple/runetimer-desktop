"""Verify independent Janus audio settings through the desktop UI and alarm call site."""
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_booster_ui as fixture
from pc_janus import JanusSample
from pc_janus_reader import JanusTracker

pc = fixture.pc_app


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class JanusVolumeTests(unittest.TestCase):
    def setUp(self):
        settings = pc.base.SETTINGS_PATH
        old_data = settings.read_bytes()
        self.addCleanup(settings.write_bytes, old_data)
        data = json.loads(old_data)
        data.pop("janus_volume", None)
        data.pop("janus_sound_path", None)
        data.update(warning_volume=29, rune_volume=43, halfhour_volume=71)
        settings.write_text(json.dumps(data), encoding="utf-8")
        with patch.object(pc.PcTimerApp, "_show_startup_splash"), \
                patch.object(pc.PcTimerApp, "_sound_loop"), \
                patch.object(pc.PcTimerApp, "_start_monitor_worker"):
            self.app = pc.PcTimerApp()
        self.addCleanup(self.close_app)

    def close_app(self):
        app = self.app
        app.shutting_down = True
        app._janus_settings_changed()
        for callback in app.root.tk.call("after", "info"):
            app.root.after_cancel(callback)
        app.root.destroy()

    def trigger(self):
        app = self.app
        app._janus_tracker = JanusTracker()
        for now, seconds in ((0, 7), (1, 6), (2, 5), (3, 4)):
            app._apply_janus_sample(JanusSample(seconds, "test", now, 12, True, True))

    def test_slider_migrates_then_remains_independent(self):
        app = self.app
        self.assertEqual(app.janus_volume, 29)
        app._show_page("settings")
        app.root.update_idletasks()
        slider = next(w for w in descendants(app.settings_stack)
                      if isinstance(w, pc.base.VolumeSlider) and w.command == app._set_janus_volume)
        self.assertEqual(slider.value, 29)
        for level in (0, 62, 100):
            slider._set_from_event(SimpleNamespace(x=8 + (slider.width-62)*level/100))
            self.assertEqual(app._janus_audio.volume(), level)
            self.assertEqual((app.warning_volume, app.rune_volume, app.halfhour_volume), (29, 43, 71))
            app.janus_volume = -1
            app._load_settings()
            self.assertEqual(app.janus_volume, level)
            with patch.object(app._janus_audio, "play_once") as play:
                self.trigger()
                self.assertEqual(play.call_count, int(level > 0))
        app._set_warning_volume(0)
        with patch.object(app._janus_audio, "play_once") as play:
            self.trigger()
            play.assert_called_once()
        self.assertEqual(app._janus_audio.volume(), 100)

    def test_custom_sound_selection_cancel_missing_file_and_restore(self):
        app = self.app
        default = Path(pc.base.resource_path("assets", "sounds", "janus.wav"))
        with tempfile.TemporaryDirectory() as folder:
            selected = Path(folder, "my janus.wav")
            selected.write_bytes(default.read_bytes())
            menu = app.janus_sound_menu
            with patch.object(menu, "tk_popup"):
                app.janus_sound_settings_button.invoke()
            with patch.object(pc.base.filedialog, "askopenfilename", return_value=str(selected)):
                menu.invoke("음원 선택…")
            app.janus_sound_path = ""
            app._load_settings()
            self.assertEqual(Path(app.janus_sound_path), selected)
            with patch.object(pc.base.filedialog, "askopenfilename", return_value=""):
                app._choose_janus_sound()
            with patch.object(app._janus_audio, "play_once") as play:
                self.trigger()
                play.assert_called_once()
            self.assertEqual(Path(app._janus_audio.path), selected)
            with patch.object(menu, "tk_popup"):
                app.janus_sound_settings_button.invoke()
            with patch.object(app._janus_audio, "play_once") as play:
                menu.invoke("미리듣기")
                play.assert_called_once()
            selected.unlink()
            self.assertEqual(Path(app._janus_sound_file()), default)
            menu.invoke("기본음 복원")
            self.assertEqual(json.loads(pc.base.SETTINGS_PATH.read_text(encoding="utf-8"))["janus_sound_path"], "")
            self.assertEqual(Path(app._janus_sound_file()), default)


if __name__ == "__main__":
    unittest.main()
