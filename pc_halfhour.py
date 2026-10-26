"""Optional independent 30-minute countdown with an alert ten seconds early."""
import math
import time

from pc_booster import BoosterAudio


class HalfHourClock:
    INTERVAL = 1800
    ALERT_AT = 1790

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.running = False
        self.started_at = None
        self._alerted_cycle = -1
        self._paused_remaining = self.INTERVAL

    def start(self):
        self.started_at = self.clock()
        self._alerted_cycle = -1
        self._paused_remaining = self.INTERVAL
        self.running = True

    def stop(self):
        self.running = False
        self.started_at = None
        self._alerted_cycle = -1
        self._paused_remaining = self.INTERVAL

    def pause(self):
        """Freeze the shown value; start() always begins a new full cycle."""
        if self.running:
            self._paused_remaining = self.remaining
            self.running = False
            self.started_at = None

    def _phase(self):
        elapsed = max(0.0, self.clock() - self.started_at)
        cycle = math.floor(elapsed / self.INTERVAL)
        return cycle, elapsed - cycle * self.INTERVAL

    @property
    def remaining(self):
        if not self.running:
            return self._paused_remaining
        _, phase = self._phase()
        return math.ceil(self.INTERVAL - phase)

    def poll(self):
        """Alert once in the current cycle's final ten seconds, never catch up."""
        if not self.running:
            return False
        cycle, phase = self._phase()
        if phase >= self.ALERT_AT and cycle > self._alerted_cycle:
            self._alerted_cycle = cycle
            return True
        return False


class HalfHourMixin:
    def _init_halfhour(self, resource_path, log_error):
        self.halfhour_enabled = False
        self.halfhour_running = False
        self.halfhour_remaining = 1800
        self._halfhour_clock = HalfHourClock()
        self._halfhour_audio = BoosterAudio(
            resource_path('assets', 'sounds', 'tts_halfhour.mp3'),
            lambda exc: log_error('halfhour_audio', exc),
            volume=lambda: getattr(self, 'halfhour_volume', 100))
        self._halfhour_after_id = None

    def _refresh_halfhour(self, redraw=True):
        self.halfhour_running = self._halfhour_clock.running
        self.halfhour_remaining = self._halfhour_clock.remaining
        if redraw:
            self._draw_countdown_display()
            draw_widget = getattr(self, '_draw_widget_mode', None)
            if draw_widget is not None:
                draw_widget(force=True)

    def _add_halfhour(self):
        self.halfhour_enabled = True
        self._refresh_halfhour()
        self._save_settings()

    def _toggle_halfhour(self):
        if not self.halfhour_enabled:
            return
        if self._halfhour_clock.running:
            self._halfhour_clock.stop()
            self._halfhour_audio.stop()
        else:
            self._halfhour_clock.start()
        self._refresh_halfhour()

    def _remove_halfhour(self):
        self._halfhour_clock.stop()
        self._halfhour_audio.stop()
        self.halfhour_enabled = False
        self._refresh_halfhour()
        self._save_settings()

    def _toggle_widget_halfhour(self):
        if not self.halfhour_enabled:
            return
        if self._halfhour_clock.running:
            self._halfhour_clock.pause()
            self._halfhour_audio.stop()
        else:
            self._halfhour_clock.start()
        self._refresh_halfhour()

    def _halfhour_tick(self):
        self._halfhour_after_id = None
        if getattr(self, 'shutting_down', False):
            return
        old = (self.halfhour_running, self.halfhour_remaining)
        if self.halfhour_enabled and self._halfhour_clock.poll():
            self._halfhour_audio.play_three()
        self._refresh_halfhour(redraw=False)
        if old != (self.halfhour_running, self.halfhour_remaining):
            self._update_countdown_display_lightweight()
            update_widget = getattr(self, '_update_widget_timer_display_lightweight', None)
            if update_widget is not None:
                update_widget()
        self._halfhour_after_id = self.root.after(100, self._halfhour_tick)

    def _quit_app(self):
        self._halfhour_clock.stop()
        self._halfhour_audio.stop()
        if self._halfhour_after_id is not None:
            try:
                self.root.after_cancel(self._halfhour_after_id)
            except Exception:
                pass
            self._halfhour_after_id = None
        return super()._quit_app()
