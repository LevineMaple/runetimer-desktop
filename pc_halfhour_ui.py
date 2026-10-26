"""Main-screen optional 30-minute card; GPL-3.0-or-later."""
import math
import time
import tkinter as tk
from tkinter import font as tkfont

import rune_base as base


class HalfHourUIMixin:
    def _bind_halfhour_control(self, tag, action):
        canvas = self.countdown_canvas

        def press(event):
            self._halfhour_ui_press = (tag, event.x_root, event.y_root)
            # Do not leave a primary-card press pending behind the plus.
            self.countdown_press_root = None
            return "break"

        def release(event):
            start = getattr(self, "_halfhour_ui_press", None)
            self._halfhour_ui_press = None
            if (start is not None and start[0] == tag
                    and abs(event.x_root - start[1]) <= 8
                    and abs(event.y_root - start[2]) <= 8):
                if tag in ("halfhour_add", "halfhour_remove"):
                    if getattr(self, "_halfhour_control_after_id", None) is None:
                        def apply_delayed():
                            self._halfhour_control_after_id = None
                            if not getattr(self, "shutting_down", False):
                                action()
                        self._halfhour_control_after_id = self.root.after(300, apply_delayed)
                else:
                    action()
            return "break"

        canvas.tag_bind(tag, "<ButtonPress-1>", press)
        canvas.tag_bind(tag, "<ButtonRelease-1>", release)
        canvas.tag_bind(tag, "<Enter>", lambda _e: canvas.configure(cursor="hand2"))
        canvas.tag_bind(tag, "<Leave>", lambda _e: canvas.configure(cursor=""))

    def _draw_countdown_display(self, _event=None):
        if not hasattr(self, "countdown_canvas"):
            return
        canvas = self.countdown_canvas
        if not getattr(self, "halfhour_enabled", False):
            self._halfhour_ui_items = []
            self.halfhour_remove_region = None
            super()._draw_countdown_display(_event)
            canvas.itemconfigure(self.countdown_number_item, fill="#8a9094" if self.warning_timer_paused else "#ffffff")
            x, y, size = self.countdown_card_metrics
            radius = max(8, int(size * .045))
            # Keep the control wholly above the card's start/pause hit area.
            gap = max(6, int(size * .025))
            cx, cy = x + size - radius * 1.8, y - gap - radius
            self.halfhour_add_region = (cx - radius, cy - radius, cx + radius, cy + radius)
            self.halfhour_card_regions = [(x, y, x + size, y + size)]
            tags = ("countdown", "halfhour_add")
            arm = max(6, int(radius * .75))
            canvas.create_line(cx - arm, cy, cx + arm, cy, fill="#ffffff", width=3, tags=tags)
            canvas.create_line(cx, cy - arm, cx, cy + arm, fill="#ffffff", width=3, tags=tags)
            self._bind_halfhour_control("halfhour_add", self._add_halfhour)
            return

        canvas.delete("countdown")
        self.halfhour_add_region = None
        self.halfhour_card_regions = []
        canvas_width = max(1, int(canvas.winfo_width()))
        if canvas_width <= 1:
            canvas_width = max(canvas.winfo_reqwidth(), base.APP_WIDTH - 26)
        scale = self._monitor_scale()
        area_size = max(125, int(500 * scale))
        area_x = (canvas_width - area_size) / 2
        area_y = int(124 * scale)
        self.countdown_card_metrics = (area_x, area_y, area_size)
        gap = max(8, int(area_size * .04))
        side = int((area_size - gap) / 2)
        card_y = area_y + (area_size - side) / 2
        self._halfhour_ui_items = []
        self._halfhour_panel_photos = []
        self._halfhour_progress_photos = {}
        self._halfhour_progress_pixels = {}
        self.countdown_number_item = None
        self.countdown_progress_item = None
        for index in range(2):
            x = area_x + index * (side + gap)
            self.halfhour_card_regions.append((x, card_y, x + side, card_y + side))
            tag = "halfhour_card_" + str(index)
            tags = ("countdown", tag)
            panel = self._make_countdown_panel_image(side, side, max(12, int(side * .17)))
            self._halfhour_panel_photos.append(panel)
            canvas.create_image(x, card_y, image=panel, anchor="nw", tags=tags)
            number_size = max(14, int(side * .20))
            if index == 1:
                measured_font = tkfont.Font(root=canvas, font=self._timer_number_font(number_size))
                # Tk font sizes are points, while the card geometry is pixels.
                # Measure using the actual DPI/font instead of estimating width.
                while number_size > 1 and max(measured_font.measure("30:00"),
                                              measured_font.measure("88:88")) > side * .78:
                    number_size -= 1
                    measured_font.configure(size=number_size)
            number = canvas.create_text(x + side / 2, card_y + side * .49,
                                        text="", fill=self.colors["text"],
                                        font=self._timer_number_font(number_size), tags=tags)
            bar_x, bar_y = x + side * .17, card_y + side * .80
            bar_width, bar_height = side * .66, max(3, int(side * .025))
            canvas.create_rectangle(bar_x, bar_y, bar_x + bar_width, bar_y + bar_height,
                                    fill="#202626", outline="", tags=tags)
            progress = canvas.create_image(bar_x, bar_y, anchor="nw", tags=tags)
            self._halfhour_ui_items.append((number, progress, bar_x, bar_y, bar_width, bar_height))
            action = self._toggle_warning_countdown_pause if index == 0 else self._toggle_halfhour
            self._bind_halfhour_control(tag, action)
            if index == 1:
                radius = max(7, int(side * .065))
                cx, cy = x + side - radius * 1.8, card_y
                remove_tags = ("countdown", "halfhour_remove")
                # A text item has a clickable bounding box without a button frame.
                remove_item = canvas.create_text(cx, cy, text="−", fill="#ffffff",
                                                font=("Segoe UI", max(12, radius * 2), "bold"), tags=remove_tags)
                # Measure the actual font box so higher Windows DPI cannot put
                # the minus hit area back inside the card.
                bounds = canvas.bbox(remove_item)
                control_gap = max(6, int(side * .04))
                canvas.move(remove_item, 0, card_y - control_gap - bounds[3])
                self.halfhour_remove_region = canvas.bbox(remove_item)
                self._bind_halfhour_control("halfhour_remove", self._remove_halfhour)
        self._refresh_halfhour_card_values(time.monotonic())
        self._draw_rune_status_bar()

    def _refresh_halfhour_card_values(self, now):
        canvas = self.countdown_canvas
        primary = max(0, math.ceil(self._warning_remaining_float(now)))
        self.countdown_remaining = primary
        clock = getattr(self, "_halfhour_clock", None)
        secondary = max(0, math.ceil(clock.remaining if clock is not None else 1800))
        minutes, seconds = divmod(secondary, 60)
        states = (
            (str(primary), self._warning_countdown_progress(now),
             getattr(self, "warning_timer_paused", False)),
            (f"{minutes:02d}:{seconds:02d}", min(1., secondary / 1800.),
             not bool(clock and clock.running)),
        )
        for items, (label, ratio, paused) in zip(self._halfhour_ui_items, states):
            number, progress, x, y, width, height = items
            canvas.itemconfigure(number, text=label, fill="#8a9094" if paused else "#ffffff")
            ratio = max(0., min(1., ratio))
            filled = round(width * ratio)
            if self._halfhour_progress_pixels.get(progress) != filled:
                photo = self._make_countdown_progress_image(max(1, int(width)), max(1, int(height)), ratio)
                self._halfhour_progress_photos[progress] = photo
                self._halfhour_progress_pixels[progress] = filled
                canvas.itemconfigure(progress, image=photo)
        self.last_countdown_progress_update_at = now

    def _update_countdown_display_lightweight(self, now=None):
        if not getattr(self, "halfhour_enabled", False):
            result = super()._update_countdown_display_lightweight(now)
            canvas = getattr(self, "countdown_canvas", None)
            number = getattr(self, "countdown_number_item", None)
            if canvas is not None and number is not None:
                canvas.itemconfigure(number, fill="#8a9094" if self.warning_timer_paused else "#ffffff")
            return result
        if not self._monitor_ui_visible() or not hasattr(self, "countdown_canvas"):
            return
        if len(getattr(self, "_halfhour_ui_items", ())) != 2:
            self._draw_countdown_display()
            return
        try:
            self._refresh_halfhour_card_values(time.monotonic() if now is None else now)
        except tk.TclError:
            self._draw_countdown_display()
