"""Keep LLM output in the reading's language.

The language rule in a prompt is only a request: a model can still slip a word of
a related language into a Tamil reading. `ScriptGuard` is the enforcement. It
watches the streamed text, holds back any run of characters from a script that
does not belong in the target language, and replaces it with a translation, or
removes it when no translation is available.

Pure text handling, no FastAPI or HTTP. The translator is injected by the caller.
Latin is always allowed: digits, citations and the odd technical term use it.
"""
import logging
import re
import unicodedata

logger = logging.getLogger("vedic.output_guard")

_SCRIPT_RANGES = {
    "Devanagari": [(0x0900, 0x097F), (0x1CD0, 0x1CFF), (0xA8E0, 0xA8FF)],
    "Bengali": [(0x0980, 0x09FF)],
    "Gurmukhi": [(0x0A00, 0x0A7F)],
    "Gujarati": [(0x0A80, 0x0AFF)],
    "Odia": [(0x0B00, 0x0B7F)],
    "Tamil": [(0x0B80, 0x0BFF)],
    "Telugu": [(0x0C00, 0x0C7F)],
    "Kannada": [(0x0C80, 0x0CFF)],
    "Malayalam": [(0x0D00, 0x0D7F)],
    "Sinhala": [(0x0D80, 0x0DFF)],
    "Thai": [(0x0E00, 0x0E7F)],
    "Tibetan": [(0x0F00, 0x0FFF)],
    "Hebrew": [(0x0590, 0x05FF)],
    "Arabic": [(0x0600, 0x06FF)],
    "Cyrillic": [(0x0400, 0x04FF)],
    "Japanese": [(0x3040, 0x30FF)],
    "Chinese": [(0x3400, 0x9FFF)],
    "Korean": [(0xAC00, 0xD7AF)],
}

# The native script of each reading language. English has none: Latin is always allowed.
LANG_SCRIPT = {
    "ta": "Tamil",
    "te": "Telugu",
    "ml": "Malayalam",
    "kn": "Kannada",
    "hi": "Devanagari",
}

# Spaces and joiners can sit inside a foreign phrase. A newline always ends one.
_RUN_NEUTRAL = " \t‌‍"
MAX_RUN_CHARS = 300
MAX_TRANSLATIONS = 6


def _foreign_class(lang, allow_scripts=()):
    allowed = set(allow_scripts)
    native = LANG_SCRIPT.get(lang)
    if native:
        allowed.add(native)
    parts = []
    for script, ranges in _SCRIPT_RANGES.items():
        if script in allowed:
            continue
        for low, high in ranges:
            parts.append(f"\\u{low:04X}-\\u{high:04X}")
    return "".join(parts)


def has_foreign_script(text, lang, allow_scripts=()):
    """True if `text` has characters from a script that doesn't belong in `lang`."""
    return bool(re.search(f"[{_foreign_class(lang, allow_scripts)}]", text or ""))


class ScriptGuard:
    """Streaming filter: `feed()` each chunk, then `flush()` once at the end.

    Text that may still be part of a foreign run is held back, so a run split
    across two chunks is treated as one phrase.
    """

    def __init__(self, lang, translate=None, allow_scripts=(), max_translations=MAX_TRANSLATIONS):
        foreign = _foreign_class(lang, allow_scripts)
        self._lang = lang
        self._allow_scripts = allow_scripts
        self._foreign_re = re.compile(f"[{foreign}]")
        self._run_re = re.compile(f"[{foreign}{_RUN_NEUTRAL}]*")
        self._translate = translate
        self._translations_left = max_translations
        self._cache = {}
        self._buf = ""
        self._last_char = ""
        self._strip_marks = False
        self.replaced = 0
        self.removed = 0

    def feed(self, chunk):
        self._buf += chunk or ""
        return self._drain(final=False)

    def flush(self, translate=True):
        """Release everything still held. `translate=False` removes a held run
        without calling the model (used when the stream has already failed)."""
        if not translate:
            self._translate = None
        return self._drain(final=True)

    def _drain(self, final):
        out = []
        while self._buf:
            if self._strip_marks:
                # A combining mark left behind by a removed run would attach to
                # the wrong letter.
                kept = self._buf.lstrip("‌‍")
                while kept and unicodedata.category(kept[0]) in ("Mn", "Mc"):
                    kept = kept[1:]
                self._buf = kept
                if not kept:
                    break
                self._strip_marks = False

            match = self._foreign_re.search(self._buf)
            if match is None:
                self._emit(out, self._buf)
                self._buf = ""
                break
            if match.start():
                self._emit(out, self._buf[:match.start()])
                self._buf = self._buf[match.start():]

            end = self._run_re.match(self._buf).end()
            if end > MAX_RUN_CHARS:
                end = MAX_RUN_CHARS
            elif end == len(self._buf) and not final:
                break  # the run may continue in the next chunk
            run, self._buf = self._buf[:end], self._buf[end:]
            self._resolve(out, run)
        return "".join(out)

    def _emit(self, out, text):
        if text:
            out.append(text)
            self._last_char = text[-1]

    def _resolve(self, out, run):
        core = run.strip(_RUN_NEUTRAL)
        lead = run[:len(run) - len(run.lstrip(_RUN_NEUTRAL))]
        trail = run[len(run.rstrip(_RUN_NEUTRAL)):]
        replacement = self._replacement(core)
        self._strip_marks = True
        if replacement:
            self.replaced += 1
            self._emit(out, f"{lead}{replacement}{trail}")
            return
        self.removed += 1
        # Avoid leaving a double space where the run used to be.
        for gap in (lead, trail):
            if gap and self._last_char and not self._last_char.isspace():
                self._emit(out, " ")
                break

    def _replacement(self, core):
        if core in self._cache:
            return self._cache[core]
        result = ""
        if self._translate and self._translations_left > 0:
            self._translations_left -= 1
            try:
                result = self._valid_translation(self._translate(core), core)
            except Exception as e:
                logger.warning("Stray-script translation failed: %s", e)
        self._cache[core] = result
        return result

    def _valid_translation(self, text, core):
        lines = (text or "").strip().splitlines()
        candidate = lines[0].strip().strip("\"'`*") if lines else ""
        if not candidate or len(candidate) > len(core) * 3 + 40:
            return ""
        return "" if self._foreign_re.search(candidate) else candidate


def clean_text(text, lang, translate=None, allow_scripts=()):
    """Apply the guard to a complete, non-streamed response."""
    guard = ScriptGuard(lang, translate=translate, allow_scripts=allow_scripts)
    return guard.feed(text) + guard.flush()
