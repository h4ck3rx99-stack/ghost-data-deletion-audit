"""Swappable, cached, token-logged LLM backend (Gemini free tier by default).

Uses the REST API via urllib so no extra dependency is required. Every call is
cached to disk (so reruns cost nothing) and its token usage is appended to
code/evaluation/usage_log.jsonl for usage_report.md. Returns None when no key is
configured, so the pipeline degrades to the deterministic baseline.

Set GEMINI_API_KEY (and optionally GEMINI_MODEL) in a gitignored repo-root .env.
To use a local model instead, implement a backend with the same generate().
"""
import base64
import hashlib
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from loaders import REPO

CACHE_DIR = REPO / "code" / ".cache" / "llm"
USAGE_LOG = REPO / "code" / "evaluation" / "usage_log.jsonl"
_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"


def load_env():
    env = REPO / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


class GeminiBackend:
    provider = "google"

    def __init__(self, key, model=None):
        self.key = key
        self.model = model or os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, digest):
        return CACHE_DIR / f"{digest}.json"

    def generate(self, prompt, image_bytes=None, mime="image/png", kind="generic"):
        """Return model text; cached by (model, prompt, image). Logs tokens."""
        h = hashlib.sha256()
        h.update(self.model.encode())
        h.update(prompt.encode("utf-8"))
        if image_bytes:
            h.update(image_bytes)
        digest = h.hexdigest()
        cp = self._cache_path(digest)
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))["text"]

        parts = [{"text": prompt}]
        if image_bytes:
            parts.append({"inline_data": {"mime_type": mime,
                                          "data": base64.b64encode(image_bytes).decode()}})
        body = json.dumps({"contents": [{"parts": parts}]}).encode("utf-8")
        url = _ENDPOINT.format(model=self.model, key=self.key)
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:  # API/network error -> caller falls back; not cached, so retried later
            return None
        text = ""
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            pass
        usage = data.get("usageMetadata", {})
        self._log(kind, usage)
        cp.write_text(json.dumps({"text": text, "usage": usage}), encoding="utf-8")
        return text

    def _log(self, kind, usage):
        _log_usage(self.provider, self.model, kind,
                   usage.get("promptTokenCount", 0), usage.get("candidatesTokenCount", 0))


def _log_usage(provider, model, kind, in_tok, out_tok):
    USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(USAGE_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "provider": provider, "model": model, "kind": kind,
            "in_tokens": in_tok, "out_tokens": out_tok,
        }) + "\n")


class OllamaBackend:
    """Local Ollama (free). Same generate() interface, so it is a drop-in for the
    Gemini backend. Needs `ollama serve` running and a (vision-capable) model
    pulled, e.g. `ollama pull llama3.2-vision`."""
    provider = "ollama"

    def __init__(self, model=None, host=None):
        self.model = model or os.environ.get("OLLAMA_MODEL", "llama3.2")
        self.vision_model = os.environ.get("OLLAMA_VISION_MODEL", "llama3.2-vision")
        self.host = (host or os.environ.get("OLLAMA_HOST", "http://localhost:11434")).rstrip("/")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def generate(self, prompt, image_bytes=None, mime="image/png", kind="generic"):
        model = self.vision_model if image_bytes else self.model
        h = hashlib.sha256()
        h.update(("ollama:" + model).encode())
        h.update(prompt.encode("utf-8"))
        if image_bytes:
            h.update(image_bytes)
        cp = CACHE_DIR / f"{h.hexdigest()}.json"
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))["text"]
        payload = {"model": model, "prompt": prompt, "stream": False}
        if image_bytes:
            payload["images"] = [base64.b64encode(image_bytes).decode()]
        req = urllib.request.Request(self.host + "/api/generate",
                                     data=json.dumps(payload).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        text = data.get("response", "")
        _log_usage(self.provider, model, kind,
                   data.get("prompt_eval_count", 0), data.get("eval_count", 0))
        cp.write_text(json.dumps({"text": text}), encoding="utf-8")
        return text


_INTENT_PROMPT = (
    "A customer sent this message to a platform. Does it authorize DELETING the "
    "account or personal data (not merely access, export, correction, or marketing "
    'opt-out)? Answer with exactly one word: YES or NO.\n\nMessage:\n"{text}"')


def is_deletion_request(text, backend):
    ans = backend.generate(_INTENT_PROMPT.format(text=text), kind="intent")
    if ans is None:  # API unavailable -> default to deletion (workflow context)
        return True
    return not ans.strip().upper().startswith("NO")


class GroqBackend:
    """Groq (OpenAI-compatible, free tier, fast). Separate text and vision models.
    Needs GROQ_API_KEY; override models with GROQ_MODEL / GROQ_VISION_MODEL."""
    provider = "groq"
    _URL = "https://api.groq.com/openai/v1/chat/completions"

    # Groq is behind Cloudflare, which blocks the default urllib User-Agent.
    _UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
           "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

    def __init__(self, key):
        self.key = key
        self.model = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
        self.vision_model = os.environ.get("GROQ_VISION_MODEL", self.model)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def generate(self, prompt, image_bytes=None, mime="image/png", kind="generic"):
        model = self.vision_model if image_bytes else self.model
        h = hashlib.sha256()
        h.update(("groq:" + model).encode())
        h.update(prompt.encode("utf-8"))
        if image_bytes:
            h.update(image_bytes)
        cp = CACHE_DIR / f"{h.hexdigest()}.json"
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))["text"]
        if image_bytes:
            url = f"data:{mime};base64," + base64.b64encode(image_bytes).decode()
            content = [{"type": "text", "text": prompt},
                       {"type": "image_url", "image_url": {"url": url}}]
        else:
            content = prompt
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": content}]}).encode()
        req = urllib.request.Request(self._URL, data=body, headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {self.key}",
            "User-Agent": self._UA})
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return None
        text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        u = data.get("usage", {})
        _log_usage(self.provider, model, kind,
                   u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
        cp.write_text(json.dumps({"text": text}), encoding="utf-8")
        return text


class OpenRouterBackend:
    """OpenRouter (OpenAI-compatible, many free vision models). Tries a primary
    model, then a fallback, each with 429 backoff — the free tier shares upstream
    pools that rate-limit independently. Needs OPENROUTER_API_KEY; override models
    with OPENROUTER_MODEL / OPENROUTER_FALLBACK."""
    provider = "openrouter"
    _URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, key):
        self.key = key
        self.model = os.environ.get("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
        self.fallback = os.environ.get("OPENROUTER_FALLBACK", "nvidia/nemotron-3.5-super-vl:free")
        CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def generate(self, prompt, image_bytes=None, mime="image/png", kind="generic"):
        h = hashlib.sha256()
        h.update(("openrouter:" + self.model).encode())  # cache once; fallback answer stored here too
        h.update(prompt.encode("utf-8"))
        if image_bytes:
            h.update(image_bytes)
        cp = CACHE_DIR / f"{h.hexdigest()}.json"
        if cp.exists():
            return json.loads(cp.read_text(encoding="utf-8"))["text"]
        if image_bytes:
            url = f"data:{mime};base64," + base64.b64encode(image_bytes).decode()
            content = [{"type": "text", "text": prompt},
                       {"type": "image_url", "image_url": {"url": url}}]
        else:
            content = prompt
        for model in (self.model, self.fallback):
            text = self._call(model, content, kind)
            if text is not None:
                cp.write_text(json.dumps({"text": text}), encoding="utf-8")
                return text
        return None

    def _call(self, model, content, kind):
        """One model, up to 3 tries with exponential backoff on 429; None on give-up."""
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": content}]}).encode()
        for attempt in range(3):
            req = urllib.request.Request(self._URL, data=body, headers={
                "Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    time.sleep(3 * 2 ** attempt)
                    continue
                return None
            except Exception:
                return None
            text = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            u = data.get("usage", {})
            _log_usage(self.provider, model, kind,
                       u.get("prompt_tokens", 0), u.get("completion_tokens", 0))
            return text
        return None


def get_backend():
    """Pick a backend by what is configured, else None (deterministic-only):
    OpenRouter (OPENROUTER_API_KEY) > Groq (GROQ_API_KEY) > Ollama
    (LLM_BACKEND=ollama / OLLAMA_MODEL) > Gemini (GEMINI_API_KEY). Force one with
    LLM_BACKEND."""
    load_env()
    choice = os.environ.get("LLM_BACKEND", "").lower()
    if choice == "openrouter" or (not choice and os.environ.get("OPENROUTER_API_KEY")):
        return OpenRouterBackend(os.environ["OPENROUTER_API_KEY"])
    if choice == "groq" or (not choice and os.environ.get("GROQ_API_KEY")):
        return GroqBackend(os.environ["GROQ_API_KEY"])
    if choice == "ollama" or (not choice and os.environ.get("OLLAMA_MODEL")):
        return OllamaBackend()
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return GeminiBackend(key) if key else None
