"""Save word notes to an Obsidian vault as markdown files.

Supports two modes:
  - "separate": one file per word lookup (default, backward compatible)
  - "journal": append all lookups to a single file per game
"""

import os
import re
import base64
from datetime import datetime


class ObsidianWriter:
    """Writes word explanation notes as .md files in an Obsidian vault."""

    def __init__(self, vault_path="", subfolder="lingua-snap",
                 include_game_name=False, game_name="",
                 save_mode="separate", attachments_subfolder="attachments"):
        self._vault_path = vault_path
        self._subfolder = subfolder
        self._include_game_name = include_game_name
        self._game_name = game_name
        self._save_mode = save_mode
        self._attachments_subfolder = attachments_subfolder

    def update_config(self, vault_path, subfolder="lingua-snap",
                      include_game_name=False, game_name="",
                      save_mode="separate", attachments_subfolder="attachments"):
        """Update Obsidian settings."""
        self._vault_path = vault_path
        self._subfolder = subfolder
        self._include_game_name = include_game_name
        self._game_name = game_name
        self._save_mode = save_mode
        self._attachments_subfolder = attachments_subfolder

    def update_game_name(self, game_name):
        """Update the current game name (for journal mode switching)."""
        self._game_name = game_name

    @property
    def enabled(self):
        return bool(self._vault_path)

    def save_word(self, word, explanation, context=None):
        """Save a word lookup, optionally with captured context.

        Args:
            word: The word or phrase that was looked up.
            explanation: The full LLM explanation text (may contain
                embedded base64 images).
            context: Optional ContextData with screenshot_path/clipboard_text.

        Returns:
            The file path if saved successfully, None otherwise.
        """
        if not self._vault_path or not word:
            return None

        output_dir = os.path.join(self._vault_path, self._subfolder)
        os.makedirs(output_dir, exist_ok=True)

        # Extract embedded base64 images, save as files, replace refs
        explanation = self._extract_images(explanation, output_dir)

        if self._save_mode == "journal":
            return self._save_journal(word, explanation, context, output_dir)
        else:
            return self._save_separate(
                word, explanation, context, output_dir
            )

    # ── Separate mode (one file per word) ──────────────────────────

    def _save_separate(self, word, explanation, context, output_dir):
        """Original behavior: one .md file per word lookup."""
        date_str = datetime.now().strftime("%Y-%m-%d")
        safe_word = self._sanitize_filename(word)
        filename = f"{safe_word}-{date_str}.md"
        filepath = os.path.join(output_dir, filename)

        content = self._build_markdown(word, explanation, date_str, context)

        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)
            return filepath
        except IOError:
            return None

    # ── Journal mode (append to game file) ─────────────────────────

    def _save_journal(self, word, explanation, context, output_dir):
        """Journal mode: append entry to {game_name}.md."""
        journal_name = (
            self._sanitize_filename(self._game_name)
            if self._game_name else "game-notes"
        )
        journal_path = os.path.join(output_dir, f"{journal_name}.md")

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")
        time_str = now.strftime("%H:%M")

        entry = self._build_journal_entry(
            word, explanation, date_str, time_str, context
        )

        try:
            if os.path.exists(journal_path):
                with open(journal_path, "r", encoding="utf-8") as f:
                    existing = f.read()

                separator = "\n\n---\n\n" if existing.strip() else ""
                content = existing.rstrip() + separator + entry
            else:
                header = self._build_journal_header()
                content = header + "\n\n" + entry

            with open(journal_path, "w", encoding="utf-8") as f:
                f.write(content)
            return journal_path
        except IOError:
            return None

    def _build_journal_header(self):
        """Title line for a new journal file."""
        title = self._game_name if self._game_name else "Game"
        return f"# {title} Vocabulary\n"

    def _build_journal_entry(self, word, explanation, date_str, time_str,
                             context):
        """Build a single dated section for the journal."""
        entry = f"## {word} ({date_str} {time_str})\n\n"
        entry += f"{explanation}\n"

        context_block = self._build_context_block(context)
        if context_block:
            entry += "\n" + context_block

        return entry

    # ── Markdown builders ──────────────────────────────────────────

    def _build_markdown(self, word, explanation, date_str, context=None):
        """Build the full markdown document for a word note (separate mode)."""
        tags = ["vocabulary"]
        if self._include_game_name and self._game_name:
            tags.append(f"game/{self._sanitize_filename(self._game_name)}")

        tags_str = ", ".join(tags)

        frontmatter = f"""---
word: "{word}"
date: {date_str}"""
        if self._include_game_name and self._game_name:
            frontmatter += f"""
game: "{self._game_name}\""""
        frontmatter += f"""
tags: [{tags_str}]
---

"""
        body = f"# {word}\n\n{explanation}\n"

        context_block = self._build_context_block(context)
        if context_block:
            body += "\n" + context_block

        return frontmatter + body

    def _build_context_block(self, context):
        """Build a markdown block for captured context."""
        if context is None:
            return ""

        parts = []

        if context.screenshot_path:
            safe_path = context.screenshot_path.replace("\\", "/")
            parts.append(f"![[{safe_path}]]")

        if context.clipboard_text:
            lines = context.clipboard_text.strip().split("\n")
            quoted = "\n".join(f"> {line}" for line in lines)
            timestamp = context.timestamp.strftime("%Y-%m-%d %H:%M:%S")
            parts.append(
                f"**Captured Text** ({timestamp}):\n{quoted}"
            )

        if parts:
            return "\n".join(parts) + "\n"

        return ""

    def _extract_images(self, text, output_dir):
        """Extract base64 images from markdown, save as files, replace refs.

        Finds ![](data:image/...) patterns, saves each as a file in the
        attachments subfolder, and replaces with ![](relative_path).
        """
        pattern = r'!\[([^\]]*)\]\((data:image/(?:png|jpeg|jpg|gif|webp);base64,([^)]+))\)'

        attach_dir = os.path.join(output_dir, self._attachments_subfolder)
        os.makedirs(attach_dir, exist_ok=True)

        def _replace(match):
            alt = match.group(1) or "image"
            mime = match.group(2)  # e.g. "image/png"
            b64_data = match.group(3)

            ext = "png"
            if "jpeg" in mime or "jpg" in mime:
                ext = "jpg"
            elif "gif" in mime:
                ext = "gif"
            elif "webp" in mime:
                ext = "webp"

            try:
                raw = base64.b64decode(b64_data)
            except Exception:
                return match.group(0)  # keep original if decode fails

            ts = datetime.now().strftime("%Y%m%d-%H%M%S")
            import uuid
            uid = str(uuid.uuid4())[:8]
            fname = f"note-{ts}-{uid}.{ext}"
            fpath = os.path.join(attach_dir, fname)

            try:
                with open(fpath, "wb") as f:
                    f.write(raw)
            except IOError:
                return match.group(0)

            rel_path = os.path.join(self._attachments_subfolder, fname)
            return f"![{alt}]({rel_path})"

        return re.sub(pattern, _replace, text)

    # ── Utilities ──────────────────────────────────────────────────

    @staticmethod
    def _sanitize_filename(name):
        """Remove characters unsafe for filenames."""
        unsafe = '<>:"/\\|?*'
        for ch in unsafe:
            name = name.replace(ch, "-")
        while "--" in name:
            name = name.replace("--", "-")
        return name.strip("- ")[:80]
