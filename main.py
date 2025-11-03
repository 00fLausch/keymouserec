# KeyMouse Recorder Web App
# Records mouse and keyboard actions, saves to JSON, replays with adjustable speed and loop modes
# Web-based interface using Flask, Socket.IO and Bootstrap

import threading
import time
import json
import os
import sys
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit
from pynput import keyboard, mouse
import pyautogui
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0
import logging
from threading import Lock

APP_NAME = "KeyMouse Recorder Web"
ICON_FILE = "icon.ico"

gui_logger = logging.getLogger('keymouse_gui')
gui_logger.setLevel(logging.INFO)

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, async_mode='threading')

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

    def start_global_listeners(self):
        def on_press(key):
            if key == keyboard.Key.f1 and not self.is_recording:
                socketio.start_background_task(self.start_recording)
            elif key == keyboard.Key.f2 and self.is_recording:
                socketio.start_background_task(self.stop_recording)
            elif key == keyboard.Key.f3 and not self.is_playing:
                socketio.start_background_task(self.start_playback)
            elif key == keyboard.Key.f4 and self.is_playing:
                self.abort_playback = True
                socketio.start_background_task(self.stop_playback)

        self.abort_listener = keyboard.Listener(on_press=on_press)
        self.abort_listener.start()

    def emit_stats(self):
        # Emit current stats via Socket.IO
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

            socketio.emit('stats_update', {
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

        socketio.start_background_task(self.run_listeners)

        # Periodic stats updates
        def update_loop():
            while self.is_recording:
                self.emit_stats()
                socketio.sleep(0.5)
            self.emit_stats()

        socketio.start_background_task(update_loop)

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
        socketio.start_background_task(self.run_playback)

        def update_loop():
            while self.is_playing:
                self.emit_stats()
                socketio.sleep(0.1)

        socketio.start_background_task(update_loop)

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

# Global manager
manager = RecordingManager()

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('start_recording')
def handle_start_recording(data):
    record_type = data.get('type', 'all')
    manager.start_recording(record_type)

@socketio.on('stop_recording')
def handle_stop_recording(data):
    manager.stop_recording()

@socketio.on('start_playback')
def handle_start_playback(data):
    manager.speed = data.get('speed', 1.0)
    manager.loop_mode = data.get('loop_mode', False)
    manager.loop_count = data.get('loop_count', 1)
    manager.start_playback()

@socketio.on('stop_playback')
def handle_stop_playback(data):
    manager.stop_playback()

@socketio.on('save_recording')
def handle_save_recording(data):
    filename = data.get('filename', 'recording.json')
    result = manager.save_recording(filename)
    emit('save_result', {'message': result})

@socketio.on('load_recording')
def handle_load_recording(data):
    filename = data.get('filename', 'recording.json')
    result = manager.load_recording(filename)
    emit('load_result', {'message': result})

@socketio.on('get_stats')
def handle_get_stats():
    manager.emit_stats()

if __name__ == "__main__":
    print("Starting KeyMouse Recorder Web App...")
    print("Open your browser to http://localhost:5000")
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)

    # Clean up listeners on exit
    if manager.abort_listener:
        manager.abort_listener.stop()
    print("App closed.")
