# LinguaSnap

An English vocabulary learning assistant for gamers. Click a floating bubble, speak a word, and get AI-powered explanations with pronunciation — all without leaving your game.

## Download & Run

1. Go to **[Releases](https://github.com/sagezhao0-source/lingua-snap/releases)** and download `LinguaSnap.exe`
2. **Right-click > Run as Administrator** (required for global hotkeys)
3. Right-click the tray icon > **Settings** to configure:
   - Your **LLM API key** (e.g. [DeepSeek](https://platform.deepseek.com/), OpenAI, etc.)
   - **Obsidian vault path** (if you want to save word notes)

That's it. No Python, no dependencies, nothing to install.

## Features

- **Floating bubble UI** — always on top, never blocks your game
- **Push-to-talk recording** — save a word and get instant lookup
- **Typed input** — type words instead of speaking when needed
- **AI-powered explanations** — IPA pronunciation, definition (with part of speech), etymology, and examples
- **Text-to-speech** — click the speaker icon to hear correct pronunciation
- **Obsidian integration** — save word notes directly to your Obsidian vault (separate files or journal mode)
- **Screenshot & clipboard context** — capture game context alongside your notes

## Usage

1. **Start recording** — Click the floating bubble or press `Ctrl+Shift+F`
2. **Speak a word** — Say the word clearly into your microphone
3. **Stop recording** — Click the bubble again or release the hotkey
4. **Confirm/Edit** — Correct the transcription if needed, then click Look Up
5. **View results** — Pronunciation (click speaker to hear), definition, etymology, examples
6. **Add notes** — Write notes in the editor, paste images (Ctrl+V)
7. **Save to Obsidian** — Click "Save to Obsidian" to persist to your vault

### Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+Shift+F` | Start/stop recording (push-to-talk) |
| `Ctrl+Shift+G` | Capture screenshot + clipboard context |

### Tray Menu

Right-click the tray icon for:
- Record Word / Stop & Look Up
- Test Microphone
- Open Config (edit `config.json` in text editor)
- **Settings** (graphical settings dialog — recommended)
- Change Game (for journal mode)
- Quit

### Settings

All settings are managed through the **Settings** dialog (tray icon > Settings):

| Tab | Configurable |
|-----|-------------|
| **LLM** | Base URL, API Key, Model |
| **Obsidian** | Enable/disable, Vault path, Subfolder, Save mode (separate/journal), Attachments |
| **Speech** | TTS speed (50–300 wpm), Whisper model/device/compute |
| **Hotkeys** | Record hotkey, Context capture hotkey |

## Requirements

- Windows 10 or later
- A microphone
- An API key from an OpenAI-compatible LLM provider (e.g. [DeepSeek](https://platform.deepseek.com/))

## Build from Source

If you prefer to run from source or contribute:

```bash
git clone https://github.com/sagezhao0-source/lingua-snap.git
cd lingua-snap
pip install -r requirements.txt
copy config.example.json config.json  # then edit config.json with your API key
python main.py
```

To build the standalone exe:

```bash
pip install pyinstaller
pyinstaller linguasnap.spec
# Output: dist/LinguaSnap.exe
```

## Project Structure

```
lingua-snap/
  main.py              # App entry point, tray icon, signal wiring
  floating_panel.py    # Floating bubble + result card (QWebEngineView)
  settings_dialog.py   # Settings dialog (LLM, Obsidian, Speech, Hotkeys)
  config.py            # Thread-safe config manager
  llm_client.py        # OpenAI-compatible LLM API client
  tts_engine.py        # TTS (Windows SAPI5 via pyttsx3)
  obsidian_writer.py   # Obsidian markdown writer
  recorder.py          # Microphone audio recorder
  transcriber.py       # faster-whisper speech-to-text
  hotkey.py            # Global hotkey listener
  context_capture.py   # Screenshot + clipboard capture
  linguasnap.spec      # PyInstaller spec
  config.example.json  # Config template
```

## License

MIT
