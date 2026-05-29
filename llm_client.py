"""OpenAI-compatible API client for word explanations."""

from openai import OpenAI, APIError, AuthenticationError, \
    APIConnectionError, APITimeoutError, RateLimitError
from PyQt5.QtCore import QObject, pyqtSignal


SYSTEM_PROMPT = """You are an English vocabulary teacher. For any English word or phrase provided, respond in this exact structure:

**Pronunciation**: [IPA]
**Definition**: [part of speech] — [clear English definition, 1-2 sentences]
**Etymology**: [origin language and root meaning, 1 sentence]
**Examples**:
1. [natural English sentence]
2. [natural English sentence]
3. [natural English sentence]

Rules:
- Respond entirely in English, no Chinese
- Keep total response under 400 tokens
- Use proper markdown formatting"""


TRANSLATE_PROMPT = """You are a professional English-to-Chinese translator. Translate the given English text into natural, fluent Chinese. Respond with ONLY the Chinese translation — no explanations, no pinyin, no additional text."""


class LLMClient(QObject):
    """Calls an OpenAI-compatible chat completions API for word explanations."""

    explanation_ready = pyqtSignal(str, str)  # (full_text, word)
    llm_error = pyqtSignal(str)

    def __init__(self, base_url="", api_key="", model="gpt-3.5-turbo"):
        super().__init__()
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._client = None

    def update_config(self, base_url, api_key, model):
        """Update API settings and reset client."""
        self._base_url = base_url
        self._api_key = api_key
        self._model = model
        self._client = None

    def _ensure_client(self):
        """Create or recreate the OpenAI client."""
        if self._client is not None:
            return
        if not self._base_url or not self._api_key:
            raise ValueError(
                "API not configured. Please set llm_base_url and llm_api_key "
                "in config.json."
            )
        self._client = OpenAI(
            base_url=self._base_url,
            api_key=self._api_key,
            timeout=15.0,
            max_retries=1
        )

    def get_explanation(self, word_or_phrase):
        """Query the LLM for word explanation. Blocking call.

        Args:
            word_or_phrase: The word or phrase to explain.

        Returns:
            Explanation text string.
        """
        word = word_or_phrase.strip()
        if not word:
            return ""

        try:
            self._ensure_client()
        except ValueError as e:
            self.llm_error.emit(str(e))
            return str(e)

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": f"Please explain: {word}"}
                ],
                max_tokens=400,
                temperature=0.3
            )
            content = response.choices[0].message.content
            if not content:
                self.llm_error.emit("API returned empty response")
                return "Error: empty response"

            self.explanation_ready.emit(content, word)
            return content

        except AuthenticationError:
            msg = "API key invalid. Check llm_api_key in config.json."
            self.llm_error.emit(msg)
            return f"Error: {msg}"
        except APIConnectionError:
            msg = "Cannot connect to API. Check base_url and network."
            self.llm_error.emit(msg)
            return f"Error: {msg}"
        except APITimeoutError:
            msg = "API request timed out. Try again."
            self.llm_error.emit(msg)
            return f"Error: {msg}"
        except RateLimitError:
            msg = "API rate limited. Wait a moment and retry."
            self.llm_error.emit(msg)
            return f"Error: {msg}"
        except APIError as e:
            msg = f"API error (HTTP {e.http_status}): {e.message}"
            self.llm_error.emit(msg)
            return f"Error: {msg}"
        except Exception as e:
            msg = f"Unexpected error: {e}"
            self.llm_error.emit(msg)
            return f"Error: {msg}"

    def translate_to_chinese(self, text):
        """Translate English text to Chinese. Blocking call.

        Args:
            text: English text to translate.

        Returns:
            Chinese translation string, or error string on failure.
        """
        text = text.strip()
        if not text:
            return ""

        try:
            self._ensure_client()
        except ValueError as e:
            return str(e)

        # Truncate long text to stay within token limits
        if len(text) > 400:
            text = text[:400] + "..."

        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": TRANSLATE_PROMPT},
                    {"role": "user", "content": f"Translate: {text}"}
                ],
                max_tokens=200,
                temperature=0.1
            )
            content = response.choices[0].message.content
            if not content:
                return "Error: empty translation"
            return content.strip()

        except AuthenticationError:
            return "Error: API key invalid"
        except APIConnectionError:
            return "Error: Cannot connect to API"
        except APITimeoutError:
            return "Error: Request timed out"
        except RateLimitError:
            return "Error: Rate limited, wait and retry"
        except APIError as e:
            return f"Error: API error ({e.http_status})"
        except Exception as e:
            return f"Error: {e}"
