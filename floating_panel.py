"""Floating panel for LinguaSnap — recording bubble + result card.

Bubble (always visible, 64x64): custom-painted circle.
  Click to start/stop recording; right-click for context menu.

ResultCard (separate dialog, centred): QWebEngineView white card.
  Displays word, IPA, pronunciation, Definition/Etymology/Examples.
"""
import ctypes
import json
import math

from PyQt5.QtCore import (
    Qt, QTimer, QUrl, QPoint, QPointF, QRectF, QRect,
    pyqtSignal, QObject, pyqtSlot
)
from PyQt5.QtGui import (
    QPainter, QPainterPath, QColor, QFont, QPen, QBrush, QPixmap
)
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtWidgets import QDialog, QMenu, QApplication, QVBoxLayout, QWidget


# ── Windows MSG for nativeEvent ────────────────────────────────────
class _WinMSG(ctypes.Structure):
    _fields_ = [
        ("hwnd", ctypes.c_void_p),
        ("message", ctypes.c_uint),
        ("wParam", ctypes.c_uint64),
        ("lParam", ctypes.c_int64),
        ("time", ctypes.c_uint),
        ("pt_x", ctypes.c_int),
        ("pt_y", ctypes.c_int),
    ]


# ── Sizing ─────────────────────────────────────────────────────────
BUBBLE_SIZE = 64          # target physical size (divided by DPI ratio at runtime)
CARD_W = 420
CARD_H = 620

# ── Bubble colours (moonlight palette) ─────────────────────────────
BODY_COLOR     = QColor(235, 228, 220, 230)   # warm off-white, semi-transparent
BODY_EDGE      = QColor(255, 255, 255, 120)    # soft glass edge
BODY_IDLE      = QColor(225, 218, 210, 220)    # slightly darker when idle
TEXT_PRIMARY   = QColor(80, 70, 60)             # warm dark for icons
ACCENT         = QColor(180, 160, 140)          # warm accent
RECORDING_BG   = QColor(220, 100, 80, 230)     # warm red pulse
PROCESSING_BG  = QColor(200, 170, 130, 230)    # warm amber spin

# ── Result-card HTML ────────────────────────────────────────────────
PAGE_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<script src="qrc:///qtwebchannel/qwebchannel.js"></script>
<style>
  :root {
    --accent:        #185FA5;
    --accent-light:  #E6F1FB;
    --accent-border: #B5D4F4;
    --text-primary:  #1a1a1a;
    --text-secondary:#666;
    --text-muted:    #999;
    --border:        #e5e5e5;
    --bg-card:       #f5f5f7;
    --bg-white:      #ffffff;
    --obsidian:      #6C4FB5;
    --obsidian-bg:   #F0EBFD;
    --radius:        12px;
    --radius-sm:     8px;
    --radius-xs:     4px;
    --font:          -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
  }
  * { margin:0; padding:0; box-sizing:border-box; }
  html, body {
    width: 100%; height: 100%; margin: 0; padding: 0;
  }
  body {
    font-family: var(--font);
    background: var(--bg-white);
    color: var(--text-primary);
    overflow: hidden;
  }
  .card {
    width: 100%; height: 100%;
    display: flex; flex-direction: column;
    border: none;
    background: var(--bg-white);
  }
  :focus { outline: none; }
  button:focus { outline: none; }

  /* ── Title bar ───────────────────── */
  .titlebar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 16px; flex-shrink: 0;
  }
  .titlebar-left { display: flex; align-items: center; gap: 8px; }
  .brand {
    font-size: 12pt; color: var(--text-muted);
    display: flex; align-items: center; gap: 8px;
  }
  .brand-icon {
    width: 22px; height: 22px;
    background: var(--accent); border-radius: 5px;
    display: flex; align-items: center; justify-content: center;
    color: #fff; font-size: 10pt; font-weight: 700;
  }
  .close-btn {
    width: 24px; height: 24px; border-radius: 50%;
    border: 1px solid #d0d0d0; background: #f0f0f0;
    color: #888; font-size: 11pt; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.15s; line-height: 1;
  }
  .close-btn:hover { background: #e0e0e0; color: #555; }
  .close-btn:focus { outline: none; }
  .divider { height: 0.5px; background: var(--border); flex-shrink: 0; }
  .divider-full { margin: 0 16px; }

  /* ── Word area ───────────────────── */
  .word-area {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px; flex-shrink: 0; min-height: 70px;
  }
  .word-info { display: flex; flex-direction: column; gap: 4px; }
  .word-text { font-size: 22pt; font-weight: 500; color: var(--text-primary); }
  .word-ipa { font-size: 14pt; color: var(--text-secondary); }
  .speak-btn {
    width: 44px; height: 44px; border-radius: 50%;
    border: 1.5px solid var(--accent-border);
    background: var(--accent-light); cursor: pointer; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    transition: background 0.15s;
  }
  .speak-btn svg { width: 20px; height: 20px; }
  .speak-btn:hover { background: #daeafa; }
  .speak-btn:focus { outline: none; }

  /* ── Content area ────────────────── */
  .content {
    flex: 1; overflow-y: auto; padding: 6px 16px 10px;
    min-height: 0;
  }
  .content::-webkit-scrollbar { width: 4px; }
  .content::-webkit-scrollbar-thumb { background: #d0d0d0; border-radius: 2px; }
  .content::-webkit-scrollbar-track { background: transparent; }

  .section { margin-bottom: 14px; }
  .section-title {
    font-size: 10pt; font-weight: 600; color: var(--text-muted);
    letter-spacing: 0.6px; margin-bottom: 6px;
  }
  .definition-card {
    background: var(--bg-card); border-radius: var(--radius-sm);
    padding: 12px 16px; line-height: 1.6;
  }
  .pos-badge {
    display: inline-block;
    background: var(--accent-light); color: var(--accent);
    font-size: 11pt; font-weight: 600;
    padding: 3px 10px; border-radius: var(--radius-xs);
    margin-right: 8px;
  }
  .definition-text { font-size: 15pt; color: var(--text-primary); }
  .etymology-text {
    font-size: 13pt; color: var(--text-secondary); line-height: 1.6;
  }
  .etymology-text b { color: var(--text-primary); font-weight: 600; }
  .example-item {
    display: flex; align-items: baseline; gap: 10px;
    margin-bottom: 4px; font-size: 14pt; color: var(--text-primary);
    line-height: 1.6;
  }
  .example-num {
    min-width: 22px; height: 22px; border-radius: 50%;
    background: var(--accent); color: #fff;
    font-size: 10pt; font-weight: 600; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
  }

  /* ── Note splitter ──────────────── */
  .note-splitter {
    display: flex; align-items: center; gap: 6px;
    height: 32px; padding: 0 16px;
    background: #F5F5F5; flex-shrink: 0;
    font-size: 10pt; font-weight: 500; color: var(--text-muted);
  }
  .note-splitter svg { width: 14px; height: 14px; }

  /* ── Note toolbar ───────────────── */
  .note-toolbar {
    display: flex; align-items: center; gap: 6px;
    padding: 14px 16px 8px; flex-shrink: 0;
  }
  .note-toolbar button {
    width: 28px; height: 28px; border-radius: 6px;
    border: 0.5px solid var(--border); background: #fff;
    cursor: pointer; font-size: 10pt; color: var(--text-secondary);
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
  }
  .note-toolbar button:hover { background: #f5f5f5; }
  .note-toolbar button.active { background: #e8e8e8; color: #333; }
  .note-toolbar button svg { width: 14px; height: 14px; }
  .note-toolbar .tb-divider {
    width: 0.5px; height: 18px; background: var(--border); margin: 0 6px;
  }
  .tb-hint {
    flex: 1; text-align: right; font-size: 10pt; color: #bbb;
  }

  /* ── Note editor ────────────────── */
  .note-editor-wrap {
    padding: 0 16px;
    display: flex; flex: 1; min-height: 0;
  }
  .note-editor {
    flex: 1; overflow-y: auto;
    background: #F5F5F5; border: 0.5px solid var(--border);
    border-radius: 8px; padding: 9px 12px;
    font-family: var(--font); font-size: 12pt;
    color: var(--text-primary); line-height: 1.6;
    resize: none; outline: none;
  }
  .note-editor:empty::before {
    content: "Add your own note, context, or memory hook\u2026";
    color: #bbb;
  }
  .note-editor::-webkit-scrollbar { width: 3px; }
  .note-editor::-webkit-scrollbar-thumb { background: #d0d0d0; border-radius: 2px; }

  /* ── Preview images ─────────────── */
  .preview-row {
    display: flex; gap: 6px; padding: 4px 16px; flex-shrink: 0;
    flex-wrap: wrap;
  }
  .preview-row:empty { display: none; }
  .preview-thumb {
    width: 48px; height: 48px; border-radius: 4px; object-fit: cover;
    border: 0.5px solid var(--border); position: relative;
  }
  .preview-remove {
    position: absolute; top: -4px; right: -4px;
    width: 16px; height: 16px; border-radius: 50%;
    background: #e0e0e0; border: none; cursor: pointer;
    font-size: 10px; line-height: 16px; color: #666;
  }

  /* ── Bottom bar ──────────────────── */
  .bottombar {
    display: flex; align-items: center; justify-content: space-between;
    padding: 10px 16px; flex-shrink: 0;
  }
  .status-text { font-size: 10pt; color: var(--text-muted); }
  .btn-dismiss {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 16px; border-radius: 20px;
    border: 0.5px solid #ccc; background: transparent;
    color: #888; font-size: 11pt; font-family: var(--font);
    cursor: pointer; transition: background 0.15s;
  }
  .btn-dismiss:hover { background: #f5f5f5; }
  .btn-save {
    display: flex; align-items: center; gap: 6px;
    padding: 6px 18px; border-radius: 20px;
    border: none; background: var(--obsidian);
    color: #fff; font-size: 11pt; font-family: var(--font);
    cursor: pointer; transition: background 0.15s;
  }
  .btn-save:hover { background: #5a3da0; }
  .btn-save svg, .btn-dismiss svg { width: 14px; height: 14px; }

  /* ── Context menu ────────────────── */
  .ctx-menu {
    position: fixed; display: none;
    background: #fff; border: 1px solid #e0e0e0; border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.12);
    min-width: 170px; z-index: 9999; padding: 4px 0;
  }
  .ctx-menu.visible { display: block; }
  .ctx-item {
    padding: 8px 16px; font-size: 12pt; cursor: pointer;
    color: var(--text-primary); font-family: var(--font);
  }
  .ctx-item:hover { background: #f0f0f5; }
  .ctx-item.disabled { color: #ccc; cursor: default; }
  .ctx-item.disabled:hover { background: transparent; }
  .ctx-divider { height: 0.5px; background: #e0e0e0; margin: 2px 0; }
</style>
</head>
<body>
<div class="card">
  <!-- Title bar -->
  <div class="titlebar">
    <div class="titlebar-left">
      <span class="brand">
        <span class="brand-icon">LS</span> LinguaSnap
      </span>
    </div>
  </div>
  <div class="divider"></div>

  <!-- Word area -->
  <div id="wordArea" class="word-area" style="display:none">
    <div class="word-info">
      <div id="wordText" class="word-text"></div>
      <div id="wordIpa" class="word-ipa"></div>
    </div>
    <button class="speak-btn" onclick="speakWord()" title="Pronounce">
      <svg viewBox="0 0 24 24" fill="none" stroke="#185FA5" stroke-width="2">
        <path d="M11 5L6 9H2v6h4l5 4V5z"/>
        <path d="M19.07 4.93a10 10 0 010 14.14M15.54 8.46a5 5 0 010 7.07"/>
      </svg>
    </button>
  </div>
  <div id="wordDivider" class="divider divider-full" style="display:none"></div>

  <!-- Content scroll area -->
  <div id="contentArea" class="content">
    <div id="emptyState" style="padding:50px 0;text-align:center;color:#bbb;font-size:14pt;">
      Click the bubble to look up a word
    </div>
  </div>

  <!-- Note section -->
  <div class="note-splitter">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 013 3L7 19l-4 1 1-4L16.5 3.5z"/>
    </svg>
    My note
  </div>

  <div class="note-toolbar">
    <button onclick="execCmd('bold')" title="Bold"><b>B</b></button>
    <button onclick="execCmd('italic')" title="Italic"><i>I</i></button>
    <button onclick="execCmd('hilite')" title="Highlight" id="btnHilite">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
        <line x1="2" y1="13" x2="14" y2="13" stroke-width="2.5"/>
        <polygon points="5,13 7,3 10,3 7,13"/>
      </svg>
    </button>
    <span class="tb-divider"></span>
    <button onclick="bridge.capture_screenshot()" title="Screenshot capture">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round">
        <polyline points="3,1 1,1 1,3"/>
        <polyline points="13,1 15,1 15,3"/>
        <polyline points="15,13 15,15 13,15"/>
        <polyline points="3,15 1,15 1,13"/>
      </svg>
    </button>
    <button onclick="document.getElementById('imgInput').click()" title="Upload image">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round" stroke-linejoin="round">
        <rect x="1.5" y="4.5" width="10" height="10" rx="1.5"/>
        <circle cx="4.5" cy="7.5" r="1"/>
        <path d="M2.5 13l2.5-2.5 1.5 1.5 2-2 3 3"/>
        <line x1="13" y1="2" x2="13" y2="6"/>
        <polyline points="11,4 13,2 15,4"/>
      </svg>
    </button>
    <span class="tb-hint">Cmd+V to paste</span>
  </div>

  <div class="note-editor-wrap">
    <div id="noteEditor" class="note-editor" contenteditable="true"
         placeholder="Add your own note, context, or memory hook\u2026"></div>
  </div>

  <div id="previewRow" class="preview-row"></div>

  <div class="divider"></div>

  <!-- Bottom bar -->
  <div class="bottombar">
    <span id="statusText" class="status-text">Looked up</span>
    <div style="display:flex;gap:12px;">
      <button class="btn-dismiss" onclick="dismissCard()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
        </svg>
        Dismiss
      </button>
      <button class="btn-save" onclick="saveNote()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M6 2L3 6v14a2 2 0 002 2h14a2 2 0 002-2V6l-3-4z"/>
          <line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 01-8 0"/>
        </svg>
        Save to Obsidian
      </button>
    </div>
  </div>
</div>

<!-- Context menu -->
<div id="ctxMenu" class="ctx-menu">
  <div class="ctx-item" id="ctxRead" onclick="ctxAction('read')">Read aloud</div>
  <div class="ctx-item" id="ctxTranslate" onclick="ctxAction('translate')">Translate to Chinese</div>
  <div class="ctx-divider"></div>
  <div class="ctx-item" onclick="hideCtxMenu()">Cancel</div>
</div>

<!-- Hidden file input -->
<input type="file" id="imgInput" accept="image/png,image/jpeg" style="display:none" onchange="onFileSelect(event)" />

<script>
var _selectedText = '';
var _currentWord = '';
var _images = [];  // array of {name, dataUrl}

var bridge = null;
new QWebChannel(qt.webChannelTransport, function(channel) {
  bridge = channel.objects.bridge;
});

/* ── Context menu ──────────────────── */
document.getElementById('contentArea').addEventListener('contextmenu', function(e) {
  var sel = window.getSelection().toString().trim();
  _selectedText = sel;
  var menu = document.getElementById('ctxMenu');
  var readItem = document.getElementById('ctxRead');
  var transItem = document.getElementById('ctxTranslate');
  if (sel) { readItem.classList.remove('disabled'); transItem.classList.remove('disabled'); }
  else { readItem.classList.add('disabled'); transItem.classList.add('disabled'); }
  menu.style.left = e.pageX + 'px';
  menu.style.top = e.pageY + 'px';
  menu.classList.add('visible');
  e.preventDefault();
});

document.addEventListener('click', function(e) {
  if (!e.target.closest('#ctxMenu')) hideCtxMenu();
});

function hideCtxMenu() { document.getElementById('ctxMenu').classList.remove('visible'); }

function ctxAction(action) {
  if (!_selectedText) return;
  if (action === 'read') bridge.read_text(_selectedText);
  else if (action === 'translate') bridge.translate_text(_selectedText);
  hideCtxMenu();
}

/* ── Speak word ────────────────────── */
function speakWord() {
  if (!_currentWord) return;
  // Use Python TTS bridge (pyttsx3/SAPI5) – more reliable than
  // Web Speech API which breaks after the first utterance in QWebEngine.
  if (bridge) {
    bridge.read_text(_currentWord);
    return;
  }
  // Fallback: browser Speech Synthesis API
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
    var u = new SpeechSynthesisUtterance(_currentWord);
    u.lang = 'en-US'; u.rate = 0.9;
    window.speechSynthesis.speak(u);
  }
}

/* ── Toolbar actions (toggle-style, like Word) ── */
var HILITE_COLOR = '#FFEB3B';

function execCmd(cmd) {
  var ed = document.getElementById('noteEditor');
  ed.focus();
  if (cmd === 'hilite') {
    var current = document.queryCommandValue('backColor');
    var isHilited = current === 'rgb(255, 235, 59)' || current === '#ffeb3b' || current === HILITE_COLOR;
    document.execCommand('backColor', false, isHilited ? 'rgba(0,0,0,0)' : HILITE_COLOR);
  } else {
    document.execCommand(cmd, false, null);
  }
  updateToolbarState();
}

function updateToolbarState() {
  var btns = {
    bold: document.querySelector('.note-toolbar button[title="Bold"]'),
    italic: document.querySelector('.note-toolbar button[title="Italic"]'),
    hilite: document.getElementById('btnHilite')
  };
  if (btns.bold) btns.bold.classList.toggle('active', document.queryCommandState('bold'));
  if (btns.italic) btns.italic.classList.toggle('active', document.queryCommandState('italic'));
  if (btns.hilite) {
    // Only match our specific highlight yellow, not the editor's #F5F5F5 bg
    var c = document.queryCommandValue('backColor');
    var on = c === 'rgb(255, 235, 59)' || c === '#ffeb3b' || c === HILITE_COLOR;
    btns.hilite.classList.toggle('active', on);
  }
}

document.addEventListener('selectionchange', function() {
  var ed = document.getElementById('noteEditor');
  var sel = document.getSelection();
  if (sel.anchorNode && ed.contains(sel.anchorNode)) {
    updateToolbarState();
  }
});

/* ── Receive screenshot from Python ── */
function addImage(dataUrl, name) {
  _images.push({name: name || 'screenshot.png', dataUrl: dataUrl});
  renderPreviews();
}

/* ── Image handling ────────────────── */
function onFileSelect(e) {
  var files = e.target.files;
  for (var i = 0; i < files.length; i++) processImageFile(files[i]);
  e.target.value = '';
}

/* ── Paste handler ─────────────────── */
document.addEventListener('paste', function(e) {
  var ed = document.getElementById('noteEditor');
  if (document.activeElement === ed || ed.contains(document.activeElement)) return; // let editor handle text
  var items = e.clipboardData.items;
  for (var i = 0; i < items.length; i++) {
    if (items[i].type.indexOf('image') !== -1) {
      e.preventDefault();
      processImageFile(items[i].getAsFile());
      return;
    }
  }
});

function processImageFile(file) {
  if (!file) return;
  var reader = new FileReader();
  reader.onload = function(ev) {
    _images.push({name: file.name || 'screenshot.png', dataUrl: ev.target.result});
    renderPreviews();
  };
  reader.readAsDataURL(file);
}

function renderPreviews() {
  var row = document.getElementById('previewRow');
  row.innerHTML = '';
  _images.forEach(function(img, idx) {
    var wrap = document.createElement('span');
    wrap.style.position = 'relative';
    var thumb = document.createElement('img');
    thumb.className = 'preview-thumb';
    thumb.src = img.dataUrl;
    var btn = document.createElement('button');
    btn.className = 'preview-remove';
    btn.textContent = '\u2715';
    btn.onclick = function() { _images.splice(idx, 1); renderPreviews(); };
    wrap.appendChild(thumb);
    wrap.appendChild(btn);
    row.appendChild(wrap);
  });
}

/* ── Save / Dismiss ────────────────── */
function saveNote() {
  var noteHtml = document.getElementById('noteEditor').innerHTML;
  bridge.save_note(_currentWord, noteHtml, JSON.stringify(_images.map(function(i){ return {name:i.name, dataUrl:i.dataUrl}; })));
}

function dismissCard() {
  bridge.dismiss_note();
}

/* ── Populate result ───────────────── */
function showResult(word, ipa, pos, definition, etymology, examples, rawExplanation) {
  _currentWord = word;
  document.getElementById('emptyState').style.display = 'none';
  document.getElementById('wordArea').style.display = 'flex';
  document.getElementById('wordDivider').style.display = 'block';
  document.getElementById('wordText').textContent = word;
  document.getElementById('wordIpa').textContent = ipa || '';

  var html = '';
  if (definition) {
    html += '<div class="section"><div class="section-title">DEFINITION</div>';
    html += '<div class="definition-card">';
    if (pos) html += '<span class="pos-badge">' + escapeHtml(pos) + '</span>';
    html += '<span class="definition-text">' + renderInlineMd(definition) + '</span>';
    html += '</div></div>';
  }
  if (etymology) {
    html += '<div class="section"><div class="section-title">ETYMOLOGY</div>';
    html += '<div class="etymology-text">' + renderInlineMd(etymology) + '</div></div>';
  }
  if (examples && examples.length > 0) {
    html += '<div class="section"><div class="section-title">EXAMPLES</div>';
    for (var i = 0; i < examples.length; i++) {
      html += '<div class="example-item"><span class="example-num">' + (i+1) + '</span>';
      html += '<span>' + escapeHtml(examples[i]) + '</span></div>';
    }
    html += '</div>';
  }
  // Fallback: if no structured fields parsed, show raw LLM explanation
  if (!html && rawExplanation) {
    html += '<div class="section"><div class="section-title">EXPLANATION</div>';
    html += '<div class="definition-text" style="white-space:pre-wrap">' + renderInlineMd(rawExplanation) + '</div>';
    html += '</div>';
  }
  document.getElementById('contentArea').innerHTML = html;

  // Reset note state
  document.getElementById('noteEditor').innerHTML = '';
  _images = [];
  renderPreviews();
}

function clearResult() {
  _currentWord = '';
  document.getElementById('emptyState').style.display = 'block';
  document.getElementById('wordArea').style.display = 'none';
  document.getElementById('wordDivider').style.display = 'none';
  document.getElementById('contentArea').innerHTML =
    '<div id="emptyState" style="padding:50px 0;text-align:center;color:#bbb;font-size:14pt;">Click the bubble to look up a word</div>';
  document.getElementById('noteEditor').innerHTML = '';
  _images = [];
  renderPreviews();
}

function setStatus(text) { document.getElementById('statusText').textContent = text; }

function escapeHtml(str) {
  return str.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function renderInlineMd(str) {
  // Escape HTML first (safety), then convert markdown **bold** and *italic* to tags.
  var safe = escapeHtml(str);
  safe = safe.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
  safe = safe.replace(/__(.+?)__/g, '<b>$1</b>');
  safe = safe.replace(/\*(.+?)\*/g, '<em>$1</em>');
  return safe;
}
</script>
</body>
</html>"""

# ── Bridge object (exposed to JavaScript) ───────────────────────────

class _Bridge(QObject):
    """QWebChannel bridge — JS calls these slots, they emit signals.

    The Python method name IS the name exposed to JavaScript.
    Signal names use _sig suffix to avoid colliding with slot names.
    """

    close_panel_sig = pyqtSignal()
    read_text_sig = pyqtSignal(str)
    translate_text_sig = pyqtSignal(str)
    save_note_sig = pyqtSignal(str, str, str)   # word, note_html, images_json
    dismiss_note_sig = pyqtSignal()
    capture_screenshot_sig = pyqtSignal()

    @pyqtSlot()
    def close_panel(self):
        self.close_panel_sig.emit()

    @pyqtSlot(str)
    def read_text(self, text):
        self.read_text_sig.emit(text)

    @pyqtSlot(str)
    def translate_text(self, text):
        self.translate_text_sig.emit(text)

    @pyqtSlot(str, str, str)
    def save_note(self, word, note_html, images_json):
        self.save_note_sig.emit(word, note_html, images_json)

    @pyqtSlot()
    def dismiss_note(self):
        self.dismiss_note_sig.emit()

    @pyqtSlot()
    def capture_screenshot(self):
        self.capture_screenshot_sig.emit()


# ── FloatingPanel (bubble only, always visible) ────────────────────

class FloatingPanel(QDialog):
    """Organic ink-sprite bubble — always visible.

    Idle: slightly irregular warm blob with subtle breathing animation.
    Hover: expands into oval, two dot 'eyes' appear, frosted-glass action
    bubbles (mic + keyboard) emerge on each side.
    Click mic bubble or body → start/stop recording.
    Click keyboard bubble → type a word directly.

    States: idle → recording → processing → idle
    """

    record_start = pyqtSignal()
    record_stop = pyqtSignal()
    panel_closed = pyqtSignal()
    type_input_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMouseTracking(True)

        self._state = "idle"
        screen = QApplication.primaryScreen()
        ratio = screen.devicePixelRatio() if screen else 1.0
        self._sz = max(16, int(BUBBLE_SIZE / ratio))
        # Widget is wider/taller to accommodate hover expansion + action bubbles
        self._full_w = self._sz * 3
        self._full_h = int(self._sz * 2.5)
        self.setFixedSize(self._full_w, self._full_h)

        # Hover state
        self._hover = False
        self._hover_progress = 0.0     # 0 → 1, animated
        self._hover_timer = QTimer(self)
        self._hover_timer.timeout.connect(self._on_hover_tick)

        # Breathing animation (idle only)
        self._breath_phase = 0.0
        self._breath_timer = QTimer(self)
        self._breath_timer.timeout.connect(self._on_breath_tick)
        self._breath_timer.start(50)

        # Drag support
        self._drag_start = None
        self._drag_moved = False

        # Action bubbles: positions relative to center
        self._bubble_mic = QRectF()
        self._bubble_kb = QRectF()

        # Recording pulse animation
        self._pulse_value = 0.0
        self._pulse_timer = QTimer(self)
        self._pulse_timer.timeout.connect(self._on_pulse_tick)

        # Processing spinner
        self._spin_angle = 0
        self._spin_timer = QTimer(self)
        self._spin_timer.timeout.connect(self._on_spin_tick)

        # Topmost refresh timer
        self._topmost_timer = QTimer(self)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start(2000)

        # Position bubble at right side
        self._position_bubble()

    # ── Windows native events ──────────────────────────────────

    def nativeEvent(self, eventType, message):
        if eventType == "windows_generic_MSG":
            try:
                msg = ctypes.cast(
                    ctypes.c_void_p(int(message)),
                    ctypes.POINTER(_WinMSG)
                ).contents
                if msg.message == 0x0084:  # WM_NCHITTEST
                    return True, 1  # HTCLIENT — accept clicks on entire widget
                if msg.message == 0x0021:
                    return True, 1  # MA_ACTIVATE
            except Exception:
                pass
        return False, 0

    def showEvent(self, event):
        super().showEvent(event)
        try:
            hwnd = int(self.winId())
            GWL_EXSTYLE = -20
            WS_EX_TOOLWINDOW = 0x00000080
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_TOPMOST = 0x00000008
            ex_style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ex_style &= ~WS_EX_NOACTIVATE
            ex_style |= WS_EX_TOOLWINDOW | WS_EX_TOPMOST
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex_style)
        except Exception:
            pass

    # ── Positioning ────────────────────────────────────────────

    def _position_bubble(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geom = screen.availableGeometry()
        # Position so the centre body is at the same spot as the old 64×64 widget
        cx = geom.right() - self._sz // 2 - 20
        cy = geom.height() // 2
        self.move(cx - self._full_w // 2, cy - self._full_h // 2)

    def _reassert_topmost(self):
        if self.isVisible():
            self.raise_()
            try:
                hwnd = int(self.winId())
                ctypes.windll.user32.SetWindowPos(
                    hwnd, -1, 0, 0, 0, 0, 0x0002 | 0x0001
                )
            except Exception:
                pass

    # ── State machine (called from main.py) ────────────────────

    def set_idle(self):
        self._state = "idle"
        self._pulse_timer.stop()
        self._spin_timer.stop()
        self.update()

    def set_recording(self):
        self._state = "recording"
        self._pulse_value = 0.0
        self._pulse_timer.start(60)
        self.update()

    def set_processing(self):
        self._state = "processing"
        self._pulse_timer.stop()
        self._spin_angle = 0
        self._spin_timer.start(40)
        self.update()

    # ── Hover / enter / leave ──────────────────────────────────

    def enterEvent(self, event):
        self._hover = True
        if not self._hover_timer.isActive():
            self._hover_timer.start(16)
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        if not self._hover_timer.isActive():
            self._hover_timer.start(16)
        super().leaveEvent(event)

    def _on_hover_tick(self):
        """Animate _hover_progress toward target (1.0 when hovered, 0.0 when not)."""
        target = 1.0 if self._hover else 0.0
        step = 0.12
        prev = self._hover_progress
        if abs(self._hover_progress - target) < 0.005:
            self._hover_progress = target
            self._hover_timer.stop()
        elif self._hover_progress < target:
            self._hover_progress = min(target, self._hover_progress + step)
        else:
            self._hover_progress = max(target, self._hover_progress - step)
        if self._hover_progress != prev:
            self.update()

    # ── Breathing animation (idle) ─────────────────────────────

    def _on_breath_tick(self):
        if self._state != "idle" or self._hover_progress > 0.1:
            return
        self._breath_phase += 0.04
        if self._breath_phase > 2 * math.pi:
            self._breath_phase -= 2 * math.pi
        self.update()

    # ── Recording / processing animation ───────────────────────

    def _on_pulse_tick(self):
        self._pulse_value += 0.08
        if self._pulse_value > 2 * math.pi:
            self._pulse_value -= 2 * math.pi
        self.update()

    def _on_spin_tick(self):
        self._spin_angle = (self._spin_angle + 12) % 360
        self.update()

    # ── Painting ───────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        self._paint_bubble(painter)

    def _paint_bubble(self, painter):
        """Paint organic ink-sprite body, eyes, and action bubbles."""
        cx = self._full_w // 2
        cy = self._full_h // 2
        r = self._sz // 2 - 1
        h = self._hover_progress

        # ── Colours per state ──────────────────────────────────
        if self._state == "recording":
            alpha = int(180 + 60 * math.sin(self._pulse_value))
            alpha = max(0, min(255, alpha))
            fill_color = QColor(220, 100, 80, alpha)
            edge_color = QColor(255, 180, 160, 80)
        elif self._state == "processing":
            fill_color = PROCESSING_BG
            edge_color = QColor(220, 200, 160, 100)
        else:
            fill_color = BODY_IDLE
            edge_color = BODY_EDGE

        # ── Main body: organic blob ────────────────────────────
        body_path = self._build_organic_body(cx, cy, r, h)
        painter.setBrush(fill_color)
        painter.setPen(QPen(edge_color, 1.5))
        painter.drawPath(body_path)

        # ── Inner content ─────────────────────────────────────
        if self._state == "recording":
            self._draw_recording_wave(painter, cx, cy, r)
        elif self._state == "processing":
            self._draw_spinner(painter, cx, cy, r)

        # ── Eyes — always visible, looking down thoughtfully ──
        eye_alpha = 160 if h < 0.15 else int(160 + 40 * min(1.0, (h - 0.15) / 0.3))
        self._draw_eyes(painter, cx, cy, r, h, eye_alpha)

        # ── Action bubbles (mic + keyboard), hover only ───────
        if h > 0.25:
            bubble_alpha = min(1.0, (h - 0.25) / 0.4)
            self._draw_action_bubbles(painter, cx, cy, r, h, bubble_alpha)

    # ── Organic body shape ─────────────────────────────────────

    def _build_organic_body(self, cx, cy, r, hover):
        """Return a QPainterPath for the organic, slightly irregular blob.

        When hovered, the body stretches horizontally and two smaller
        aux bumps emerge on each side (the action-bubble attachment points).
        """
        path = QPainterPath()
        breath = self._breath_phase

        # Subtle expansion on hover (bubbles sit in upper-left, not on sides)
        stretch_x = 1.0 + hover * 0.10
        stretch_y = 1.0 + hover * 0.06

        n = 12  # control points around the blob
        pts = []
        for i in range(n):
            a = 2 * math.pi * i / n
            # Subtle irregularity from breath phase
            wave = math.sin(a * 3 + breath) * 0.04 + math.sin(a * 5 + breath * 1.3) * 0.02
            rr = r * (1 + wave)
            px = cx + rr * stretch_x * math.cos(a)
            py = cy + rr * stretch_y * math.sin(a)
            pts.append((px, py))

        # Build smooth closed path with cubic beziers
        path.moveTo(*pts[0])
        for i in range(n):
            x1, y1 = pts[i]
            x2, y2 = pts[(i + 1) % n]
            # Control points ~0.45 of the way through each segment
            cp1x = x1 + (x2 - x1) * 0.45
            cp1y = y1 + (y2 - y1) * 0.45
            cp2x = x1 + (x2 - x1) * 0.55
            cp2y = y1 + (y2 - y1) * 0.55
            path.cubicTo(cp1x, cp1y, cp2x, cp2y, x2, y2)
        path.closeSubpath()
        return path

    # ── Eyes ───────────────────────────────────────────────────

    def _draw_eyes(self, painter, cx, cy, r, hover, alpha):
        """Two dot eyes — positioned low for a 'looking down, thinking' expression."""
        eye_color = QColor(
            TEXT_PRIMARY.red(), TEXT_PRIMARY.green(),
            TEXT_PRIMARY.blue(), alpha
        )
        painter.setBrush(eye_color)
        painter.setPen(Qt.NoPen)
        eye_r = max(2.0, r * 0.10)
        # Position eyes near or slightly below centre — thoughtful downward gaze
        eye_y = cy + r * 0.05
        eye_spread = r * 0.28
        painter.drawEllipse(QPointF(cx - eye_spread, eye_y), eye_r, eye_r)
        painter.drawEllipse(QPointF(cx + eye_spread, eye_y), eye_r, eye_r)

    # ── Action bubbles (frosted glass) ─────────────────────────

    def _draw_action_bubbles(self, painter, cx, cy, r, hover, alpha):
        """Draw a single frosted-glass keyboard bubble above the body."""
        bubble_r = r * 0.72
        # Keyboard: above the body, clear of the sprite
        kb_cx = cx
        kb_cy = cy - r - bubble_r * 0.85

        # Store rects for hit testing (mic bubble cleared)
        self._bubble_mic = QRectF()
        self._bubble_kb = QRectF(
            kb_cx - bubble_r, kb_cy - bubble_r,
            bubble_r * 2, bubble_r * 2
        )

        # Frosted glass fill
        glass_color = QColor(255, 255, 255, int(160 * alpha))
        glass_edge = QColor(255, 255, 255, int(100 * alpha))

        painter.setBrush(glass_color)
        painter.setPen(QPen(glass_edge, 1.0))
        painter.drawEllipse(QPointF(kb_cx, kb_cy), bubble_r, bubble_r)

        icon_color = QColor(
            TEXT_PRIMARY.red(), TEXT_PRIMARY.green(),
            TEXT_PRIMARY.blue(), int(200 * alpha)
        )
        self._draw_kb_icon(painter, kb_cx, kb_cy, bubble_r, icon_color)

    def _draw_kb_icon(self, painter, cx, cy, r, color):
        """Small keyboard icon inside an action bubble."""
        scale = r / 18.0
        pen = QPen(color, 1.2 * scale)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        kw = 9 * scale
        kh = 6 * scale
        left = cx - kw / 2
        top = cy - kh / 2
        # keyboard body
        painter.drawRoundedRect(
            QRectF(left, top, kw, kh), 1.5 * scale, 1.5 * scale
        )
        # keys
        key_w = 1.8 * scale
        gap = 0.6 * scale
        for row_i, row_y in enumerate([top + 1.5 * scale, top + 3.5 * scale]):
            painter.drawLine(
                QPointF(left + 1.5 * scale, row_y),
                QPointF(left + kw - 1.5 * scale, row_y)
            )
            for ki in range(4):
                kx = left + 2 * scale + ki * (key_w + gap)
                painter.drawLine(
                    QPointF(kx, row_y),
                    QPointF(kx + key_w, row_y)
                )

    # ── State icons (inside main body) ─────────────────────────

    # ── Recording: animated ripple "mouth" ─────────────────────

    def _draw_recording_wave(self, painter, cx, cy, r):
        """Animated concentric ripples like a cute mouth — below the eyes."""
        scale = r / 18.0
        pulse = self._pulse_value
        # Mouth sits below the eyes (~ cy + r*0.3)
        mouth_y = cy + r * 0.30

        # Expanding concentric arcs (mouth ripples)
        for i in range(3):
            phase = pulse + i * 1.2
            alpha = int(160 * (0.5 + 0.5 * math.sin(phase)))
            alpha = max(30, min(220, alpha))
            ring_r = (5 + i * 4 + 3 * math.sin(phase * 0.7)) * scale
            ring_pen = QPen(QColor(255, 255, 255, alpha), 1.4 * scale)
            ring_pen.setCapStyle(Qt.RoundCap)
            painter.setPen(ring_pen)
            painter.setBrush(Qt.NoBrush)
            # Arc below eyes, like a mouth opening
            painter.drawArc(
                QRectF(cx - ring_r, mouth_y - ring_r * 0.5, ring_r * 2, ring_r),
                0, 180 * 16
            )

    def _draw_spinner(self, painter, cx, cy, r):
        pen = QPen(ACCENT, max(2.0, 2.5 * r / 18.0))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        sr = r * 0.55
        start = self._spin_angle * 16
        painter.drawArc(
            QRectF(cx - sr, cy - sr, sr * 2, sr * 2), start, 90 * 16
        )

    # ── Mouse interaction ──────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            pt = event.pos()
            # Check action bubbles first (only when hovered enough)
            if self._hover_progress > 0.4:
                if self._bubble_mic.contains(pt):
                    self._on_bubble_click()
                    return
                if self._bubble_kb.contains(pt):
                    self.type_input_requested.emit()
                    return
            # Check main body
            if self._hit_body(pt):
                self._drag_start = event.globalPos()
                self._drag_moved = False
        elif event.button() == Qt.RightButton:
            self._show_context_menu(event.globalPos())

    def mouseMoveEvent(self, event):
        if self._drag_start is None:
            return
        delta = event.globalPos() - self._drag_start
        if abs(delta.x()) > 3 or abs(delta.y()) > 3:
            self._drag_moved = True
        if self._drag_moved:
            self.move(self.pos() + delta)
            self._drag_start = event.globalPos()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._drag_start is not None and not self._drag_moved:
            self._on_bubble_click()
        self._drag_start = None

    def _on_bubble_click(self):
        if self._state == "idle":
            self.set_recording()
            self.record_start.emit()
        elif self._state == "recording":
            self.set_processing()
            self.record_stop.emit()
        # processing — ignore clicks

    def _hit_body(self, pt):
        """Check if pt (in widget coords) is inside the main organic body."""
        cx = self._full_w // 2
        cy = self._full_h // 2
        r = self._sz // 2 - 1
        h = self._hover_progress
        stretch_x = 1.0 + h * 0.10
        dx = (pt.x() - cx) / stretch_x
        dy = pt.y() - cy
        return (dx * dx + dy * dy) <= (r * r * 1.15)

    def _hit_test(self, pt):
        """Check if a point (in widget coords) is over any painted area.

        Used by nativeEvent to decide HTCLIENT vs HTTRANSPARENT.
        """
        # Main body
        if self._hit_body(pt):
            return True
        # Action bubbles (only when visible)
        if self._hover_progress > 0.25:
            if self._bubble_mic.contains(pt) or self._bubble_kb.contains(pt):
                return True
        return False

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1e1e28; color: #e0e0e0;
                border: 1px solid #444; padding: 4px;
            }
            QMenu::item:selected { background-color: #335577; }
        """)
        quit_action = menu.addAction("Quit LinguaSnap")
        action = menu.exec_(pos)
        if action == quit_action:
            QApplication.instance().quit()


# ── Screen Region Selector ──────────────────────────────────────────

class ScreenRegionSelector(QDialog):
    """Full-screen overlay for drag-to-select screenshot region."""

    def __init__(self):
        super().__init__(None)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setCursor(Qt.CrossCursor)

        screen = QApplication.primaryScreen()
        self._screen_geom = screen.geometry() if screen else QRect(0, 0, 1920, 1080)
        self.setGeometry(self._screen_geom)

        self._start = None
        self._end = None
        self._selecting = False
        self._captured = QPixmap()

    @property
    def captured_pixmap(self):
        return self._captured

    def paintEvent(self, event):
        painter = QPainter(self)
        # Dim overlay
        painter.setBrush(QColor(0, 0, 0, 100))
        painter.setPen(Qt.NoPen)
        painter.drawRect(self.rect())

        if self._start and self._end:
            sel = self._selection_rect()
            # Cut out selection area
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.drawRect(sel)
            # Selection border
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
            painter.setPen(QPen(QColor(24, 95, 165), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(sel)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._start = event.pos()
            self._end = event.pos()
            self._selecting = True

    def mouseMoveEvent(self, event):
        if self._selecting:
            self._end = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._selecting:
            self._selecting = False
            self._end = event.pos()
            sel = self._selection_rect()
            if sel.width() > 10 and sel.height() > 10:
                self.hide()
                screen = QApplication.primaryScreen()
                if screen:
                    self._captured = screen.grabWindow(
                        0, sel.x(), sel.y(), sel.width(), sel.height()
                    )
                self.accept()
            else:
                self.reject()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self.reject()

    def _selection_rect(self):
        if not self._start or not self._end:
            return QRect()
        return QRect(
            min(self._start.x(), self._end.x()),
            min(self._start.y(), self._end.y()),
            abs(self._end.x() - self._start.x()),
            abs(self._end.y() - self._start.y()),
        )


# ── ResultCard (standalone QWebEngineView dialog, centred) ─────────

class ResultCard(QDialog):
    """Resizable window with system borders showing AI explanation + notes.

    Appears centred on screen. Bubble stays visible independently.
    """

    read_text = pyqtSignal(str)
    translate_requested = pyqtSignal(str)
    card_closed = pyqtSignal()
    save_note = pyqtSignal(str, str, str)   # word, note_html, images_json
    dismiss_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LinguaSnap — Result")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Window)
        self.setMinimumSize(380, 400)
        self.resize(CARD_W, CARD_H)
        self.setStyleSheet("""
            QDialog {
                background-color: #ffffff;
            }
        """)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._web = QWebEngineView(self)
        self._web.setContextMenuPolicy(Qt.NoContextMenu)

        # Bridge
        self._bridge = _Bridge()
        self._channel = QWebChannel()
        self._channel.registerObject("bridge", self._bridge)
        self._web.page().setWebChannel(self._channel)
        self._web.setHtml(PAGE_HTML, QUrl("https://linguasnap.local/"))

        layout.addWidget(self._web)
        self.setLayout(layout)

        # Wire bridge signals
        self._bridge.close_panel_sig.connect(self._on_close)
        self._bridge.read_text_sig.connect(self.read_text)
        self._bridge.translate_text_sig.connect(self.translate_requested)
        self._bridge.save_note_sig.connect(self.save_note)
        self._bridge.dismiss_note_sig.connect(self._on_dismiss)
        self._bridge.capture_screenshot_sig.connect(self._on_capture_screenshot)

    def showEvent(self, event):
        """Center on screen."""
        super().showEvent(event)
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            self.move(
                (geom.width() - self.width()) // 2,
                (geom.height() - self.height()) // 2
            )

    def show_result(self, word, ipa, pos, definition, etymology, examples,
                    raw_explanation=""):
        """Populate and show the result card."""
        self._call_js("showResult", word, ipa, pos, definition, etymology,
                      examples, raw_explanation)
        self._call_js("setStatus", "Looked up: " + word)
        self.show()
        self.raise_()

    def _on_close(self):
        self.hide()
        self.card_closed.emit()

    def _on_dismiss(self):
        self.hide()
        self.dismiss_requested.emit()

    def _on_capture_screenshot(self):
        """Hide card, let user drag-select a region, pass image to JS."""
        self.hide()
        QApplication.processEvents()
        QTimer.singleShot(200, self._show_region_selector)

    def _show_region_selector(self):
        import os, base64, tempfile
        selector = ScreenRegionSelector()
        if selector.exec_() == QDialog.Accepted:
            pixmap = selector.captured_pixmap
            if not pixmap.isNull():
                tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                tmp.close()
                try:
                    pixmap.save(tmp.name, 'PNG')
                    with open(tmp.name, 'rb') as f:
                        data_url = 'data:image/png;base64,' + base64.b64encode(f.read()).decode()
                    self._call_js('addImage', data_url, 'screenshot.png')
                finally:
                    os.unlink(tmp.name)
        self.show()
        self.raise_()

    def _call_js(self, func_name, *args):
        """Call a JS function by name with JSON-serialised arguments."""
        js_args = ", ".join(json.dumps(a) for a in args)
        expr = f"{func_name}({js_args})"
        self._web.page().runJavaScript(expr)
