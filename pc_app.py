# SPDX-License-Identifier: GPL-3.0-or-later
# Windows capture and diagnostics.
import json
import os
import sys
import threading
import time
from pathlib import Path
import pc_capture as cap
from pc_map_audio import MapAudioMatcher
from pc_booster import BoosterMixin
from pc_halfhour import HalfHourMixin

cap.enable_dpi()
DATA = Path(os.environ.get('RUNE_TIMER_PC_DATA', str(Path.home()/'AppData/Roaming/RuneTimerThisPC')))

def seed_settings():
    DATA.mkdir(parents=True, exist_ok=True)
    legacy=Path.home()/'AppData/Roaming/MapleTimerAutoDetect'
    if not (DATA/'ui-profile.json').exists():
        profile='high'
        try:
            candidate=json.loads((legacy/'ui-profile.json').read_text(encoding='utf-8'))
            if candidate in ('low','high'): profile=candidate
        except (OSError,ValueError): pass
        (DATA/'ui-profile.json').write_text(json.dumps(profile),encoding='utf-8')
    for name in ('settings.json','settings-low.json'):
        target=DATA/name
        if target.exists(): continue
        try:
            data=json.loads((legacy/name).read_text(encoding='utf-8'))
        except (OSError,ValueError):
            try: data=json.loads((legacy/'settings.json').read_text(encoding='utf-8'))
            except (OSError,ValueError): data={}
        # Never import the old window anchor (it followed an auxiliary window).
        data.update(region=None,rune_region=None,rune_window_anchor=None,
                    offline_mode_enabled=False,monitor_enabled=True,rune_sound_enabled=True,
                    booster_mode_enabled=False,
                    warning_volume=100,rune_volume=100,first_launch_centered_done=True)
        target.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')

seed_settings()
import rune_base as base
from pc_halfhour_ui import HalfHourUIMixin
from PIL import Image,ImageTk,ImageDraw
import tkinter as tk
from tkinter import messagebox


class ScreenSelector(tk.Toplevel):
    """Frozen, physical-pixel virtual desktop selection, including negative origins."""
    def __init__(self, parent, callback, closed):
        bounds=cap.desktop_bounds()
        screenshot=cap.grab(bounds)
        super().__init__(parent)
        self.bounds=bounds; self.callback=callback; self.closed_callback=closed; self.done=False
        self.overrideredirect(True); self.attributes('-topmost',True)
        x,y,r,b=bounds
        self.geometry(f'{r-x}x{b-y}{x:+d}{y:+d}')
        self.photo=ImageTk.PhotoImage(screenshot)
        self.canvas=tk.Canvas(self,highlightthickness=0,cursor='crosshair')
        self.canvas.pack(fill='both',expand=True)
        self.canvas.create_image(0,0,image=self.photo,anchor='nw')
        self.canvas.create_rectangle(20,18,780,102,fill='#101819',outline='#4af1ae')
        self.canvas.create_text(36,59,anchor='w',text='미니맵 전체 + 흰 테두리 바깥 여백까지 넓게 드래그\n지도 제목과 테두리 네 면이 잘리지 않게 지정 · Esc 취소',fill='white',font=('맑은 고딕',15,'bold'))
        self.box=None; self.start=None
        self.canvas.bind('<ButtonPress-1>',self.begin)
        self.canvas.bind('<B1-Motion>',self.move)
        self.canvas.bind('<ButtonRelease-1>',self.finish)
        self.bind('<Escape>',lambda e:self.close())
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.lift(); self.focus_force(); self.grab_set()

    def begin(self,e):
        self.start=(e.x,e.y)
        if self.box: self.canvas.delete(self.box)
        self.box=self.canvas.create_rectangle(e.x,e.y,e.x,e.y,outline='#4af1ae',width=3)
    def move(self,e):
        if self.start: self.canvas.coords(self.box,*self.start,e.x,e.y)
    def finish(self,e):
        if not self.start: return
        x1,x2=sorted((self.start[0],e.x)); y1,y2=sorted((self.start[1],e.y))
        if x2-x1<40 or y2-y1<30: return
        x,y,_,_=self.bounds
        region=(x+x1,y+y1,x+x2,y+y2)
        self.close()
        self.callback(region)
    def close(self):
        if self.done:return
        self.done=True
        self.grab_release(); self.destroy(); self.closed_callback()


class PcTimerApp(HalfHourUIMixin, HalfHourMixin, BoosterMixin, base.MapleTimerApp):
    def _ensure_widget_window(self):
        if not super()._ensure_widget_window():
            return False
        widget = self.widget
        widget.title('RuneTimer OBS Widget')
        if not getattr(widget, '_obs_map_bound', False):
            widget.bind('<Map>', self._expose_obs_widget, add='+')
            widget._obs_map_bound = True
        return True

    def _expose_obs_widget(self, event):
        if event.widget is not self.widget:
            return
        try:
            cap.expose_obs_widget(self.widget)
        except (OSError, tk.TclError) as exc:
            base.log_error('obs_widget_window', exc)

    def __init__(self):
        self._init_booster(base.resource_path, base.log_error)
        self._init_halfhour(base.resource_path, base.log_error)
        self.capture_generation=0
        self.pc_status='미니맵 찾기 대기'
        self.pc_last_result={}
        self.pc_hit_count=0
        self.pc_miss_count=0
        self.pc_diag=None
        self.pc_selecting=False
        self.pc_last_search=0
        self.pc_last_log_key=None
        self.pc_last_log_time=0
        self.pc_selected_window=None
        self.pc_anchor_error=None
        self.pc_ready=False
        self.pc_map_audio_muted=False
        self.pc_map_matcher=MapAudioMatcher()
        super().__init__()
        self.monitor_interval_ms=900
        self.rune_alert_interval=3.0
        self.pc_ready=True
        self._booster_tick()
        self._halfhour_tick()
        base.log_error('pc_start',RuntimeError(f'v1.1.3-pc1 desktop={cap.desktop_bounds()} windows={cap.maple_windows()}'))

    def _sound_enabled_for_key(self, key):
        if (key == 'rune' and not getattr(self, 'offline_mode_enabled', False)
                and getattr(self, 'pc_map_audio_muted', False)):
            return False
        return super()._sound_enabled_for_key(key)

    def _set_map_audio_muted(self, muted):
        muted = bool(muted)
        changed = muted != getattr(self, 'pc_map_audio_muted', False)
        self.pc_map_audio_muted = muted
        if changed:
            self._booster_detection_invalidated()
            self.pc_hit_count = self.pc_miss_count = 0
            self.rune_alert_latched = False
            self.last_rune_alert_at = 0.0
            self._clear_queued_sound('rune')
            self._log_status('map_audio', '사계가 머무는 누각: 룬 알림음 자동 끔' if muted
                             else '맵별 음소거 해제: 기존 룬 알림 설정 사용')

    def _build_settings_page(self):
        page=super()._build_settings_page()
        panel=self.settings_diagnostics_parent
        self.settings_diagnostics_button=tk.Button(panel,text='캡처 확인 / 소리 테스트',command=self._open_diagnostics,
                  bg='#224038',fg='white',relief='flat',font=self._settings_font(8 if base.LOW_RES else 9),padx=2,pady=5)
        self.settings_diagnostics_button.pack(fill='x',pady=(4,2))
        return page

    def _find_maplestory_windows(self):
        return cap.maple_windows()

    def _choose_game(self):
        windows=cap.maple_windows()
        if not windows:return None
        # cap sorts by visible area. Never select a same-PID auxiliary window
        # simply because EnumWindows happened to return it first.
        return windows[0]

    def _bind_rune_region_to_maplestory_window(self):
        window=self._choose_game()
        if not window or not self.rune_region:
            self.rune_window_anchor=None
            return False
        x,y,r,b=window['rect']; x1,y1,x2,y2=self.rune_region
        if not (x<=x1<x2<=r and y<=y1<y2<=b):
            self.rune_window_anchor=None
            return False
        self.rune_window_anchor=dict(pid=window['pid'],process_name=window['process_name'],
            window_rect=list(window['rect']),relative_region=[x1-x,y1-y,x2-x,y2-y])
        self.pc_selected_window=window
        return True

    def _sync_rune_region_to_maplestory_window(self):
        self.pc_anchor_error=None
        if not self.rune_region:return False
        window=self._choose_game()
        if not window:
            self.pc_anchor_error='메이플 창을 화면에 표시해 주세요'
            return False
        if not self.rune_window_anchor:
            if not self._bind_rune_region_to_maplestory_window():
                self.pc_anchor_error='게임 창 안의 미니맵을 다시 지정해 주세요'
                return False
        try:
            region=cap.translate_region(self.rune_window_anchor['relative_region'],window['rect'])
        except ValueError as exc:
            self.pc_anchor_error='게임 창 크기가 바뀌었습니다. 미니맵 다시 찾기를 누르세요'
            self._log_status('coordinate_error',str(exc))
            return False
        if region!=self.rune_region:
            self._booster_detection_invalidated()
            self.capture_generation+=1
            self.rune_region=region
            self.last_capture=None
        self.pc_selected_window=window
        return True

    def _set_rune_region(self,region):
        try: region=cap.validate_region(region)
        except ValueError as exc:
            messagebox.showerror('캡처 영역',str(exc),parent=self.root)
            return
        window=self._choose_game()
        if not window:
            messagebox.showinfo('미니맵 지정','메이플 게임 창을 먼저 표시해 주세요.',parent=self.root)
            return
        x,y,r,b=window['rect']
        if not (x<=region[0]<region[2]<=r and y<=region[1]<region[3]<=b):
            messagebox.showinfo('미니맵 지정','실제 메이플 게임 창 안의 미니맵을 선택해 주세요.',parent=self.root)
            return
        self._booster_detection_invalidated()
        self.capture_generation+=1
        self.pc_hit_count=self.pc_miss_count=0
        super()._set_rune_region(region)
        self.pc_status='미니맵 검사 중'
        self._log_status('region_selected',f'region={region}, target={window}')

    def _grab_frame(self,region):
        if self.offline_mode_enabled:return None
        with self.capture_lock:
            return cap.grab(region)

    def _select_rune_region(self):
        if self.pc_selecting:return
        self._booster_detection_invalidated()
        self.pc_selecting=True; self.capture_generation+=1
        self.root.withdraw()
        for window in (getattr(self,'widget',None),self.pc_diag):
            if window:
                try: window.withdraw()
                except tk.TclError:pass
        self.root.after(180,self._show_selector)

    def _show_selector(self):
        try: ScreenSelector(self.root,self._set_rune_region,self._selector_closed)
        except Exception as exc:
            self._selector_closed(); self.pc_status=f'영역 선택 실패: {exc}'
            base.log_error('selector',exc)

    def _selector_closed(self):
        self.pc_selecting=False
        self._show_main_window(force_focus=True)
        if self.pc_diag:
            try:self.pc_diag.deiconify()
            except tk.TclError:pass

    def _search_minimap(self):
        if self.monitor_worker_running or self.pc_selecting or self.offline_mode_enabled:return
        window=self._choose_game()
        if not window:
            self.pc_status='메이플 게임 창을 화면에 표시해 주세요'; return
        self.pc_selected_window=window
        x,y,r,b=window['rect']
        region=(x,y,min(x+540,r),min(y+400,b))
        self.monitor_worker_running=True
        generation=self.capture_generation
        def worker():
            result=dict(pc_search=True,generation=generation,region=region,window=window)
            try:
                frame=self._grab_frame(region)
                found=self._find_minimap_region(frame)
                result.update(found=tuple((x+found[0],y+found[1],x+found[2],y+found[3])) if found else None,captured=frame)
            except Exception as exc:result.update(error=str(exc))
            self.worker_results.put(('monitor',result))
        threading.Thread(target=worker,daemon=True).start()

    def _monitor_tick_body(self):
        if not self.pc_ready:return
        now=time.monotonic()
        if self.monitor_enabled and not self.warning_timer_paused and now-self.last_stall_alert_at>=self.warning_loop_seconds:
            self._play('warning'); self.last_stall_alert_at=now
        if self.offline_mode_enabled:
            self._booster_detection_invalidated()
            self._set_map_audio_muted(False)
            self.pc_status='수동 모드 · 자동 감지 꺼짐'
            self._offline_rune_tick(now)
            self._set_rune_capture_active(False)
        elif self.pc_selecting:
            self.pc_status='영역 선택 중'
        elif not self.rune_region:
            self.pc_status='미니맵을 찾는 중 · 실패하면 직접 지정해 주세요'
            if now-self.pc_last_search>=5:
                self.pc_last_search=now; self._search_minimap()
        else:
            self._sync_rune_region_to_maplestory_window()
            if self.pc_anchor_error:
                self._reset_detection(self.pc_anchor_error)
            elif not self.monitor_worker_running:
                self._start_monitor_worker()
        self._render_monitor_status()
        self._refresh_diagnostics()

    def _start_monitor_worker(self):
        if self.monitor_worker_running or not self.rune_region:return
        self.monitor_worker_running=True
        region=tuple(self.rune_region); generation=self.capture_generation
        game = self.pc_selected_window
        header = None
        if game:
            gx, gy, gr, gb = game['rect']
            header = (gx, gy, min(gx + 540, gr), min(gy + 180, gb))
        masks=[]
        if self.root.winfo_viewable():
            masks.append(self._get_app_rect())
        for window in (self.pc_diag,getattr(self,'widget',None)):
            if window:
                try:
                    if window.winfo_viewable():
                        x,y=window.winfo_rootx(),window.winfo_rooty()
                        masks.append((x,y,x+window.winfo_width(),y+window.winfo_height()))
                except tk.TclError:pass
        def worker():
            result=dict(generation=generation,region=region,error=False,minimap_ok=False,
                        score=0.0,map_audio_muted=False)
            try:
                if any(rect and min(rect[2],region[2])>max(rect[0],region[0]) and min(rect[3],region[3])>max(rect[1],region[1]) for rect in masks):
                    raise RuntimeError('타이머/미리보기 창이 미니맵을 가리고 있습니다. 창을 옮겨 주세요.')
                # Read the map label and minimap in ONE frame so a map change
                # cannot combine the previous title with a new minimap.
                capture_region = region
                if header:
                    capture_region = (min(region[0],header[0]), min(region[1],header[1]),
                                      max(region[2],header[2]), max(region[3],header[3]))
                combined = self._grab_frame(capture_region)
                def crop(rect):
                    return combined.crop((rect[0]-capture_region[0], rect[1]-capture_region[1],
                                          rect[2]-capture_region[0], rect[3]-capture_region[1]))
                frame = crop(region)
                if header:
                    try:
                        title_frame = crop(header)
                        # Hide only the actually covered pixels, not the whole
                        # header when a timer window sits away from its text.
                        draw = ImageDraw.Draw(title_frame)
                        for rect in masks:
                            if not rect:
                                continue
                            left, top = max(rect[0],header[0]), max(rect[1],header[1])
                            right, bottom = min(rect[2],header[2]), min(rect[3],header[3])
                            if right > left and bottom > top:
                                draw.rectangle((left-header[0],top-header[1],
                                                right-header[0]-1,bottom-header[1]-1),fill='black')
                        result['map_audio_muted'] = self.pc_map_matcher.match(title_frame)
                        result['map_audio_match'] = dict(self.pc_map_matcher.last_result)
                    except Exception as exc:
                        # A title-reading problem must not suppress other maps.
                        result['map_audio_error'] = str(exc)
                minimap=self._crop_minimap_view(frame)
                result.update(captured=frame,minimap=minimap,minimap_ok=minimap is not None)
                if minimap is not None:result['score']=self._score_rune(minimap,already_cropped=True)
            except Exception as exc:
                result['error']=str(exc)
            self.worker_results.put(('monitor',result))
        threading.Thread(target=worker,daemon=True).start()

    def _reset_detection(self,status):
        self._booster_detection_invalidated()
        self._set_map_audio_muted(False)
        self.pc_status=status
        self.pc_hit_count=self.pc_miss_count=0
        self.rune_alert_latched=False; self.rune_score=0.0; self.last_rune_alert_at=0.0
        self._clear_queued_sound('rune'); self._set_rune_visual(False)
        self._set_rune_capture_active(False)

    def _apply_monitor_result(self,result):
        if result.get('generation')!=self.capture_generation or self.pc_selecting:return
        if self.offline_mode_enabled:
            self._booster_detection_invalidated()
            return
        if result.get('pc_search'):
            if result.get('found'):
                self._set_rune_region(result['found'])
            else:
                self.pc_last_result=result
                self.pc_status='미니맵을 찾지 못했습니다. 게임을 표시하고 직접 지정해 주세요'
                if result.get('error'):self._log_status('search_error',result['error'])
            self._refresh_diagnostics(); return
        # A result for a previous window location must never trigger an alert.
        self._sync_rune_region_to_maplestory_window()
        if self.pc_anchor_error:
            self._booster_detection_invalidated()
            return
        if result.get('generation')!=self.capture_generation:return
        self.pc_last_result=result
        self.last_capture=result.get('captured')
        if result.get('error'):
            self._reset_detection('캡처 실패: '+str(result['error']))
            self._log_status('capture_error',f"region={result.get('region')} desktop={cap.desktop_bounds()} error={result['error']}")
        elif not result.get('minimap_ok'):
            self._reset_detection('미니맵 테두리를 찾지 못했습니다 · 미리보기 확인')
            self._log_status('minimap_not_found',f"region={result.get('region')}")
        else:
            self._set_map_audio_muted(result.get('map_audio_muted', False))
            self._set_rune_capture_active(True)
            self.rune_score=float(result['score'])
            if self.rune_score>=self.rune_threshold:
                self.pc_hit_count+=1; self.pc_miss_count=0
            else:
                self.pc_miss_count+=1; self.pc_hit_count=0
            was_rune_latched = self.rune_alert_latched
            if self.pc_hit_count>=2:
                self.rune_alert_latched=True
            elif self.pc_miss_count>=2:
                self.rune_alert_latched=False; self.last_rune_alert_at=0.0
                self._clear_queued_sound('rune')
            if self.rune_alert_latched and not was_rune_latched and not self.pc_map_audio_muted:
                self._booster_new_rune_detected()
            self._booster_detection_update(self.rune_alert_latched,
                                            valid=not self.pc_map_audio_muted,
                                            generation=self.capture_generation)
            if self.pc_map_audio_muted:
                self.pc_status='사계가 머무는 누각 · 룬 알림음 자동 끔'
                self._set_auto_detect_status(self.pc_status)
            elif self.rune_alert_latched:
                self.pc_status='룬 감지!'
                self._set_auto_detect_status('룬이 등장했습니다')
                now=time.monotonic()
                if now-self.last_rune_alert_at>=self.rune_alert_interval:
                    self._play('rune'); self.last_rune_alert_at=now
            else:
                self.pc_status='룬 후보 확인 중' if self.pc_hit_count else '정상 감시 중 · 룬 대기'
                self._set_auto_detect_status('기존 미니맵 영역 사용 중')
            self._log_status('detection',f'active={self.rune_alert_latched} score={self.rune_score:.1f} region={self.rune_region}',key=str(self.rune_alert_latched))
        self._refresh_diagnostics()

    def _log_status(self,tag,detail,key=None):
        current=(tag,key if key is not None else detail)
        now=time.monotonic()
        if current!=self.pc_last_log_key or now-self.pc_last_log_time>=60:
            base.log_error(tag,RuntimeError(detail))
            self.pc_last_log_key=current; self.pc_last_log_time=now

    def _open_diagnostics(self):
        if self.pc_diag and self.pc_diag.winfo_exists():
            self.pc_diag.deiconify(); self.pc_diag.lift();return
        win=tk.Toplevel(self.root);self.pc_diag=win
        win.title('RuneTimer · 이 PC용 · 캡처 확인')
        win.configure(bg='#14191d');win.attributes('-topmost',True)
        left,top,right,bottom=cap.desktop_bounds()
        positions=[(max(left,right-660),top+40),(left+20,top+40),
                   (max(left,right-660),max(top,bottom-540))]
        blocked=[self._get_app_rect(),self.rune_region]
        def free(pos):
            x,y=pos
            return not any(r and min(x+640,r[2])>max(x,r[0]) and min(y+500,r[3])>max(y,r[1]) for r in blocked)
        px,py=next((p for p in positions if free(p)),positions[0])
        win.geometry(f'640x500{px:+d}{py:+d}');win.minsize(560,440)
        win.protocol('WM_DELETE_WINDOW',lambda:(win.destroy(),setattr(self,'pc_diag',None)))
        tk.Label(win,text='이 PC용 수정판  •  미니맵 감시',bg='#14191d',fg='#4af1ae',font=('맑은 고딕',15,'bold')).pack(anchor='w',padx=18,pady=(16,8))
        self.pc_status_var=tk.StringVar(value=self.pc_status)
        tk.Label(win,textvariable=self.pc_status_var,bg='#14191d',fg='white',font=('맑은 고딕',11),wraplength=600,justify='left').pack(anchor='w',padx=18)
        self.pc_preview=tk.Label(win,bg='#080b0e',fg='#99a7ae',text='캡처 대기 중')
        self.pc_preview.pack(fill='both',expand=True,padx=18,pady=12)
        self.pc_info_var=tk.StringVar()
        tk.Label(win,textvariable=self.pc_info_var,bg='#14191d',fg='#b3bfc5',font=('맑은 고딕',9),justify='left').pack(anchor='w',padx=18)
        row=tk.Frame(win,bg='#14191d');row.pack(fill='x',padx=18,pady=14)
        for label,command in [('다시 찾기',self._research),('직접 지정',self._select_rune_region),('룬 소리 테스트',self._test_rune_sound),('진단 저장',self._save_diagnostic)]:
            tk.Button(row,text=label,command=command,bg='#253d36',fg='white',relief='flat',padx=9,pady=8).pack(side='left',padx=(0,6))
        self._refresh_diagnostics()

    def _research(self):
        self.capture_generation+=1;self.rune_region=None;self.rune_window_anchor=None
        self.pc_hit_count=self.pc_miss_count=0
        self._reset_detection('미니맵 다시 찾기')
        self.pc_last_search=0
        self._save_settings()
        self._search_minimap()

    def _refresh_diagnostics(self):
        if not self.pc_diag or not self.pc_diag.winfo_exists():return
        self.pc_status_var.set(self.pc_status)
        result=self.pc_last_result
        frame=result.get('captured')
        if frame is not None:
            preview=frame.copy()
            maxw=max(100,self.pc_preview.winfo_width()-10);maxh=max(80,self.pc_preview.winfo_height()-10)
            scale=min(maxw/frame.width,maxh/frame.height,3)
            preview=preview.resize((max(1,int(frame.width*scale)),max(1,int(frame.height*scale))),Image.Resampling.NEAREST)
            self.pc_photo=ImageTk.PhotoImage(preview)
            self.pc_preview.configure(image=self.pc_photo,text='')
        else:self.pc_preview.configure(image='',text='캡처 대기 중')
        region=result.get('region') or self.rune_region
        hwnd=(self.pc_selected_window or {}).get('hwnd','-')
        self.pc_info_var.set(f'룬 점수 {self.rune_score:.1f} / 기준 {self.rune_threshold:.0f}   ·   연속 확인 {self.pc_hit_count}/2\n캡처 영역 {region}   ·   게임 창 {hwnd}\n룬 알림 {"켜짐" if self.rune_sound_enabled else "꺼짐"} / 볼륨 {self.rune_volume}   ·   설정에서 캡처 확인')

    def _test_rune_sound(self):
        volume=max(30,self.rune_volume)
        source=self._sound_source_path('rune')
        self.sound_queue.put(('test_rune',self._volume_adjusted_sound_path('rune',volume,source),volume))
        self.pc_status=f'룬 소리 1회 테스트 · 볼륨 {volume}'
        self._refresh_diagnostics()

    def _save_diagnostic(self):
        folder=base.APP_DIR/'diagnostics'/time.strftime('%Y%m%d-%H%M%S')
        folder.mkdir(parents=True,exist_ok=True)
        result=self.pc_last_result
        for key in ('captured','minimap'):
            frame=result.get(key)
            if frame is not None:frame.save(folder/(key+'.png'))
        meta={k:v for k,v in result.items() if k not in ('captured','minimap')}
        meta.update(status=self.pc_status,desktop=cap.desktop_bounds(),windows=cap.maple_windows(),threshold=self.rune_threshold)
        (folder/'status.json').write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        messagebox.showinfo('진단 저장',f'이 PC에 저장했습니다.\n{folder}',parent=self.pc_diag)


if __name__=='__main__':
    app=PcTimerApp()
    if '--smoke-test' in sys.argv:
        def report_and_exit():
            result=app.pc_last_result
            report=dict(status=app.pc_status,region=app.rune_region,window=app.pc_selected_window,
                        minimap_ok=result.get('minimap_ok'),score=app.rune_score,error=result.get('error'),
                        map_audio_muted=app.pc_map_audio_muted,map_audio_match=result.get('map_audio_match'))
            (DATA/'smoke-result.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
            app._quit_app()
        app.root.after(14000,report_and_exit)
    app.run()
