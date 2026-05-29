# LinguaSnap

An English vocabulary learning assistant for gamers. Click a floating bubble, speak a word, and get AI-powered explanations with pronunciation — all without leaving your game.

## Features

- **Floating bubble UI** — always on top, never blocks your game
- **Push-to-talk recording** — speak a word and get instant lookup
- **AI-powered explanations** — IPA pronunciation, definition, etymology, and examples
- **Text-to-speech** — hear the correct pronunciation
- **Obsidian integration** — save word notes directly to your Obsidian vault
- **Typed input** — type words instead of speaking when needed
- **Screenshot & clipboard context** — capture game context alongside your notes

## Prerequisites

- Windows 10 or later
- Python 3.10+
- A microphone
- Administrator privileges (required for global hotkeys)
- An API key from an OpenAI-compatible LLM provider (e.g. [DeepSeek](https://platform.deepseek.com/), OpenAI, etc.)

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/your-username/lingua-snap.git
cd lingua-snap
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure

Copy the example config and edit it with your API key:

```bash
copy config.example.json config.json
```

Open `config.json` and fill in your `llm_api_key`. You can also configure the settings from within the app (right-click the tray icon > **Settings**).

### 4. Run

```bash
python main.py
```

Run as administrator for global hotkey support (Ctrl+Shift+F to record).

## Configuration

All settings are managed through the **Settings** dialog (tray icon > Settings) or by editing `config.json` directly.

### LLM

| Setting | Description |
|---------|-------------|
| `llm_base_url` | OpenAI-compatible API endpoint |
| `llm_api_key` | Your API key |
| `llm_model` | Model name (e.g. `deepseek-chat`, `gpt-4o`) |

### Obsidian

Enable Obsidian integration to save word notes as markdown files in your vault. Supports two save modes:

- **Separate** — one `.md` file per word lookup
- **Journal** — all lookups appended to a single notebook file per game

### Speech

- **TTS Speed** — adjust pronunciation speed (50–300 words per minute)
- **Whisper Model** — larger models are more accurate but slower (`tiny` is the fastest)

## Building from Source

To create a standalone `.exe`:

```bash
pip install pyinstaller
pyinstaller linguasnap.spec
```

The executable will be at `dist/LinguaSnap.exe`.

## Usage

1. **Start recording** — Click the floating bubble or press `Ctrl+Shift+F`
2. **Speak a word** — Say the word clearly into your microphone
3. **Stop recording** — Click the bubble again or release the hotkey
4. **Confirm/Edit** — Correct the transcription if needed, then click Look Up
5. **View results** — See pronunciation (click the speaker icon to hear it), definition, etymology, and examples
6. **Add notes** — Write your own notes in the editor, paste images (Ctrl+V)
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
- **Settings** (graphical settings dialog)
- Change Game (for journal mode)
- Quit

## Project Structure

```
lingua-snap/
  main.py              # Application entry point, tray icon, signal wiring
  floating_panel.py    # Floating bubble + result card (QWebEngineView)
  settings_dialog.py   # Settings dialog (LLM, Obsidian, Speech, Hotkeys)
  config.py            # Thread-safe config manager (JSON)
  llm_client.py        # OpenAI-compatible LLM API client
  tts_engine.py        # Text-to-speech (Windows SAPI5 via pyttsx3)
  obsidian_writer.py   # Obsidian vault markdown writer
  recorder.py          # Microphone audio recorder
  transcriber.py       # faster-whisper speech-to-text
  hotkey.py            # Global hotkey listener
  context_capture.py   # Screenshot + clipboard capture
  overlay.py           # Legacy overlay window
  linguasnap.spec      # PyInstaller spec for building .exe
  config.example.json  # Configuration template
  requirements.txt     # Python dependencies
```

## License

MIT
