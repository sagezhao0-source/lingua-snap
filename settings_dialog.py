"""Settings dialog for LinguaSnap."""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QSlider, QTabWidget, QVBoxLayout, QWidget
)


class SettingsDialog(QDialog):
    """Settings dialog with tabs for LLM, Obsidian, Speech, and Hotkeys."""

    CARD_STYLE = """
        QDialog {
            background-color: #ffffff;
            border: 0.5px solid #e5e5e5;
            border-radius: 12px;
        }
        QLabel {
            background: transparent;
        }
        QTabWidget::pane {
            border: none;
            background: transparent;
        }
        QTabBar::tab {
            background: transparent;
            color: #888;
            font-family: "Segoe UI";
            font-size: 13px;
            padding: 8px 16px;
            border: none;
            border-bottom: 2px solid transparent;
            min-width: 60px;
        }
        QTabBar::tab:selected {
            color: #185FA5;
            border-bottom: 2px solid #185FA5;
        }
        QTabBar::tab:hover {
            color: #444;
        }
        QLineEdit {
            background-color: #F3F3F3;
            color: #1a1a1a;
            border: none;
            border-radius: 8px;
            padding: 8px 12px;
            font-family: "Segoe UI";
            font-size: 13px;
        }
        QComboBox {
            background-color: #F3F3F3;
            color: #1a1a1a;
            border: none;
            border-radius: 8px;
            padding: 8px 12px;
            font-family: "Segoe UI";
            font-size: 13px;
        }
        QComboBox::drop-down {
            border: none;
        }
        QCheckBox {
            font-family: "Segoe UI";
            font-size: 13px;
            color: #333;
        }
        QCheckBox::indicator {
            width: 18px;
            height: 18px;
        }
        QSlider::groove:horizontal {
            border: none;
            height: 4px;
            background: #e0e0e0;
            border-radius: 2px;
        }
        QSlider::handle:horizontal {
            background: #185FA5;
            border: none;
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }
        QPushButton#cancelBtn, QPushButton#okBtn {
            background: transparent;
            border: 1.5px solid #c0c0c0;
            color: #999;
            font-size: 13px;
            font-weight: bold;
            border-radius: 10px;
            font-family: "Segoe UI";
            padding: 8px 24px;
        }
        QPushButton#cancelBtn:hover {
            background: #f5f5f5;
            border-color: #888;
            color: #666;
        }
        QPushButton#okBtn {
            background: #185FA5;
            border-color: #185FA5;
            color: #fff;
        }
        QPushButton#okBtn:hover {
            background: #134b84;
            border-color: #134b84;
        }
        QPushButton#browseBtn {
            background: transparent;
            border: 1.5px solid #c0c0c0;
            color: #666;
            font-size: 12px;
            font-family: "Segoe UI";
            border-radius: 8px;
            padding: 8px 12px;
        }
        QPushButton#browseBtn:hover {
            background: #f5f5f5;
            border-color: #888;
        }
        QPushButton#toggleKeyBtn {
            background: transparent;
            border: none;
            color: #888;
            font-size: 14px;
            font-family: "Segoe UI";
            padding: 4px 8px;
        }
        QPushButton#toggleKeyBtn:hover {
            color: #333;
        }
    """

    def __init__(self, config, parent=None):
        super().__init__(parent)
        self._config = config
        self._whisper_changed = False

        self.setWindowTitle("LinguaSnap — Settings")
        self.setFixedSize(520, 460)
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.Dialog | Qt.WindowStaysOnTopHint
        )
        self.setStyleSheet(self.CARD_STYLE)

        # ── Main layout ───────────────────────────────────────
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Title
        main_layout.addSpacing(20)
        title = QLabel("Settings")
        title.setFont(QFont("Segoe UI", 16, 600))
        title.setStyleSheet("color: #222;")
        title_row = QHBoxLayout()
        title_row.setContentsMargins(28, 0, 28, 0)
        title_row.addWidget(title)
        title_row.addStretch()
        main_layout.addLayout(title_row)

        main_layout.addSpacing(12)

        # Tab widget
        self._tabs = QTabWidget()
        self._tabs.setFont(QFont("Segoe UI", 11))
        self._tabs.addTab(self._create_llm_tab(), "LLM")
        self._tabs.addTab(self._create_obsidian_tab(), "Obsidian")
        self._tabs.addTab(self._create_speech_tab(), "Speech")
        self._tabs.addTab(self._create_hotkeys_tab(), "Hotkeys")

        tabs_row = QHBoxLayout()
        tabs_row.setContentsMargins(28, 0, 28, 0)
        tabs_row.addWidget(self._tabs)
        main_layout.addLayout(tabs_row)

        # Buttons
        main_layout.addSpacing(16)
        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(28, 0, 28, 0)
        btn_row.setSpacing(10)
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setObjectName("cancelBtn")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        save_btn = QPushButton("Save")
        save_btn.setObjectName("okBtn")
        save_btn.setDefault(True)
        save_btn.clicked.connect(self._save_settings)
        btn_row.addWidget(save_btn)

        main_layout.addLayout(btn_row)
        main_layout.addSpacing(20)
        self.setLayout(main_layout)

        # Populate fields from current config
        self._load_settings()

    # ── Tab factories ─────────────────────────────────────────

    def _create_llm_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(14)
        label_font = QFont("Segoe UI", 12)
        label_style = "color: #555;"

        # Base URL
        url_label = QLabel("Base URL")
        url_label.setFont(label_font)
        url_label.setStyleSheet(label_style)
        self._base_url = QLineEdit()
        layout.addRow(url_label, self._base_url)

        # API Key
        key_label = QLabel("API Key")
        key_label.setFont(label_font)
        key_label.setStyleSheet(label_style)
        key_row = QHBoxLayout()
        key_row.setSpacing(0)
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.Password)
        key_row.addWidget(self._api_key)
        self._toggle_key_btn = QPushButton("\u25C9")  # ◉
        self._toggle_key_btn.setObjectName("toggleKeyBtn")
        self._toggle_key_btn.setFixedSize(36, 34)
        self._toggle_key_btn.setToolTip("Show/hide API key")
        self._toggle_key_btn.clicked.connect(self._toggle_api_key_visibility)
        key_row.addWidget(self._toggle_key_btn)
        key_widget = QWidget()
        key_widget.setLayout(key_row)
        layout.addRow(key_label, key_widget)

        # Model
        model_label = QLabel("Model")
        model_label.setFont(label_font)
        model_label.setStyleSheet(label_style)
        self._model = QLineEdit()
        layout.addRow(model_label, self._model)

        tab.setLayout(layout)
        return tab

    def _create_obsidian_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(14)
        label_font = QFont("Segoe UI", 12)
        label_style = "color: #555;"

        # Enabled
        self._obsidian_enabled = QCheckBox("Enable Obsidian integration")
        self._obsidian_enabled.setFont(label_font)
        layout.addRow("", self._obsidian_enabled)

        # Vault path
        path_label = QLabel("Vault Path")
        path_label.setFont(label_font)
        path_label.setStyleSheet(label_style)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self._vault_path = QLineEdit()
        path_row.addWidget(self._vault_path)
        browse_btn = QPushButton("Browse...")
        browse_btn.setObjectName("browseBtn")
        browse_btn.clicked.connect(self._browse_vault)
        path_row.addWidget(browse_btn)
        path_widget = QWidget()
        path_widget.setLayout(path_row)
        layout.addRow(path_label, path_widget)

        # Subfolder
        sub_label = QLabel("Subfolder")
        sub_label.setFont(label_font)
        sub_label.setStyleSheet(label_style)
        self._subfolder = QLineEdit()
        layout.addRow(sub_label, self._subfolder)

        # Save mode
        mode_label = QLabel("Save Mode")
        mode_label.setFont(label_font)
        mode_label.setStyleSheet(label_style)
        self._save_mode = QComboBox()
        self._save_mode.addItem("separate — one file per word", "separate")
        self._save_mode.addItem("journal — append to game notebook", "journal")
        layout.addRow(mode_label, self._save_mode)

        # Attachments subfolder
        att_label = QLabel("Attachments")
        att_label.setFont(label_font)
        att_label.setStyleSheet(label_style)
        self._attachments_subfolder = QLineEdit()
        layout.addRow(att_label, self._attachments_subfolder)

        tab.setLayout(layout)
        return tab

    def _create_speech_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(14)
        label_font = QFont("Segoe UI", 12)
        label_style = "color: #555;"

        # TTS Rate
        rate_label = QLabel("TTS Speed")
        rate_label.setFont(label_font)
        rate_label.setStyleSheet(label_style)
        rate_row = QHBoxLayout()
        rate_row.setSpacing(10)
        self._rate_slider = QSlider(Qt.Horizontal)
        self._rate_slider.setRange(50, 300)
        self._rate_slider.setValue(150)
        rate_row.addWidget(self._rate_slider, 1)
        self._rate_label = QLabel("150")
        self._rate_label.setFont(QFont("Segoe UI", 13))
        self._rate_label.setStyleSheet("color: #185FA5; min-width: 36px;")
        self._rate_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._rate_slider.valueChanged.connect(
            lambda v: self._rate_label.setText(str(v))
        )
        rate_row.addWidget(self._rate_label)
        rate_widget = QWidget()
        rate_widget.setLayout(rate_row)
        layout.addRow(rate_label, rate_widget)

        # Whisper model size
        model_label = QLabel("Whisper Model")
        model_label.setFont(label_font)
        model_label.setStyleSheet(label_style)
        self._whisper_model = QComboBox()
        self._whisper_model.addItems(["tiny", "base", "small", "medium"])
        layout.addRow(model_label, self._whisper_model)

        # Whisper device
        device_label = QLabel("Device")
        device_label.setFont(label_font)
        device_label.setStyleSheet(label_style)
        self._whisper_device = QComboBox()
        self._whisper_device.addItems(["cpu", "cuda"])
        layout.addRow(device_label, self._whisper_device)

        # Whisper compute type
        compute_label = QLabel("Compute Type")
        compute_label.setFont(label_font)
        compute_label.setStyleSheet(label_style)
        self._whisper_compute = QComboBox()
        self._whisper_compute.addItems(["int8", "float16", "int8_float16"])
        layout.addRow(compute_label, self._whisper_compute)

        tab.setLayout(layout)
        return tab

    def _create_hotkeys_tab(self):
        tab = QWidget()
        layout = QFormLayout()
        layout.setContentsMargins(8, 16, 8, 16)
        layout.setSpacing(14)
        label_font = QFont("Segoe UI", 12)
        label_style = "color: #555;"
        hint_style = "color: #aaa; font-size: 11px;"

        # Record hotkey
        rec_label = QLabel("Record Hotkey")
        rec_label.setFont(label_font)
        rec_label.setStyleSheet(label_style)
        self._hotkey = QLineEdit()
        self._hotkey.setPlaceholderText("e.g. ctrl+shift+f")
        layout.addRow(rec_label, self._hotkey)

        rec_hint = QLabel("Hold to record, release to stop")
        rec_hint.setStyleSheet(hint_style)
        layout.addRow("", rec_hint)

        # Context hotkey
        ctx_label = QLabel("Context Capture")
        ctx_label.setFont(label_font)
        ctx_label.setStyleSheet(label_style)
        self._context_hotkey = QLineEdit()
        self._context_hotkey.setPlaceholderText("e.g. ctrl+shift+g")
        layout.addRow(ctx_label, self._context_hotkey)

        ctx_hint = QLabel("Screenshot + clipboard capture for obsidian context")
        ctx_hint.setStyleSheet(hint_style)
        layout.addRow("", ctx_hint)

        tab.setLayout(layout)
        return tab

    # ── Browse ────────────────────────────────────────────────

    def _browse_vault(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select Obsidian Vault"
        )
        if path:
            self._vault_path.setText(path)

    # ── API key visibility toggle ─────────────────────────────

    def _toggle_api_key_visibility(self):
        if self._api_key.echoMode() == QLineEdit.Password:
            self._api_key.setEchoMode(QLineEdit.Normal)
            self._toggle_key_btn.setText("\u25CB")  # ○
        else:
            self._api_key.setEchoMode(QLineEdit.Password)
            self._toggle_key_btn.setText("\u25C9")  # ◉

    # ── Load / Save ───────────────────────────────────────────

    def _load_settings(self):
        c = self._config

        self._base_url.setText(c.llm_base_url)
        self._api_key.setText(c.llm_api_key)
        self._model.setText(c.llm_model)

        self._obsidian_enabled.setChecked(c.obsidian_enabled)
        self._vault_path.setText(c.obsidian_vault_path)
        self._subfolder.setText(c.obsidian_subfolder)
        # Set save mode combo
        idx = self._save_mode.findData(c.obsidian_save_mode)
        if idx >= 0:
            self._save_mode.setCurrentIndex(idx)
        self._attachments_subfolder.setText(c.obsidian_attachments_subfolder)

        rate = c.get("tts_rate", 150)
        self._rate_slider.setValue(rate)
        self._rate_label.setText(str(rate))

        # Set whisper combo boxes
        idx = self._whisper_model.findText(c.whisper_model_size)
        if idx >= 0:
            self._whisper_model.setCurrentIndex(idx)
        idx = self._whisper_device.findText(c.whisper_device)
        if idx >= 0:
            self._whisper_device.setCurrentIndex(idx)
        idx = self._whisper_compute.findText(c.whisper_compute_type)
        if idx >= 0:
            self._whisper_compute.setCurrentIndex(idx)

        self._hotkey.setText(c.hotkey)
        self._context_hotkey.setText(c.context_hotkey)

    def _save_settings(self):
        c = self._config

        # Track whisper changes before saving
        old_model = c.whisper_model_size
        old_device = c.whisper_device
        old_compute = c.whisper_compute_type

        # LLM
        c.set("llm_base_url", self._base_url.text().strip())
        c.set("llm_api_key", self._api_key.text().strip())
        c.set("llm_model", self._model.text().strip())

        # Obsidian
        c.set("obsidian.enabled", self._obsidian_enabled.isChecked())
        c.set("obsidian.vault_path", self._vault_path.text().strip())
        c.set("obsidian.subfolder", self._subfolder.text().strip())
        c.set(
            "obsidian.save_mode",
            self._save_mode.currentData()
        )
        c.set(
            "obsidian.attachments_subfolder",
            self._attachments_subfolder.text().strip()
        )

        # TTS
        c.set("tts_rate", self._rate_slider.value())

        # Whisper
        new_model = self._whisper_model.currentText()
        new_device = self._whisper_device.currentText()
        new_compute = self._whisper_compute.currentText()
        c.set("whisper_model", new_model)
        c.set("whisper_device", new_device)
        c.set("whisper_compute_type", new_compute)

        if old_model != new_model or old_device != new_device \
                or old_compute != new_compute:
            self._whisper_changed = True

        # Hotkeys
        c.set("hotkey", self._hotkey.text().strip())
        c.set("context_hotkey", self._context_hotkey.text().strip())

        self.accept()

    @property
    def whisper_changed(self):
        return self._whisper_changed

    # ── Centering ─────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            self.move(
                (geom.width() - self.width()) // 2,
                (geom.height() - self.height()) // 2
            )
