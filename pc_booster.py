"""100-second booster cycles with a three-play alert three seconds early."""
import ctypes
import math
import threading
import time
import uuid


class BoosterClock:
    def __init__(self, clock=time.monotonic, interval=100.0):
        self.clock = clock
        self.interval = float(interval)
        if self.interval <= 0:
            raise ValueError('interval must be positive')
        self.running = False
        self.deadline = None
        self.started_at = None
        self._alerted_cycle = -1

    def start(self):
        self.running = True
        self.started_at = self.clock()
        self.deadline = self.started_at + self.interval
        self._alerted_cycle = -1

    def stop(self):
        self.running = False
        self.deadline = None
        self.started_at = None
        self._alerted_cycle = -1

    def _phase(self):
        elapsed = max(0.0, self.clock() - self.started_at)
        cycle = math.floor(elapsed / self.interval)
        self.deadline = self.started_at + (cycle + 1) * self.interval
        return cycle, elapsed - cycle * self.interval

    def poll(self):
        """Alert once in the final three seconds; do not restart early/catch up."""
        if not self.running:
            return False
        cycle, phase = self._phase()
        if phase >= max(0.0, self.interval - 3.0) and cycle > self._alerted_cycle:
            self._alerted_cycle = cycle
            return True
        return False

    @property
    def remaining(self):
        if not self.running:
            return math.ceil(self.interval)
        _, phase = self._phase()
        return math.ceil(self.interval - phase)


class BoosterAudio:
    """Owns one MCI alias; cancellation never stops the app's other sounds."""
    def __init__(self, path, on_error=None, repeat_gap=0.0, volume=None):
        self.path = str(path)
        self.on_error = on_error
        self.repeat_gap = max(0.0, float(repeat_gap))
        self.volume = volume
        self._lock = threading.Lock()
        self._cancel = None
        self._alias = None
        self._thread = None

    def _command(self, command, output=False):
        buffer = ctypes.create_unicode_buffer(256) if output else None
        code = ctypes.windll.winmm.mciSendStringW(command, buffer, 256 if output else 0, None)
        if code:
            raise OSError(f'Booster audio MCI error {code}')
        return buffer.value if buffer is not None else ''

    def _close_locked(self, alias):
        if self._alias == alias:
            self._alias = None
        if alias:
            for command in (f'stop {alias}', f'close {alias}'):
                try:
                    self._command(command)
                except OSError:
                    pass

    def stop(self):
        with self._lock:
            if self._cancel is not None:
                self._cancel.set()
            worker = self._thread
        # MCI aliases are thread-local: the owning worker must stop/close.
        # Event.wait wakes immediately, so it need not finish the current clip.
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=0.5)

    def play_three(self):
        self._play(3)

    def play_once(self):
        self._play(1)

    def _play(self, repetitions):
        self.stop()
        cancelled = threading.Event()
        worker = threading.Thread(target=self._run, args=(cancelled, repetitions), daemon=True)
        with self._lock:
            self._cancel = cancelled
            self._thread = worker
        worker.start()

    def _run(self, cancelled, repetitions=3):
        alias = 'booster_' + uuid.uuid4().hex
        opened = False
        try:
            with self._lock:
                if cancelled.is_set():
                    return
                safe_path = self.path.replace('"', '')
                self._command(f'open "{safe_path}" type mpegvideo alias {alias}')
                opened = True
                self._alias = alias
            for repetition in range(repetitions):
                with self._lock:
                    if cancelled.is_set():
                        return
                    if self.volume is not None:
                        value = self.volume() if callable(self.volume) else self.volume
                        level = round(max(0.0, min(100.0, float(value))) * 10)
                        self._command(f'setaudio {alias} volume to {level}')
                    self._command(f'seek {alias} to start')
                    self._command(f'play {alias}')
                while not cancelled.wait(0.03):
                    with self._lock:
                        if cancelled.is_set():
                            return
                        if self._command(f'status {alias} mode', output=True).strip() != 'playing':
                            break
                if cancelled.is_set():
                    return
                if repetition < repetitions - 1 and self.repeat_gap and cancelled.wait(self.repeat_gap):
                    return
        except Exception as exc:
            if not cancelled.is_set() and self.on_error:
                self.on_error(exc)
        finally:
            with self._lock:
                if opened:
                    self._close_locked(alias)


class BoosterMixin:
    def _init_booster(self, resource_path, log_error):
        self.booster_mode_enabled = False
        self.booster_running = False
        self.booster_remaining = 100
        self._booster_clock = BoosterClock()
        self._booster_audio = BoosterAudio(resource_path('assets', 'sounds', 'tts_booster.mp3'),
                                           lambda exc: log_error('booster_audio', exc), repeat_gap=0.5,
                                           volume=lambda: getattr(self, 'warning_volume', 100))
        self._booster_after_id = None
        self._booster_detection_invalidated()
        self._booster_auto_session = None

    def _booster_detection_invalidated(self):
        """Forget transitions/pending work, including when called before init."""
        self._booster_seen_rune = False
        self._booster_pending_at = None
        self._booster_last_valid_at = None
        self._booster_detection_generation = None

    def _booster_new_rune_detected(self):
        """Replace the previous character/rune cycle on a fresh detection edge."""
        clock = getattr(self, '_booster_clock', None)
        if clock is None:
            return
        self._booster_detection_invalidated()
        self._booster_auto_session = None
        clock.stop()
        self._booster_audio.stop()
        self._refresh_booster()

    def _booster_auto_allowed(self):
        return (getattr(self, 'booster_mode_enabled', False)
                and not getattr(self, 'offline_mode_enabled', False)
                and not getattr(self, 'pc_map_audio_muted', False))

    def _booster_detection_update(self, present, valid=True, generation=None):
        clock = getattr(self, '_booster_clock', None)
        if not valid or clock is None or not self._booster_auto_allowed():
            self._booster_detection_invalidated()
            return
        if generation != getattr(self, '_booster_detection_generation', None):
            self._booster_detection_invalidated()
        self._booster_detection_generation = generation
        if clock.running:
            # A rune seen during a run must not queue another run behind it.
            self._booster_seen_rune = False
            self._booster_pending_at = None
            self._booster_last_valid_at = None
            return
        now = clock.clock()
        self._booster_last_valid_at = now
        if present:
            self._booster_seen_rune = True
            self._booster_pending_at = None
        elif getattr(self, '_booster_seen_rune', False):
            self._booster_seen_rune = False
            self._booster_pending_at = now + 1.0

    def _booster_start_automatic_if_due(self, now):
        pending = getattr(self, '_booster_pending_at', None)
        if pending is None:
            return
        if not self._booster_auto_allowed() or self._booster_clock.running:
            self._booster_detection_invalidated()
            return
        if now < pending:
            return
        last_valid = getattr(self, '_booster_last_valid_at', None)
        if last_valid is None or not 0 <= now - last_valid <= 2.5:
            self._booster_detection_invalidated()
            return
        uses = getattr(self, 'booster_use_count', 3)
        if isinstance(uses, bool) or not isinstance(uses, int) or uses <= 0:
            uses = 3
        self._booster_detection_invalidated()
        self._booster_clock.start()
        self._booster_auto_session = {'started_at': self._booster_clock.started_at,
                                      'uses': uses, 'alerts': 1}
        self._booster_audio.play_once()
        self._refresh_booster()

    def _refresh_booster(self, redraw=True):
        self.booster_running = self._booster_clock.running
        self.booster_remaining = self._booster_clock.remaining
        if redraw:
            self._draw_bottom_dock()
            self._draw_widget_mode(force=True)

    def _set_booster_mode_enabled(self, value):
        self.booster_mode_enabled = bool(value)
        if not self.booster_mode_enabled:
            self._booster_detection_invalidated()
            self._booster_auto_session = None
            self._booster_clock.stop()
            self._booster_audio.stop()
        variable = getattr(self, 'booster_mode_var', None)
        if variable is not None:
            variable.set(self.booster_mode_enabled)
        self._refresh_booster()
        self._save_settings()

    def _toggle_booster(self):
        if not self.booster_mode_enabled:
            return
        self._booster_detection_invalidated()
        self._booster_auto_session = None
        if self._booster_clock.running:
            self._booster_clock.stop()
            self._booster_audio.stop()
        else:
            self._booster_clock.start()
        self._refresh_booster()

    def _booster_tick(self):
        self._booster_after_id = None
        if getattr(self, 'shutting_down', False):
            return
        old = (self.booster_running, self.booster_remaining)
        now = self._booster_clock.clock()
        self._booster_start_automatic_if_due(now)
        session = getattr(self, '_booster_auto_session', None)
        if session and now - session['started_at'] >= session['uses'] * self._booster_clock.interval:
            self._booster_clock.stop()
            self._booster_audio.stop()
            self._booster_auto_session = None
            self._booster_detection_invalidated()
            self._refresh_booster()
        elif self.booster_mode_enabled and self._booster_clock.poll():
            # Missed alert windows never become extra uses in a later cycle.
            cycle = self._booster_clock._alerted_cycle
            if session is None or (cycle < session['uses'] - 1 and session['alerts'] < session['uses']):
                self._booster_audio.play_three()
                if session is not None:
                    session['alerts'] += 1
        self._refresh_booster(redraw=False)
        if old != (self.booster_running, self.booster_remaining):
            self._update_widget_timer_display_lightweight()
        self._booster_after_id = self.root.after(100, self._booster_tick)

    def _quit_app(self):
        self._booster_detection_invalidated()
        self._booster_auto_session = None
        self._booster_clock.stop()
        self._booster_audio.stop()
        if self._booster_after_id is not None:
            try:
                self.root.after_cancel(self._booster_after_id)
            except Exception:
                pass
            self._booster_after_id = None
        return super()._quit_app()
