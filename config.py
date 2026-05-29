"""Configuration management for LinguaSnap."""

import json
import os
import tempfile
from threading import Lock

DEFAULT_CONFIG = {
    "hotkey": "ctrl+shift+f",
    "context_hotkey": "ctrl+shift+g",
    "whisper_model": "tiny",
    "whisper_device": "cpu",
    "whisper_compute_type": "int8",
    "llm_base_url": "https://api.deepseek.com",
    "llm_api_key": "",
    "llm_model": "deepseek-chat",
    "sample_rate": 16000,
    "max_recording_sec": 30,
    "min_recording_sec": 0.3,
    "overlay_duration_sec": 10,
    "tts_rate": 150,
    "obsidian": {
        "enabled": False,
        "vault_path": "",
        "subfolder": "lingua-snap",
        "include_game_name": False,
        "game_name": "",
        "save_mode": "separate",
        "attachments_subfolder": "attachments"
    }
}


class Config:
    """Thread-safe singleton configuration manager."""

    _instance = None
    _lock = Lock()

    def __new__(cls, config_path=None):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, config_path=None):
        if self._initialized:
            return
        self._initialized = True

        if config_path is None:
            config_path = os.path.join(
                os.path.dirname(os.path.abspath(__file__)), "config.json"
            )
        self._config_path = config_path
        self._data = {}
        self._file_lock = Lock()
        self.load()

    def load(self):
        """Load config from file, falling back to defaults on any error."""
        if os.path.exists(self._config_path):
            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self._data = self._deep_merge(DEFAULT_CONFIG.copy(), data)
            except (json.JSONDecodeError, IOError):
                self._data = DEFAULT_CONFIG.copy()
        else:
            self._data = DEFAULT_CONFIG.copy()
            self.save()

    def save(self):
        """Atomically write config to file."""
        with self._file_lock:
            try:
                dirname = os.path.dirname(self._config_path)
                if dirname and not os.path.exists(dirname):
                    os.makedirs(dirname, exist_ok=True)
                fd, tmp_path = tempfile.mkstemp(
                    dir=dirname or None, suffix=".json"
                )
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)
                os.replace(tmp_path, self._config_path)
            except Exception:
                pass

    def _deep_merge(self, base, override):
        """Recursively merge override dict into base dict."""
        result = base.copy()
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        return result

    def get(self, key, default=None):
        """Get a config value by dot-separated key (e.g. 'obsidian.enabled')."""
        keys = key.split(".")
        node = self._data
        for k in keys:
            if isinstance(node, dict):
                node = node.get(k)
            else:
                return default
        return node if node is not None else default

    def set(self, key, value):
        """Set a config value by dot-separated key and save."""
        keys = key.split(".")
        node = self._data
        for k in keys[:-1]:
            if k not in node or not isinstance(node[k], dict):
                node[k] = {}
            node = node[k]
        node[keys[-1]] = value
        self.save()

    @property
    def hotkey(self):
        return self._data.get("hotkey", "ctrl+shift+f")

    @property
    def whisper_model_size(self):
        return self._data.get("whisper_model", "tiny")

    @property
    def whisper_device(self):
        return self._data.get("whisper_device", "cpu")

    @property
    def whisper_compute_type(self):
        return self._data.get("whisper_compute_type", "int8")

    @property
    def llm_base_url(self):
        return self._data.get("llm_base_url", "")

    @property
    def llm_api_key(self):
        return self._data.get("llm_api_key", "")

    @property
    def llm_model(self):
        return self._data.get("llm_model", "gpt-3.5-turbo")

    @property
    def tts_rate(self):
        return self._data.get("tts_rate", 150)

    @property
    def obsidian_enabled(self):
        return self.get("obsidian.enabled", False)

    @property
    def obsidian_vault_path(self):
        return self.get("obsidian.vault_path", "")

    @property
    def obsidian_subfolder(self):
        return self.get("obsidian.subfolder", "lingua-snap")

    @property
    def obsidian_game_name(self):
        return self.get("obsidian.game_name", "")

    @property
    def context_hotkey(self):
        return self._data.get("context_hotkey", "ctrl+shift+g")

    @property
    def obsidian_save_mode(self):
        return self.get("obsidian.save_mode", "separate")

    @property
    def obsidian_attachments_subfolder(self):
        return self.get("obsidian.attachments_subfolder", "attachments")
