"""Thin wrapper around the Ollama HTTP API.

Keeps request/session handling centralized so generation scripts can call the backend
without duplicating transport logic.
"""

import requests
import os
import threading
from typing import Any, Dict

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
MODEL_NAME = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

_TLS = threading.local()


def _get_session() -> requests.Session:
    """Return a thread-local requests session for connection reuse."""
    sess = getattr(_TLS, "session", None)
    if sess is None:
        # Reuse one session per thread to benefit from connection pooling.
        sess = requests.Session()
        _TLS.session = sess
    return sess


def _env_float(name: str, default: float) -> float:
    """Read a float environment variable with default fallback."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    """Read an integer environment variable with default fallback."""
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def get_generation_options() -> dict:
    """Build the generation options payload for the Ollama API from environment variables."""
    temperature = _env_float("OLLAMA_TEMPERATURE", 0.0)



    num_predict = _env_int("OLLAMA_NUM_PREDICT", 256)
    top_p = _env_float("OLLAMA_TOP_P", 1.0)
    return {
        "temperature": temperature,
        "num_predict": num_predict,
        "top_p": top_p,
    }


def call_ollama(prompt: str) -> str:
    """Call the Ollama generate endpoint and return the response text."""
    opts = get_generation_options()
    timeout_seconds = _env_int("OLLAMA_TIMEOUT_SECONDS", 300)


    max_num_predict = _env_int("OLLAMA_MAX_NUM_PREDICT", 1024)

    def _post(num_predict: int) -> Dict[str, Any]:
        """Submit one Ollama request with the requested token budget."""
        payload: Dict[str, Any] = {
            "model": MODEL_NAME,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": opts["temperature"],
                "num_predict": int(num_predict),
                "top_p": opts["top_p"],
            },
        }

        try:
            response = _get_session().post(
                OLLAMA_URL,
                json=payload,
                timeout=timeout_seconds,
            )
        except requests.exceptions.Timeout as exc:
            raise TimeoutError(
                f"Ollama request timed out after {timeout_seconds}s"
            ) from exc
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(f"Ollama request failed: {exc}") from exc

        if response.status_code != 200:
            raise RuntimeError(f"Ollama error ({response.status_code}): {response.text}")

        try:
            return response.json()
        except Exception as exc:
            raise RuntimeError(f"Ollama returned non-JSON response: {response.text[:200]}") from exc

    num_predict = int(opts["num_predict"])
    data = _post(num_predict)
    done_reason = str(data.get("done_reason") or "").strip().lower()
    if done_reason in {"length", "max_tokens", "token_limit"} and num_predict < max_num_predict:
        bumped = min(max_num_predict, max(num_predict * 2, num_predict + 128))
        data = _post(bumped)

    return str(data.get("response") or "")
