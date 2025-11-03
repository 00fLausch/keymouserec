# KeyMouse Recorder Desktop App
# Records mouse and keyboard actions, saves to JSON, replays with adjustable speed and loop modes
# Desktop GUI using Tkinter

import threading
import time
import json
import os
import sys
from datetime import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
from tkinter import font as tkfont
import logging
from threading import Lock
from pynput import keyboard, mouse
import pyautogui

# Try to import win32gui for Windows-specific minimize
try:
    import win32gui
    import win32con
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

# Import settings from configuration
APP_NAME = "KeyMouse Recorder Desktop"
SETTINGS_FILE = "keymouserec_settings.json"
ICON_FILE = "icon.ico"

BG_COLOR = "#1a1a1a"
DEFAULT_ACCENT_COLOR = "#00BCD4"
TEXT_COLOR = "#ecf0f1"
WIDGET_BG = "#252525"
SYSTEM_COLOR = "#95a5a6"
LOG_BG = BG_COLOR
HEADER_BG = BG_COLOR
BUTTON_BG = "#303030"
BUTTON_HOVER_BG = "#3c3c3c"
BUTTON_TEXT_COLOR = "#ecf0f1"
BUTTON_TEXT_INACTIVE = "#aaaaaa"

# Import the RecordingManager class from main.py if needed
# For now, we'll copy and adapt it

class RecordingManager:
    def __init__(self):
        # Recording state
        self.is_recording = False
        self.events = []
        self.start_time = 0
        self.record_type = "all"  # all, mouse, keyboard

        # Stats for recording
        self.move_count = 0
        self.click_count = 0
        self.key_press_count = 0
        self.key_release_count = 0
        self.recording_start_timestamp = 0
        self.total_duration = 0

        # Playback state
        self.is_playing = False
        self.playback_thread = None
        self.abort_playback = False

        # Listeners
        self.keyboard_listener = None
        self.mouse_listener = None
        self.abort_listener = None

        # Speed and loop settings
        self.speed = 1.0
        self.loop_mode = False
        self.loop_count = 1

        # Threading
        self.events_lock = Lock()

        # Status
        self.status = "Ready"
        self.last_event_info = "None"

        # Start global keyboard listener
        self.start_global_listeners()

        # GUI callback (will be set by GUI)
        self.gui_callback = None

    def set_gui_callback(self, callback):
        self.gui_callback = callback

    def start_global_listeners(self):
        def on_press(key):
            if key == keyboard.Key.f1 and not self.is_recording:
                threading.Thread(target=self.start_recording).start()
            elif key == keyboard.Key.f2 and self.is_recording:
                threading.Thread(target=self.stop_recording).start()
            elif key == keyboard.Key.f3 and not self.is_playing:
                threading.Thread(target=self.start_playback).start()
            elif key == keyboard.Key.f4 and self.is_playing:
                self.abort_playback = True
                threading.Thread(target=self.stop_playback).start()

        self.abort_listener = keyboard.Listener(on_press=on_press)
        self.abort_listener.start()

    def emit_stats(self):
        # Emit current stats to GUI
        if self.gui_callback:
            with self.events_lock:
                total_events = len(self.events)
                mouse_total = self.move_count + self.click_count
                key_total = self.key_press_count + self.key_release_count

                duration = 0
                if self.is_recording:
                    duration = time.time() - self.recording_start_timestamp
                else:
                    duration = self.total_duration

                eps = total_events / duration if duration > 0 else 0

                hours, rem = divmod(int(duration), 3600)
                mins, secs = divmod(rem, 60)
                duration_str = f"{hours:02d}:{mins:02d}:{secs:02d}"

                progress = min(100, (mouse_total + key_total) // 10) if self.is_recording else 0

                self.gui_callback({
                    'status': self.status,
                    'total_events': total_events,
                    'mouse_events': mouse_total,
                    'key_events': key_total,
                    'duration': duration_str,
                    'eps': f"{eps:.1f}",
                    'progress': progress,
                    'last_event': self.last_event_info,
                    'is_recording': self.is_recording,
                    'is_playing': self.is_playing
                })

    def start_recording(self, record_type="all"):
        if self.is_recording:
            return
        self.record_type = record_type
        pyautogui.moveTo(0, 0)

        self.is_recording = True
        with self.events_lock:
            self.events = []
        self.start_time = time.time()
        # Reset stats
        self.move_count = 0
        self.click_count = 0
        self.key_press_count = 0
        self.key_release_count = 0
        self.recording_start_timestamp = self.start_time
        self.status = "Recording... Press F2 to stop"

        threading.Thread(target=self.run_listeners).start()

        # Periodic stats updates
        def update_loop():
            while self.is_recording:
                self.emit_stats()
                time.sleep(0.5)
            self.emit_stats()

        threading.Thread(target=update_loop).start()

    def run_listeners(self):
        last_move_time = 0

        def on_mouse_move(x, y):
            nonlocal last_move_time
            current_time = time.time() - self.start_time
            if self.is_recording and self.record_type in ["all", "mouse"] and current_time - last_move_time > 0.05:  # Record only every ~20fps
                with self.events_lock:
                    self.events.append({
                        'type': 'mouse_move',
                        'x': x,
                        'y': y,
                        'time': current_time
                    })
                    self.move_count += 1
                    self.last_event_info = f"Mouse move to ({x}, {y})"
                last_move_time = current_time

        def on_mouse_click(x, y, button, pressed):
            if self.is_recording and self.record_type in ["all", "mouse"]:
                with self.events_lock:
                    self.events.append({
                        'type': 'mouse_click',
                        'x': x,
                        'y': y,
                        'button': str(button),
                        'pressed': pressed,
                        'time': time.time() - self.start_time
                    })
                    self.click_count += 1
                    button_name = str(button).replace('Button.', '')
                    action = 'press' if pressed else 'release'
                    self.last_event_info = f"Mouse {button_name} {action}"

        def on_keyboard_press(key):
            if self.is_recording and self.record_type in ["all", "keyboard"]:
                with self.events_lock:
                    self.events.append({
                        'type': 'key_press',
                        'key': str(key),
                        'time': time.time() - self.start_time
                    })
                    self.key_press_count += 1
                    key_str = str(key).strip("'")
                    self.last_event_info = f"Key press: {key_str}"

        def on_keyboard_release(key):
            if self.is_recording and self.record_type in ["all", "keyboard"]:
                with self.events_lock:
                    self.events.append({
                        'type': 'key_release',
                        'key': str(key),
                        'time': time.time() - self.start_time
                    })
                    self.key_release_count += 1
                    key_str = str(key).strip("'")
                    self.last_event_info = f"Key release: {key_str}"

        # Start listeners
        self.mouse_listener = mouse.Listener(
            on_move=on_mouse_move,
            on_click=on_mouse_click
        )
        self.keyboard_listener = keyboard.Listener(
            on_press=on_keyboard_press,
            on_release=on_keyboard_release
        )

        self.mouse_listener.start()
        self.keyboard_listener.start()

        # Wait for stop
        self.mouse_listener.join()
        self.keyboard_listener.join()

    def stop_recording(self):
        if not self.is_recording:
            return
        self.total_duration = time.time() - self.recording_start_timestamp
        self.is_recording = False
        self.status = f"Recording stopped. Events: {len(self.events)}"

        # Stop listeners
        if self.mouse_listener:
            self.mouse_listener.stop()
        if self.keyboard_listener:
            self.keyboard_listener.stop()

        self.emit_stats()

    def start_playback(self):
        if not self.events or self.is_playing:
            return

        pyautogui.moveTo(0, 0)
        # Make a copy of events for thread safety
        with self.events_lock:
            self.events_copy = self.events.copy()

        self.is_playing = True
        self.abort_playback = False
        self.status = "Playing... Press F4 to abort"

        # Start playback thread
        threading.Thread(target=self.run_playback).start()

        def update_loop():
            while self.is_playing:
                self.emit_stats()
                time.sleep(0.1)

        threading.Thread(target=update_loop).start()

    def run_playback(self):
        # Disable failsafe to prevent interruptions from corner moves
        original_failsafe = pyautogui.FAILSAFE
        pyautogui.FAILSAFE = False

        speed = max(self.speed, 0.1)

        current_loop = 0
        start_time = time.time()

        while not self.abort_playback:
            for event in self.events_copy:
                if self.abort_playback:
                    break
                # Wait for the time
                event_time = start_time + (event['time'] / speed)
                wait_time = event_time - time.time()
                if wait_time > 0:
                    time.sleep(wait_time)

                try:
                    if event['type'] == 'mouse_move':
                        pyautogui.moveTo(event['x'], event['y'])
                    else:
                        if event['type'] == 'mouse_click':
                            button = event['button'].replace("Button.", "").lower()
                            if event['pressed']:
                                pyautogui.mouseDown(button=button)
                            else:
                                pyautogui.mouseUp(button=button)
                        elif event['type'] == 'key_press':
                            key_str = self.key_to_pya(event['key'])
                            if key_str:
                                pyautogui.keyDown(key_str)
                        elif event['type'] == 'key_release':
                            key_str = self.key_to_pya(event['key'])
                            if key_str:
                                pyautogui.keyUp(key_str)
                except pyautogui.FailSafeException:
                    self.status = "FailSafe triggered, aborting playback"
                    self.abort_playback = True
                    break
                except Exception as e:
                    # Skip invalid events
                    pass

            if self.loop_mode:
                # Infinite loop, continue
                pass
            else:
                current_loop += 1
                if current_loop >= self.loop_count:
                    break
            start_time = time.time()

        # Finished playback
        self.is_playing = False
        pyautogui.FAILSAFE = original_failsafe

        self.status = "Playback finished"
        self.emit_stats()

    def key_to_pya(self, key_str):
        # Convert pynput key string to pyautogui key
        if key_str.startswith("Key."):
            specials = {
                'Key.space': 'space',
                'Key.enter': 'return',
                'Key.tab': 'tab',
                'Key.backspace': 'backspace',
                'Key.esc': 'esc',
                'Key.shift': 'shift',
                'Key.shift_l': 'shiftleft',
                'Key.shift_r': 'shiftright',
                'Key.ctrl': 'ctrl',
                'Key.ctrl_l': 'ctrlleft',
                'Key.ctrl_r': 'ctrlright',
                'Key.alt': 'alt',
                'Key.alt_l': 'altleft',
                'Key.alt_r': 'altright',
                'Key.cmd': 'win',
                'Key.cmd_l': 'winleft',
                'Key.cmd_r': 'winright',
                'Key.f1': 'f1',
                'Key.f2': 'f2',
                'Key.f3': 'f3',
                'Key.f4': 'f4',
                'Key.f5': 'f5',
                'Key.f6': 'f6',
                'Key.f7': 'f7',
                'Key.f8': 'f8',
                'Key.f9': 'f9',
                'Key.f10': 'f10',
                'Key.f11': 'f11',
                'Key.f12': 'f12',
            }
            return specials.get(key_str)
        elif key_str.startswith('\'') and key_str.endswith('\''):
            return key_str[1:-1]
        elif key_str.startswith('"') and key_str.endswith('"'):
            return key_str[1:-1]
        else:
            return key_str

    def stop_playback(self):
        if not self.is_playing:
            return
        self.abort_playback = True
        self.is_playing = False
        self.status = "Playback aborted"
        self.emit_stats()

    def save_recording(self, filename="recording.json"):
        try:
            with self.events_lock:
                if not self.events:
                    return "No data to save"

                data = {
                    'events': self.events,
                    'timestamp': time.time(),
                    'description': "Recorded macro",
                    'stats': {
                        'total_events': len(self.events),
                        'mouse_events': self.move_count + self.click_count,
                        'key_events': self.key_press_count + self.key_release_count,
                        'duration': self.total_duration
                    }
                }

                with open(filename, 'w') as f:
                    json.dump(data, f, indent=2)
                return f"Saved to {filename}"
        except Exception as e:
            return f"Error saving: {str(e)}"

    def load_recording(self, filename="recording.json"):
        try:
            with open(filename, 'r') as f:
                data = json.load(f)
            with self.events_lock:
                self.events = data.get('events', [])
                stats = data.get('stats', {})
                self.move_count = 0
                self.click_count = 0
                self.key_press_count = 0
                self.key_release_count = 0
                # Recount stats
                for event in self.events:
                    if event['type'] == 'mouse_move':
                        self.move_count += 1
                    elif event['type'] == 'mouse_click':
                        self.click_count += 1
                    elif event['type'] == 'key_press':
                        self.key_press_count += 1
                    elif event['type'] == 'key_release':
                        self.key_release_count += 1

                self.total_duration = stats.get('duration', 0)
                self.status = f"Loaded: {len(self.events)} events"
                self.emit_stats()
                return f"Loaded: {len(self.events)} events"
        except Exception as e:
            return f"Error loading: {str(e)}"


class ColorPicker(ttk.Frame):
    def __init__(self, parent, initial_color="#00BCD4", on_change=None, app_instance=None):
        super().__init__(parent, style="Card.TFrame")
        self.parent = parent
        self.on_change = on_change
        self.app = app_instance
        self.predefined_colors = [
            ("#00BCD4", "Cyan (Default)"), ("#2ecc71", "Grün"), ("#3498db", "Blau"),
            ("#e74c3c", "Rot"), ("#f39c12", "Orange"), ("#9b59b6", "Lila"),
            ("#1abc9c", "Türkis"), ("#f1c40f", "Gelb"), ("#7f8c8d", "Grau")
        ]
        self.current_color_var = tk.StringVar(value=initial_color)
        self._create_ui()

    def _create_ui(self):
        preview_label_container = ttk.Frame(self, style="Card.TFrame")
        preview_label_container.pack(fill=tk.X, pady=(0,5))
        ttk.Label(preview_label_container, text="Accent Color:", style="TLabel").pack(side=tk.LEFT, padx=(0,10), anchor='w')
        self.color_preview = tk.Canvas(preview_label_container, width=40, height=25, relief=tk.RIDGE, borderwidth=1, background=BG_COLOR)
        self.color_preview.pack(side=tk.LEFT, anchor='w')
        self._update_preview()
        colors_button_container = ttk.Frame(self, style="Card.TFrame")
        colors_button_container.pack(fill=tk.X, pady=(5,0))
        predef_colors_frame = ttk.Frame(colors_button_container, style="Card.TFrame")
        predef_colors_frame.pack(side=tk.LEFT, fill=tk.X, expand=True)
        for i, (color, name) in enumerate(self.predefined_colors):
            color_btn = tk.Button(predef_colors_frame, bg=color, width=2, height=1, relief=tk.FLAT,
                                 borderwidth=1, command=lambda c=color: self.set_color(c))
            color_btn.grid(row=0, column=i, padx=2, pady=2)
            self.create_tooltip(color_btn, f"{name}\n{color}")
        custom_color_btn = ttk.Button(colors_button_container, text="Wähle...",
                                      command=self._open_color_chooser, style="Rounded.TButton")
        custom_color_btn.pack(side=tk.LEFT, padx=(10,0), pady=2, anchor='e')

    def _update_preview(self):
        color = self.current_color_var.get()
        try: self.color_preview.config(bg=color)
        except tk.TclError: self.color_preview.config(bg=DEFAULT_ACCENT_COLOR)

    def set_color(self, color):
        self.current_color_var.set(color); self._update_preview()
        if self.on_change: self.on_change(color)

    def get_color(self): return self.current_color_var.get()

    def _open_color_chooser(self):
        parent_window = self.winfo_toplevel()
        result = colorchooser.askcolor(initialcolor=self.current_color_var.get(), parent=parent_window)
        if result and result[1]: self.set_color(result[1])
        if parent_window and parent_window.winfo_exists(): parent_window.lift(); parent_window.grab_set()

    def create_tooltip(self, widget, text):
        tool_tip = ToolTip(widget)
        def enter(event): tool_tip.showtip(text)
        def leave(event): tool_tip.hidetip()
        widget.bind('<Enter>', enter); widget.bind('<Leave>', leave)

class ToolTip(object):
    def __init__(self, widget): self.widget = widget; self.tipwindow = None
    def showtip(self, text):
        self.text = text
        if self.tipwindow or not self.text: return
        x, y, _, _ = self.widget.bbox("insert"); x = x + self.widget.winfo_rootx() + 25; y = y + self.widget.winfo_rooty() + 20
        self.tipwindow = tw = tk.Toplevel(self.widget); tw.wm_overrideredirect(1); tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(tw, text=self.text, justify=tk.LEFT, background="#ffffe0", relief=tk.SOLID, borderwidth=1, font=("tahoma", "8", "normal"))
        label.pack(ipadx=1)
    def hidetip(self):
        tw = self.tipwindow; self.tipwindow = None
        if tw: tw.destroy()

class KeyMouseRecorderGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.configure(bg=BG_COLOR)

        try:
            if getattr(sys, 'frozen', False): application_path = os.path.dirname(sys.executable)
            else: application_path = os.path.dirname(os.path.abspath(__file__))
            icon_path = os.path.join(application_path, ICON_FILE)
            if os.path.exists(icon_path): self.root.iconbitmap(icon_path)
            else: self.log_message(f"WARNUNG: Icon '{ICON_FILE}' nicht gefunden.")
        except Exception as e: self.log_message(f"WARNUNG: Icon Fehler: {e}")

        window_width, window_height = 900, 750
        try:
            screen_width, screen_height = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
            center_x, center_y = int(screen_width/2 - window_width/2), int(screen_height/2 - window_height/2)
            self.root.geometry(f'{window_width}x{window_height}+{center_x}+{center_y}')
            self.root.minsize(750, 650)
        except: self.root.geometry(f'{window_width}x{window_height}'); self.root.minsize(750, 650)
        self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

        # Variables
        self.accent_color_var = tk.StringVar(value=DEFAULT_ACCENT_COLOR)
        self.status_var = tk.StringVar(value="Bereit")

        # Initialize Recording Manager
        self.manager = RecordingManager()
        self.manager.set_gui_callback(self.update_stats)

        # Load settings
        self._load_settings()

        # Style
        self.style = ttk.Style(self.root)

        # Setup initial styles after loading settings
        self._setup_styles()

        self._update_accent_color(self.accent_color_var.get(), initial_setup=True)

        # Header frame (for dragging)
        self.header_frame = tk.Frame(self.root, bg=HEADER_BG)
        self.header_frame.pack(side=tk.TOP, fill=tk.X)
        self.header_frame.bind("<ButtonPress-1>", self.start_move)
        self.header_frame.bind("<ButtonRelease-1>", self.stop_move)
        self.header_frame.bind("<B1-Motion>", self.on_move)

        # Header content
        self.title_label = tk.Label(self.header_frame, text=f"🖱️ {APP_NAME}", font=("Segoe UI", 12),
                                     fg=self.accent_color_var.get(), bg=HEADER_BG)
        self.title_label.pack(side=tk.LEFT, padx=10, pady=5)
        hotkey_info = tk.Label(self.header_frame, text="Global: F1 Record • F2 Stop • F3 Play • F4 Abort", font=("Segoe UI", 9), bg=HEADER_BG, fg=SYSTEM_COLOR)
        hotkey_info.pack(side=tk.LEFT, padx=(20,0), pady=5)
        self.min_btn = tk.Button(self.header_frame, text="–", command=self._on_minimize, width=3, bg=HEADER_BG, fg=TEXT_COLOR, relief="flat", font=("Segoe UI", 14, "bold"))
        self.min_btn.pack(side=tk.RIGHT, padx=5, pady=2)
        self.close_btn = tk.Button(self.header_frame, text="×", command=self._on_closing, width=3, bg=HEADER_BG, fg="red", relief="flat", font=("Segoe UI", 14, "bold"))
        self.close_btn.pack(side=tk.RIGHT, padx=0, pady=2)

        # Main container
        main_ui_frame = tk.Frame(self.root, bg=BG_COLOR)
        main_ui_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0,10))

        # Control panels container
        panels_container = tk.Frame(main_ui_frame, bg=BG_COLOR)
        panels_container.pack(fill=tk.X, pady=(0,10))

        # Recording controls panel
        recording_panel = tk.Frame(panels_container, bg=WIDGET_BG, relief="flat", padx=5, pady=5)
        recording_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0,10))

        # Settings button in top right
        settings_frame = tk.Frame(recording_panel, bg=WIDGET_BG)
        settings_frame.pack(fill=tk.X, pady=(5,0))
        settings_btn = tk.Button(settings_frame, text="⚙️ Settings", command=self._open_settings_window, bg=BUTTON_BG, fg=BUTTON_TEXT_COLOR, relief="flat",
                               font=("Segoe UI", 9), padx=8, pady=5, width=15)
        settings_btn.pack(side=tk.RIGHT)
        self._bind_dark_hover(settings_btn, BUTTON_BG, BUTTON_HOVER_BG)

        tk.Label(recording_panel, text="Recording Controls", font=("Segoe UI", 11, "bold"), bg=WIDGET_BG, fg=TEXT_COLOR).pack(fill=tk.X, pady=(5,5))

        # Recording mode
        mode_frame = tk.Frame(recording_panel, bg=WIDGET_BG)
        mode_frame.pack(fill=tk.X, padx=5, pady=5)
        tk.Label(mode_frame, text="Recording Mode:", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).pack(anchor=tk.W)
        self.record_type = tk.StringVar(value="all")
        mode_radio_frame = tk.Frame(mode_frame, bg=WIDGET_BG)
        mode_radio_frame.pack(fill=tk.X)
        ttk.Radiobutton(mode_radio_frame, text="All (Mouse + Keys)", variable=self.record_type, value="all").pack(anchor=tk.W)
        ttk.Radiobutton(mode_radio_frame, text="Mouse Only", variable=self.record_type, value="mouse").pack(anchor=tk.W)
        ttk.Radiobutton(mode_radio_frame, text="Keys Only", variable=self.record_type, value="keyboard").pack(anchor=tk.W)

        # Recording buttons
        record_buttons_frame = tk.Frame(recording_panel, bg=WIDGET_BG)
        record_buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        self.record_btn = tk.Button(record_buttons_frame, text="🎬 Start Recording (F1)", command=self.start_recording, bg=self.accent_color_var.get(), fg=TEXT_COLOR, relief="flat", font=("Segoe UI", 9, "bold"), padx=8, pady=5)
        self.record_btn.pack(fill=tk.X, pady=2)
        self.stop_record_btn = tk.Button(record_buttons_frame, text="⏹️ Stop Recording (F2)", command=self.stop_recording, state=tk.DISABLED, bg="#B71C1C", fg=TEXT_COLOR, relief="flat", font=("Segoe UI", 9), padx=8, pady=5)
        self.stop_record_btn.pack(fill=tk.X, pady=2)

        # Bind hover effects for recording buttons
        self._bind_dark_hover(self.record_btn, self.accent_color_var.get(), self.darken_color(self.accent_color_var.get()))
        self._bind_red_hover(self.stop_record_btn, "#B71C1C", "#D32F2F")

        # Playback panel
        playback_panel = tk.Frame(panels_container, bg=WIDGET_BG, relief="flat", padx=5, pady=5)
        playback_panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        tk.Label(playback_panel, text="Playback Controls", font=("Segoe UI", 11, "bold"), bg=WIDGET_BG, fg=TEXT_COLOR).pack(fill=tk.X, pady=(5,5))

        # Playback buttons
        play_buttons_frame = tk.Frame(playback_panel, bg=WIDGET_BG)
        play_buttons_frame.pack(fill=tk.X, padx=5, pady=5)
        self.play_btn = tk.Button(play_buttons_frame, text="▶️ Start Playback (F3)", command=self.start_playback, state=tk.DISABLED, bg=BUTTON_BG, fg=BUTTON_TEXT_COLOR, relief="flat", font=("Segoe UI", 9), padx=8, pady=5)
        self.play_btn.pack(fill=tk.X, pady=2)
        self.stop_play_btn = tk.Button(play_buttons_frame, text="⏸️ Stop Playback (F4)", command=self.stop_playback, state=tk.DISABLED, bg=BUTTON_BG, fg=BUTTON_TEXT_COLOR, relief="flat", font=("Segoe UI", 9), padx=8, pady=5)
        self.stop_play_btn.pack(fill=tk.X, pady=2)

        # Bind hover effects for playback buttons
        self._bind_dark_hover(self.play_btn, BUTTON_BG, BUTTON_HOVER_BG)
        self._bind_dark_hover(self.stop_play_btn, BUTTON_BG, BUTTON_HOVER_BG)

        # Playback settings
        playback_settings_frame = tk.Frame(playback_panel, bg=WIDGET_BG)
        playback_settings_frame.pack(fill=tk.X, padx=5, pady=5)

        speed_frame = tk.Frame(playback_settings_frame, bg=WIDGET_BG)
        speed_frame.pack(fill=tk.X, pady=2)
        tk.Label(speed_frame, text="Speed:", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).grid(row=0, column=0, sticky=tk.W)
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_scale = ttk.Scale(speed_frame, from_=0.1, to=5.0, variable=self.speed_var, orient=tk.HORIZONTAL, style="Accent.Horizontal.TScale")
        self.speed_scale.grid(row=0, column=1, sticky="ew", padx=5)
        self.speed_label = tk.Label(speed_frame, text="1.0x", bg=WIDGET_BG, fg=SYSTEM_COLOR, font=("Segoe UI", 8))
        self.speed_label.grid(row=0, column=2, sticky=tk.W)

        loop_frame = tk.Frame(playback_settings_frame, bg=WIDGET_BG)
        loop_frame.pack(fill=tk.X, pady=2)
        self.loop_var = tk.BooleanVar(value=False)
        loop_check = ttk.Checkbutton(loop_frame, text="Infinite loop (press F4 to stop)", variable=self.loop_var)
        loop_check.pack(anchor=tk.W)
        finite_loop_frame = tk.Frame(loop_frame, bg=WIDGET_BG)
        finite_loop_frame.pack(fill=tk.X, pady=2)
        tk.Label(finite_loop_frame, text="Loop Count:", bg=WIDGET_BG, fg=SYSTEM_COLOR, font=("Segoe UI", 8)).pack(side=tk.LEFT)
        self.loop_count_var = tk.IntVar(value=1)
        loop_spin = tk.Spinbox(finite_loop_frame, from_=1, to=100, textvariable=self.loop_count_var, width=5,
                              bg="#3c3c3c", fg=TEXT_COLOR, insertbackground=TEXT_COLOR, relief="flat")
        loop_spin.pack(side=tk.LEFT, padx=5)

        # File operations
        file_panel_frame = tk.Frame(main_ui_frame, bg=WIDGET_BG, relief="flat", padx=5, pady=5)
        file_panel_frame.pack(fill=tk.X, pady=(0,10))
        tk.Label(file_panel_frame, text="File Operations", font=("Segoe UI", 11, "bold"), bg=WIDGET_BG, fg=TEXT_COLOR).pack(fill=tk.X, pady=(5,5))
        file_buttons_frame = tk.Frame(file_panel_frame, bg=WIDGET_BG)
        file_buttons_frame.pack(fill=tk.X, padx=5)
        save_btn = tk.Button(file_buttons_frame, text="💾 Save Recording", command=self.save_recording, bg=BUTTON_BG, fg=BUTTON_TEXT_COLOR, relief="flat", font=("Segoe UI", 9), padx=8, pady=5)
        save_btn.pack(side=tk.LEFT, padx=(0,5))
        load_btn = tk.Button(file_buttons_frame, text="📁 Load Recording", command=self.load_recording, bg=BUTTON_BG, fg=BUTTON_TEXT_COLOR, relief="flat", font=("Segoe UI", 9), padx=8, pady=5)
        load_btn.pack(side=tk.LEFT)
        self.file_status_label = tk.Label(file_panel_frame, text="", bg=WIDGET_BG, fg="#00BCD4", font=("Segoe UI", 8))
        self.file_status_label.pack(fill=tk.X, padx=5, pady=2)

        # Bind hover effects for file buttons
        self._bind_dark_hover(save_btn, BUTTON_BG, BUTTON_HOVER_BG)
        self._bind_dark_hover(load_btn, BUTTON_BG, BUTTON_HOVER_BG)

        # Stats dashboard
        stats_panel = tk.Frame(main_ui_frame, bg=WIDGET_BG, relief="flat", padx=5, pady=5)
        stats_panel.pack(fill=tk.BOTH, expand=True)

        tk.Label(stats_panel, text="Recording Statistics", font=("Segoe UI", 11, "bold"), bg=WIDGET_BG, fg=TEXT_COLOR).pack(fill=tk.X, pady=(5,5))

        # Progress bar
        progress_frame = tk.Frame(stats_panel, bg=WIDGET_BG)
        progress_frame.pack(fill=tk.X, padx=5, pady=(0,10))
        self.progress_var = tk.IntVar(value=0)
        self.progress_bar = ttk.Progressbar(progress_frame, variable=self.progress_var, maximum=100, style="Accent.Horizontal.TProgressbar")
        self.progress_bar.pack(fill=tk.X)

        # Stats grid
        stats_grid = tk.Frame(stats_panel, bg=WIDGET_BG)
        stats_grid.pack(fill=tk.X, padx=5, pady=5)

        # Row 1: Status and Duration
        tk.Label(stats_grid, text="Status:", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).grid(row=0, column=0, sticky=tk.W, pady=2)
        self.status_label = tk.Label(stats_grid, text="Ready", bg=WIDGET_BG, fg="#00BCD4", font=("Segoe UI", 10))
        self.status_label.grid(row=0, column=1, sticky=tk.W, pady=2)
        tk.Label(stats_grid, text="Duration:", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).grid(row=0, column=2, sticky=tk.W, padx=(20,5), pady=2)
        self.duration_label = tk.Label(stats_grid, text="00:00:00", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 14, "bold"))
        self.duration_label.grid(row=0, column=3, sticky=tk.W, pady=2)

        # Row 2: Total Events and EPS
        tk.Label(stats_grid, text="Total Events:", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).grid(row=1, column=0, sticky=tk.W, pady=2)
        self.total_events_label = tk.Label(stats_grid, text="0", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 14, "bold"))
        self.total_events_label.grid(row=1, column=1, sticky=tk.W, pady=2)
        tk.Label(stats_grid, text="Events/Sec:", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).grid(row=1, column=2, sticky=tk.W, padx=(20,5), pady=2)
        self.eps_label = tk.Label(stats_grid, text="0.0", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 14, "bold"))
        self.eps_label.grid(row=1, column=3, sticky=tk.W, pady=2)

        # Row 3: Mouse and Key Events
        tk.Label(stats_grid, text="Mouse Events:", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).grid(row=2, column=0, sticky=tk.W, pady=2)
        self.mouse_events_label = tk.Label(stats_grid, text="0", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 14, "bold"))
        self.mouse_events_label.grid(row=2, column=1, sticky=tk.W, pady=2)
        tk.Label(stats_grid, text="Key Events:", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).grid(row=2, column=2, sticky=tk.W, padx=(20,5), pady=2)
        self.key_events_label = tk.Label(stats_grid, text="0", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 14, "bold"))
        self.key_events_label.grid(row=2, column=3, sticky=tk.W, pady=2)

        # Activity indicators
        activity_frame = tk.Frame(stats_panel, bg=WIDGET_BG)
        activity_frame.pack(fill=tk.X, padx=5, pady=(10,5))
        tk.Label(activity_frame, text="Activity:", bg=WIDGET_BG, fg=TEXT_COLOR, font=("Segoe UI", 10)).grid(row=0, column=0, sticky=tk.W)
        self.recording_indicator = tk.Label(activity_frame, text="● Recording: OFF", bg=WIDGET_BG, fg="red", font=("Segoe UI", 8))
        self.recording_indicator.grid(row=0, column=1, sticky=tk.W, padx=10)
        self.playing_indicator = tk.Label(activity_frame, text="● Playing: OFF", bg=WIDGET_BG, fg="green", font=("Segoe UI", 8))
        self.playing_indicator.grid(row=0, column=2, sticky=tk.W, padx=10)

        # Last event
        last_event_frame = tk.Frame(stats_panel, bg=WIDGET_BG)
        last_event_frame.pack(fill=tk.X, padx=5, pady=(5,10))
        tk.Label(last_event_frame, text="Last Event:", bg=WIDGET_BG, fg=SYSTEM_COLOR, font=("Segoe UI", 8)).pack(anchor=tk.W)
        self.last_event_label = tk.Label(last_event_frame, text="None", bg=WIDGET_BG, fg=SYSTEM_COLOR, font=("Segoe UI", 8))
        self.last_event_label.pack(anchor=tk.W, pady=2)

        # Update speed label when scale changes
        self.speed_scale.config(command=self.update_speed_label)

        self.log_message("KeyMouse Recorder Desktop gestartet.")

    def update_speed_label(self, value):
        self.speed_label.config(text=f"{float(value):.1f}x")

    def start_recording(self):
        record_type = self.record_type.get()
        self.manager.speed = self.speed_var.get()
        self.manager.loop_mode = self.loop_var.get()
        self.manager.loop_count = self.loop_count_var.get()
        threading.Thread(target=lambda: self.manager.start_recording(record_type)).start()

    def stop_recording(self):
        threading.Thread(target=self.manager.stop_recording).start()

    def start_playback(self):
        self.manager.speed = self.speed_var.get()
        self.manager.loop_mode = self.loop_var.get()
        self.manager.loop_count = self.loop_count_var.get()
        threading.Thread(target=self.manager.start_playback).start()

    def stop_playback(self):
        threading.Thread(target=self.manager.stop_playback).start()

    def save_recording(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Aufnahme speichern"
        )
        if filename:
            result = self.manager.save_recording(filename)
            self.file_status_label.config(text=result)

    def load_recording(self):
        filename = filedialog.askopenfilename(
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            title="Aufnahme laden"
        )
        if filename:
            result = self.manager.load_recording(filename)
            self.file_status_label.config(text=result)

    def update_stats(self, stats):
        def update():
            # Update status
            status_text = stats['status']
            if status_text.startswith("Recording"):
                status_color = self.accent_color_var.get()
            elif status_text.startswith("Playing"):
                status_color = "#2ecc71"
            else:
                status_color = TEXT_COLOR
            self.status_label.config(text=status_text, foreground=status_color)

            # Update stats labels
            self.total_events_label.config(text=str(stats['total_events']))
            self.mouse_events_label.config(text=str(stats['mouse_events']))
            self.key_events_label.config(text=str(stats['key_events']))
            self.duration_label.config(text=stats['duration'])
            self.eps_label.config(text=stats['eps'])
            self.last_event_label.config(text=stats['last_event'])

            # Update progress
            self.progress_var.set(stats['progress'])

            # Update activity indicators
            if stats['is_recording']:
                self.recording_indicator.config(text="● Aufnahme: EIN", foreground="#ff6b6b")
                self.record_btn.config(state=tk.DISABLED)
                self.stop_record_btn.config(state=tk.NORMAL)
                self.play_btn.config(state=tk.DISABLED)
                self.stop_play_btn.config(state=tk.DISABLED)
            elif stats['is_playing']:
                self.playing_indicator.config(text="● Wiedergabe: EIN", foreground="#2ecc71")
                self.record_btn.config(state=tk.DISABLED)
                self.stop_record_btn.config(state=tk.DISABLED)
                self.play_btn.config(state=tk.DISABLED)
                self.stop_play_btn.config(state=tk.NORMAL)
            else:
                self.recording_indicator.config(text="● Aufnahme: AUS", foreground=SYSTEM_COLOR)
                self.playing_indicator.config(text="● Wiedergabe: AUS", foreground=SYSTEM_COLOR)
                self.record_btn.config(state=tk.NORMAL)
                self.stop_record_btn.config(state=tk.DISABLED)
                self.play_btn.config(state=tk.NORMAL if stats['total_events'] > 0 else tk.DISABLED)
                self.stop_play_btn.config(state=tk.DISABLED)

        self.root.after(0, update)

    def start_move(self, event):
        self.x = event.x
        self.y = event.y

    def stop_move(self, event):
        self.x = None
        self.y = None

    def on_move(self, event):
        deltax = event.x - self.x
        deltay = event.y - self.y
        x = self.root.winfo_x() + deltax
        y = self.root.winfo_y() + deltay
        self.root.geometry(f"+{x}+{y}")

    def _on_minimize(self):
        if HAS_WIN32:
            # Use Windows API to minimize the window properly
            try:
                hwnd = win32gui.GetActiveWindow() if win32gui.GetActiveWindow() else self.root.winfo_id()
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                self.log_message("Window minimized using Win32 API")
                return
            except Exception as e:
                self.log_message(f"Win32 minimize failed: {e}")

        # Fallback: Temporarily disable overrideredirect and force geometry update
        self.root.overrideredirect(False)
        self.root.wm_attributes('-toolwindow', 0)  # Ensure it's a tool window
        self.root.update_idletasks()

        # Try to minimize using iconify
        self.root.iconify()

        # Re-enable overrideredirect immediately after iconify
        import time
        time.sleep(0.05)  # Very short sleep to ensure iconify takes effect
        self.root.overrideredirect(True)
        self.root.wm_attributes('-toolwindow', 0)
        self.log_message("Window minimized fallback method")

    def _on_closing(self):
        if messagebox.askokcancel("Beenden", "Möchtest du die Anwendung wirklich beenden?"):
            self._save_settings()
            self.root.destroy()

    def _update_accent_color(self, color_hex, initial_setup=False):
        if not color_hex or not color_hex.startswith("#"):
            color_hex = DEFAULT_ACCENT_COLOR
        self.accent_color_var.set(color_hex)
        if not initial_setup and hasattr(self,'style'):
            self._setup_styles()
            if hasattr(self,'title_label') and self.title_label.winfo_exists():
                self.title_label.config(foreground=color_hex)

    def _setup_styles(self):
        style = self.style
        style.theme_use("clam")

        current_accent = self.accent_color_var.get()

        # Base widget styles override
        style.configure("TFrame", background=BG_COLOR)
        style.configure("TLabel", background=BG_COLOR, foreground=TEXT_COLOR, font=("Segoe UI", 10))
        style.configure("TButton", background=BUTTON_BG, foreground=BUTTON_TEXT_COLOR, font=("Segoe UI", 9),
                       borderwidth=0, padding=(8, 5), relief="flat")

        # Root window background
        self.root.configure(bg=BG_COLOR)

        # Custom styles
        style.configure("App.TFrame", background=BG_COLOR)
        style.configure("Header.TFrame", background=HEADER_BG, relief="flat")
        style.configure("Card.TFrame", background=WIDGET_BG, relief="flat", padding=5)

        # Button styles with dark theme
        style.configure("Rounded.TButton", background=BUTTON_BG, foreground=BUTTON_TEXT_COLOR, borderwidth=0,
                       padding=(8, 5), relief="flat", font=("Segoe UI", 9))
        style.map("Rounded.TButton", background=[("active", BUTTON_HOVER_BG), ("disabled", WIDGET_BG),
                                                ("selected", BUTTON_HOVER_BG)], foreground=[("active", BUTTON_TEXT_COLOR),
                                                ("disabled", BUTTON_TEXT_INACTIVE)], relief=[("pressed", "sunken"), ("!pressed", "flat")])

        style.configure("Active.TButton", background=current_accent, foreground=TEXT_COLOR, borderwidth=0,
                       padding=(8, 5), relief="flat", font=("Segoe UI", 9, "bold"))
        style.map("Active.TButton", background=[("active", current_accent), ("selected", current_accent),
                                             ("pressed", self.darken_color(current_accent, 0.85))],
                  foreground=[("disabled", BUTTON_TEXT_INACTIVE), ("!disabled", TEXT_COLOR)],
                  relief=[("pressed", "sunken"), ("!pressed", "flat")])

        style.configure("Cancel.Rounded.TButton", background="#B71C1C", foreground=TEXT_COLOR, borderwidth=0,
                       padding=(8, 5), relief="flat", font=("Segoe UI", 9))
        style.map("Cancel.Rounded.TButton", background=[("active", "#D32F2F"), ("disabled", WIDGET_BG),
                                                       ("selected", "#B71C1C")], foreground=[("disabled", BUTTON_TEXT_INACTIVE)],
                  relief=[("pressed", "sunken"), ("!pressed", "flat")])

        # Header buttons
        style.configure("Close.TButton", background=HEADER_BG, foreground="red", borderwidth=0,
                       font=("Segoe UI", 14, "bold"), relief="flat", padding=1)
        style.map("Close.TButton", background=[("active", "red"), ("!active", HEADER_BG)],
                  foreground=[("active", "white"), ("!active", "red")], relief=[("pressed", "flat"), ("!pressed", "flat")])

        style.configure("Minimize.TButton", background=HEADER_BG, foreground=TEXT_COLOR, borderwidth=0,
                       font=("Segoe UI", 14, "bold"), relief="flat", padding=1)
        style.map("Minimize.TButton", background=[("active", "#555555"), ("!active", HEADER_BG)],
                  foreground=[("active", TEXT_COLOR), ("!active", TEXT_COLOR)], relief=[("pressed", "flat"), ("!pressed", "flat")])

        # Label variants
        style.configure("App.TLabel", background=BG_COLOR, foreground=TEXT_COLOR)
        style.configure("Header.TLabel", background=HEADER_BG, foreground=current_accent)
        style.configure("Status.TLabel", background=BG_COLOR, foreground=SYSTEM_COLOR, padding="2 5")
        style.configure("Small.TLabel", background=WIDGET_BG, foreground=SYSTEM_COLOR, font=("Segoe UI", 8))
        style.configure("Big.TLabel", background=WIDGET_BG, foreground=TEXT_COLOR, font=("Segoe UI", 14, "bold"))

        # Progress bar
        style.configure("Accent.Horizontal.TProgressbar", troughcolor=WIDGET_BG, background=current_accent,
                       bordercolor=WIDGET_BG, lightcolor=current_accent, darkcolor=current_accent)

        # Scale (seek bar)
        style.configure("Accent.Horizontal.TScale", background=WIDGET_BG, troughcolor=WIDGET_BG, bordercolor=WIDGET_BG,
                       lightcolor=WIDGET_BG, darkcolor=WIDGET_BG)

        # Checkbuttons (t_CONT)
        style.configure("TCheckbutton", background=WIDGET_BG, foreground=TEXT_COLOR, indicatorrelief=tk.FLAT,
                       indicatormargin=-1, indicatorpadding=0, indicatordiameter=18, padding=5)
        style.configure("Switch.TCheckbutton", background=WIDGET_BG, foreground=TEXT_COLOR, indicatorrelief=tk.FLAT,
                       indicatormargin=-1, indicatorpadding=0, indicatordiameter=18, padding=5)
        style.map("Switch.TCheckbutton", indicatorbackground=[('selected', current_accent), ('!selected', '#555555')],
                  indicatorforeground=[('selected', current_accent), ('!selected', '#555555')],
                  background=[('active', WIDGET_BG)])

        # Spinbox styling
        style.configure("Rounded.TSpinbox", background=WIDGET_BG, foreground=TEXT_COLOR, arrowcolor=TEXT_COLOR,
                       fieldbackground="#3c3c3c", bordercolor="#4a4a4a", lightcolor=WIDGET_BG, darkcolor=WIDGET_BG,
                       relief="flat", padding=3)
        style.map("Rounded.TSpinbox", bordercolor=[("focus", current_accent)], arrowcolor=[("pressed", current_accent),
                                                                                       ("active", current_accent)])

        # Radiobuttons
        style.configure("TRadiobutton", background=WIDGET_BG, foreground=TEXT_COLOR, indicatorrelief=tk.FLAT,
                       indicatormargin=-1, indicatorpadding=0, indicatordiameter=18, padding=5)
        style.map("TRadiobutton", indicatorbackground=[('selected', current_accent), ('!selected', WIDGET_BG)],
                  indicatorforeground=[('selected', current_accent), ('!selected', TEXT_COLOR)],
                  background=[('active', WIDGET_BG)])

    def darken_color(self, hex_color, factor=0.8):
        if not hex_color.startswith('#'): return hex_color
        hex_color = hex_color.lstrip('#')
        r, g, b = 0, 0, 0
        try: r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        except ValueError: return f"#{hex_color}"
        r, g, b = max(0, int(r * factor)), max(0, int(g * factor)), max(0, int(b * factor))
        return f"#{r:02x}{g:02x}{b:02x}"

    def _load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r') as f:
                    settings = json.load(f)
                self.accent_color_var.set(settings.get('accent_color', DEFAULT_ACCENT_COLOR))
        except Exception as e:
            self.accent_color_var.set(DEFAULT_ACCENT_COLOR)
            self.log_message(f"Fehler beim Laden der Einstellungen: {e}")

    def _save_settings(self):
        settings = {'accent_color': self.accent_color_var.get()}
        try:
            with open(SETTINGS_FILE, 'w') as f:
                json.dump(settings, f, indent=4)
        except Exception as e:
            self.log_message(f"Fehler beim Speichern der Einstellungen: {e}")

    def _open_settings_window(self):
        if hasattr(self, 'settings_window') and self.settings_window and self.settings_window.winfo_exists():
            self.settings_window.lift()
            self.settings_window.grab_set()
            return
        self.settings_window = tk.Toplevel(self.root)
        self.settings_window.title("Einstellungen")
        self.settings_window.configure(bg=BG_COLOR)
        self.settings_window.transient(self.root)
        self.settings_window.grab_set()
        set_w, set_h = 400, 300
        try:
            self.root.update_idletasks()
            main_x, main_y, main_w, main_h = self.root.winfo_x(), self.root.winfo_y(), self.root.winfo_width(), self.root.winfo_height()
            pos_x, pos_y = main_x + (main_w // 2) - (set_w // 2), main_y + (main_h // 2) - (set_h // 2)
            self.settings_window.geometry(f"{set_w}x{set_h}+{pos_x}+{pos_y}")
            self.settings_window.resizable(False, False)
        except:
            self.settings_window.geometry(f"{set_w}x{set_h}")
        frame = ttk.Frame(self.settings_window, padding=15, style="Card.TFrame")
        frame.pack(expand=True, fill=tk.BOTH, padx=10, pady=10)

        color_picker_frame = ttk.Frame(frame, style="Card.TFrame")
        color_picker_frame.pack(fill=tk.X, pady=5)
        self.color_picker_widget = ColorPicker(color_picker_frame, initial_color=self.accent_color_var.get(),
                                               on_change=self._update_accent_color, app_instance=self)
        self.color_picker_widget.pack(fill=tk.X, expand=True)

        button_frame = ttk.Frame(frame, style="Card.TFrame")
        button_frame.pack(fill=tk.X, pady=(15, 0))

        def apply_and_close():
            self._update_accent_color(self.color_picker_widget.get_color())
            self._save_settings()
            self.log_message("Einstellungen gespeichert.")
            if self.settings_window and self.settings_window.winfo_exists():
                self.settings_window.destroy()
                self.settings_window = None
        def cancel_and_close():
            self._load_settings()
            self._update_accent_color(self.accent_color_var.get())
            if self.settings_window and self.settings_window.winfo_exists():
                self.settings_window.destroy()
                self.settings_window = None

        save_button = ttk.Button(button_frame, text="Speichern & Schließen", command=apply_and_close, style="Active.TButton")
        save_button.pack(side=tk.RIGHT, padx=5)
        cancel_button = ttk.Button(button_frame, text="Abbrechen", command=cancel_and_close, style="Rounded.TButton")
        cancel_button.pack(side=tk.RIGHT, padx=5)

        self.settings_window.protocol("WM_DELETE_WINDOW", cancel_and_close)

    def log_message(self, message, level=logging.INFO):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")


    def _bind_dark_hover(self, widget, normal_bg, hover_bg):
        def on_enter(event):
            widget.config(bg=hover_bg)
        def on_leave(event):
            widget.config(bg=normal_bg)
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)

    def _bind_red_hover(self, widget, normal_bg, hover_bg):
        def on_enter(event):
            widget.config(bg=hover_bg, fg=TEXT_COLOR)
        def on_leave(event):
            widget.config(bg=normal_bg, fg=TEXT_COLOR)
        widget.bind("<Enter>", on_enter)
        widget.bind("<Leave>", on_leave)


if __name__ == "__main__":
    root = tk.Tk()
    app = KeyMouseRecorderGUI(root)
    root.mainloop()

    # Clean up listeners on exit
    if app.manager.abort_listener:
        app.manager.abort_listener.stop()
    print("App closed.")
