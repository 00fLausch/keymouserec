# 🖱️ KeyMouse Recorder

A powerful application for recording and replaying mouse and keyboard actions. Available as both a web app (Flask) and desktop app (Tkinter).

## ✨ Features

- **High-precision recording** of mouse and keyboard actions
- **Multiple recording modes**: All actions, mouse only, or keyboard only
- **Adjustable playback speed** (0.1x to 5.0x)
- **Loop modes**: Infinite loop or limited repetitions
- **Real-time statistics** during recording
- **JSON storage format** for recordings
- **Global hotkeys** for quick control (F1-F4)
- **Modern user interface** with Bootstrap (web) and Tkinter (desktop)
- **Cross-platform** compatible

## 🚀 Installation

### Prerequisites

- Python 3.7+
- pip for package installation

### Install Dependencies

```bash
pip install flask flask-socketio pynput pyautogui
```

For the desktop version (Windows):
```bash
pip install pywin32  # For Windows-specific functions
```

## 📖 Usage

### Start Web Version

```bash
python main.py
```

Open your browser and go to `http://localhost:5000`

### Start Desktop Version

```bash
python main_desktop.pyw
```

### Controls

- **F1**: Start recording
- **F2**: Stop recording
- **F3**: Start playback
- **F4**: Stop playback

### Recording Modes

1. **All**: Records mouse movements, clicks, and key presses
2. **Mouse Only**: Mouse actions only
3. **Keys Only**: Keyboard actions only

### Playback Settings

- **Speed**: From 0.1x (very slow) to 5.0x (very fast)
- **Loop Mode**: Infinite loop or limited number of repetitions

## 📁 Project Structure

```
keymouserec/
├── main.py                 # Web app (Flask + Socket.IO)
├── main_desktop.pyw        # Desktop app (Tkinter)
├── keymouserec_settings.json  # Settings for desktop app
├── templates/
│   └── index.html         # Web interface
├── __pycache__/           # Python cache
├── .venv/                 # Virtual environment
└── README.md             # This file
```

## 🔧 Technical Details

### Web Version
- **Backend**: Flask with Socket.IO for real-time communication
- **Frontend**: Bootstrap 5, Font Awesome icons
- **Styling**: Dark theme with gradients and animations

### Desktop Version
- **GUI**: Tkinter with ttk for modern widgets
- **Styling**: Dark theme with customizable accent colors
- **Window**: Borderless design with drag functionality

### Recording Technology
- **Mouse**: pynput for precise recording
- **Keys**: pynput for keyboard events
- **Timing**: Timestamp-based playback
- **Threading**: Separate threads for recording and playback

## 📊 Statistics

During recording, the following metrics are displayed in real-time:
- Total number of events
- Mouse events (movements + clicks)
- Key events (press + release)
- Recording duration
- Events per second
- Progress bar

## 💾 File Format

Recordings are saved as JSON:

```json
{
  "events": [
    {
      "type": "mouse_move",
      "x": 100,
      "y": 200,
      "time": 1.234
    },
    {
      "type": "key_press",
      "key": "Key.enter",
      "time": 2.345
    }
  ],
  "timestamp": 1634567890.123,
  "description": "Recorded macro",
  "stats": {
    "total_events": 150,
    "mouse_events": 120,
    "key_events": 30,
    "duration": 45.67
  }
}
```

## 🛠️ Development

### Code Quality
- Clean separation of UI and logic
- Comprehensive error handling
- Thread-safe implementation
- Modular architecture

### Advanced Features
- Customizable hotkeys
- Multiple simultaneous recordings
- Export to various formats
- Plugin system for extensions

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributions

Contributions are welcome! Please create an issue for feature requests or bugs.

## 📞 Support

For questions or issues:
1. Check console output for error messages
2. Ensure all dependencies are installed
3. Test with administrator privileges (for global hotkeys)

---

**Note**: This application uses system hooks for recording. Additional permissions may be required on some systems.
