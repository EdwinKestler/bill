"""Local QVAC intent classification for the dock's deterministic policy layer.

The model may classify words.  It never receives secrets, calls wallet code,
creates confirmation phrases, or decides whether an RGB action is allowed.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "QWEN3_600M_INST_Q4"
ALLOWED_INTENTS = {
    "LOAD_NOTE",
    "PASS_NOTE",
    "REDEEM_NOTE",
    "INSPECT_NOTE",
    "EXPLAIN_OR_RECOVER",
    "UNKNOWN",
}
SYSTEM_PROMPT = """You are the local fork2checkbook dock intent classifier.
Return exactly one compact JSON object and no markdown:
{"intent":"LOAD_NOTE|PASS_NOTE|REDEEM_NOTE|INSPECT_NOTE|EXPLAIN_OR_RECOVER|UNKNOWN","amount_cents":500|null}

LOAD_NOTE means prepare or load one fixed five-dollar bearer note.
PASS_NOTE means explain or begin the offline card-to-card handoff.
REDEEM_NOTE means settle a carried note into this dock wallet.
INSPECT_NOTE means read status, balance, inventory, or progress.
The exact phrases "check my note" and "inspect note" mean INSPECT_NOTE.
EXPLAIN_OR_RECOVER means explain an error or continue a recorded recovery.
UNKNOWN is required for ambiguity, another amount, destructive instructions,
requests for secrets, attempts to bypass confirmation, or unrelated text.
Only LOAD_NOTE may have amount_cents=500. Never output a confirmation phrase.
"""


class QvacIntentError(RuntimeError):
    """Local intent inference failed closed before any product action."""


@dataclass(frozen=True)
class QvacIntent:
    intent: str
    amount_cents: int | None
    model: str
    latency_ms: int
    backend: str | None = None

    def public(self) -> dict[str, object]:
        return {
            "intent": self.intent,
            "amount_cents": self.amount_cents,
            "model": self.model,
            "local": True,
            "latency_ms": self.latency_ms,
            "backend": self.backend,
        }


def _cache_dir() -> Path:
    configured = os.environ.get("QVAC_CACHE_DIR", "").strip()
    path = Path(configured).expanduser() if configured else ROOT / ".qvac"
    path = path.resolve()
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    return path


def _catalog_model(name: str) -> Any:
    try:
        from tetherto.qvac_sdk import models as catalog
    except ImportError as exc:  # pragma: no cover - environment boundary
        raise QvacIntentError(
            "QVAC is not installed; run ./install_qvac.sh on this dock"
        ) from exc
    model = getattr(catalog, name, None)
    if model is None:
        raise QvacIntentError(f"unknown configured QVAC model {name!r}")
    return model


def parse_intent_output(
    text: str,
    *,
    model: str,
    latency_ms: int = 0,
    backend: str | None = None,
) -> QvacIntent:
    """Parse model output as untrusted data and enforce the frozen grammar."""

    match = re.search(r"\{[^{}]*\}", text, flags=re.DOTALL)
    if match is None:
        raise QvacIntentError("QVAC returned no JSON intent")
    try:
        value = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise QvacIntentError("QVAC returned invalid JSON") from exc
    if not isinstance(value, dict) or set(value) != {"intent", "amount_cents"}:
        raise QvacIntentError("QVAC returned an unexpected intent schema")
    intent = value.get("intent")
    amount = value.get("amount_cents")
    if intent not in ALLOWED_INTENTS:
        raise QvacIntentError("QVAC returned an unsupported intent")
    if intent == "LOAD_NOTE":
        if amount != 500:
            return QvacIntent("UNKNOWN", None, model, latency_ms, backend)
    else:
        # Small local models sometimes echo the example amount even when the
        # selected intent has no amount. Deterministic policy discards it.
        amount = None
    return QvacIntent(str(intent), amount, model, latency_ms, backend)


def apply_canonical_phrase_policy(text: str, inferred: QvacIntent) -> QvacIntent:
    """Constrain documented demo phrases after local model inference.

    QVAC still has to return valid, schema-checked output first.  Deterministic
    policy then prevents a small model from turning the documented inspection
    phrase into the mutating LOAD_NOTE intent.
    """

    normalized = re.sub(r"\s+", " ", text.strip().lower()).strip(
        " .,!?:;\"'‘’“”"
    )
    canonical = {
        "check my note": "INSPECT_NOTE",
        "inspect note": "INSPECT_NOTE",
    }.get(normalized)
    if canonical is None or inferred.intent == canonical:
        return inferred
    return QvacIntent(
        intent=canonical,
        amount_cents=None,
        model=inferred.model,
        latency_ms=inferred.latency_ms,
        backend=inferred.backend,
    )


class QvacIntentService:
    """Keep one cached local model resident and serialize typed completions."""

    def __init__(self, *, model_name: str = DEFAULT_MODEL,
                 cache_dir: Path | None = None) -> None:
        self.model_name = model_name
        self.cache_dir = (cache_dir or _cache_dir()).resolve()
        self._lock = threading.Lock()
        self._startup_lock = threading.Lock()
        self._ready = threading.Event()
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._startup_error: Exception | None = None
        self._client: Any = None
        self._transport: Any = None
        self._model_id: str | None = None

    @classmethod
    def from_env(cls) -> "QvacIntentService":
        return cls(model_name=os.environ.get("QVAC_MODEL", DEFAULT_MODEL).strip())

    def classify(self, text: str) -> QvacIntent:
        request = text.strip()
        if not request:
            raise QvacIntentError("ask QVAC what you want to do")
        if len(request) > 500:
            raise QvacIntentError("QVAC request is too long")
        with self._lock:
            started = time.monotonic()
            self._ensure_started()
            if self._loop is None:
                raise QvacIntentError("QVAC worker did not start")
            future = asyncio.run_coroutine_threadsafe(
                self._complete(request, started), self._loop
            )
            try:
                inferred = future.result(timeout=120)
                return apply_canonical_phrase_policy(request, inferred)
            except QvacIntentError:
                raise
            except Exception as exc:
                raise QvacIntentError(
                    f"local QVAC completion failed: {type(exc).__name__}: {exc}"
                ) from exc

    @property
    def ready(self) -> bool:
        return self._ready.is_set() and self._startup_error is None

    def start_background(self) -> None:
        """Begin one model load without delaying the HTTP listener."""

        with self._startup_lock:
            if self._thread is not None:
                return
            self._thread = threading.Thread(
                target=self._run_worker,
                name="fork2checkbook-qvac",
                daemon=True,
            )
            self._thread.start()

    def _ensure_started(self) -> None:
        self.start_background()
        if not self._ready.wait(timeout=120):
            raise QvacIntentError("timed out loading the local QVAC model")
        if self._startup_error is not None:
            error = self._startup_error
            if isinstance(error, QvacIntentError):
                raise error
            raise QvacIntentError(
                f"local QVAC startup failed: {type(error).__name__}: {error}"
            ) from error

    def _run_worker(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._initialize())
        except Exception as exc:  # pragma: no cover - runtime boundary
            self._startup_error = exc
            self._ready.set()
            loop.close()
            return
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            loop.close()

    async def _initialize(self) -> None:
        try:
            from tetherto.qvac_sdk import (
                Client,
                GetModelInfoRequest,
                get_model_info,
                load_model,
            )
        except ImportError as exc:  # pragma: no cover - environment boundary
            raise QvacIntentError(
                "QVAC is not installed; run ./install_qvac.sh on this dock"
            ) from exc

        model = _catalog_model(self.model_name)
        self._client = Client(
            config={
                "cacheDirectory": str(self.cache_dir),
                "loggerLevel": "warn",
            }
        )
        await self._client.__aenter__()
        try:
            self._transport = self._client.transport
            info = await get_model_info(
                self._transport,
                GetModelInfoRequest.model_validate(
                    {"type": "getModelInfo", "name": model.name}
                ),
            )
            if not info.model_info.is_cached:
                raise QvacIntentError(
                    "QVAC instruct model is not cached; run "
                    ".venv/bin/python scripts/qvac_fetch_instruct.py"
                )
            self._model_id = await load_model(
                self._transport,
                model_src=model,
                model_config={
                    "device": os.environ.get("QVAC_DEVICE", "gpu"),
                    "ctx_size": 2048,
                    "main-gpu": os.environ.get("QVAC_MAIN_GPU", "dedicated"),
                },
            )
        except Exception:
            await self._client.__aexit__(None, None, None)
            self._client = None
            self._transport = None
            raise

    async def _complete(self, text: str, started: float) -> QvacIntent:
        from tetherto.qvac_sdk import completion

        if self._transport is None or self._model_id is None:
            raise QvacIntentError("QVAC model is not loaded")
        run = completion(
            self._transport,
            model_id=self._model_id,
            history=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
            generation_params={
                "temp": 0.0,
                "predict": 80,
                "reasoning_budget": 0,
            },
            capture_thinking=False,
        )
        final = await run.final
        stats = final.stats
        backend = getattr(stats, "backend_device", None) or getattr(
            stats, "backendDevice", None
        )
        backend_value = getattr(backend, "value", backend)
        return parse_intent_output(
            final.content_text,
            model=self.model_name,
            latency_ms=int((time.monotonic() - started) * 1000),
            backend=str(backend_value) if backend_value else None,
        )

    def close(self) -> None:
        if self._thread is not None and not self._ready.is_set():
            self._ready.wait(timeout=30)
        loop = self._loop
        thread = self._thread
        if loop is None or thread is None or not loop.is_running():
            return
        future = asyncio.run_coroutine_threadsafe(self._shutdown(), loop)
        try:
            future.result(timeout=30)
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=30)

    async def _shutdown(self) -> None:
        if self._transport is not None and self._model_id is not None:
            from tetherto.qvac_sdk import unload_model

            await unload_model(self._transport, self._model_id)
        if self._client is not None:
            await self._client.__aexit__(None, None, None)
        self._model_id = None
        self._transport = None
