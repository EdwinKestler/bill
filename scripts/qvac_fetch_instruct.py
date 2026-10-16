#!/usr/bin/env python3
"""Phase-3: cache the small instruct GGUF into .qvac and run one completion.

Default model: QWEN3_600M_INST_Q4 (~382 MB). Override with QVAC_MODEL.
Does not pull extra catalog models.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "QWEN3_600M_INST_Q4"


def _dump(obj):
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json", by_alias=True)
    if hasattr(obj, "value"):
        return obj.value
    return obj


def _resolve_cache_dir() -> Path:
    env = os.environ.get("QVAC_CACHE_DIR")
    if env:
        path = Path(env).expanduser()
        if not path.is_absolute():
            raise SystemExit("QVAC_CACHE_DIR must be an absolute path")
        path.mkdir(parents=True, exist_ok=True)
        return path
    path = (ROOT / ".qvac").resolve()
    path.mkdir(parents=True, exist_ok=True)
    os.environ["QVAC_CACHE_DIR"] = str(path)
    return path


def _resolve_model():
    from tetherto.qvac_sdk import models as catalog

    name = os.environ.get("QVAC_MODEL", DEFAULT_MODEL).strip()
    const = getattr(catalog, name, None)
    if const is None:
        raise SystemExit(f"unknown QVAC_MODEL {name!r}")
    return const


def _print_progress(p) -> None:
    line = (
        f"download {p.percentage:.0f}% "
        f"({getattr(p, 'downloaded', 0) / 1e6:.1f}/{getattr(p, 'total', 0) / 1e6:.1f} MB)"
    )
    print(line, end="\r" if sys.stderr.isatty() else "\n", file=sys.stderr)
    if getattr(p, "percentage", 0) >= 100:
        print(file=sys.stderr)


async def _run(cache_dir: Path) -> dict:
    from tetherto.qvac_sdk import (
        Client,
        GetLoadedModelInfoRequest,
        GetModelInfoRequest,
        completion,
        get_loaded_model_info,
        get_model_info,
        load_model,
        unload_model,
    )

    model = _resolve_model()
    report: dict = {
        "model": model.name,
        "expected_size": model.expected_size,
        "engine": model.engine,
        "params": model.params,
        "cache_directory": str(cache_dir),
    }

    async with Client(
        config={"cacheDirectory": str(cache_dir), "loggerLevel": "warn"}
    ) as client:
        t = client.transport
        info = await get_model_info(
            t,
            GetModelInfoRequest.model_validate(
                {"type": "getModelInfo", "name": model.name}
            ),
        )
        report["before"] = {
            "is_cached": info.model_info.is_cached,
            "is_loaded": info.model_info.is_loaded,
            "cache_files": [
                {
                    "filename": f.filename,
                    "path": f.path,
                    "is_cached": f.is_cached,
                    "actual_size": f.actual_size,
                }
                for f in (info.model_info.cache_files or [])
            ],
        }

        model_id = await load_model(
            t,
            model_src=model,
            model_config={
                "device": "gpu",
                "ctx_size": 4096,
                "main-gpu": "dedicated",
            },
            on_progress=_print_progress,
        )
        loaded = await get_loaded_model_info(
            t,
            GetLoadedModelInfoRequest.model_validate(
                {"type": "getLoadedModelInfo", "modelId": model_id}
            ),
        )
        fit = loaded.info.fit_probe
        report["loaded"] = {
            "model_id": model_id,
            "path": loaded.info.path,
            "display_name": loaded.info.display_name,
            "fit_probe": _dump(fit),
        }

        run = completion(
            t,
            model_id=model_id,
            history=[
                {
                    "role": "system",
                    "content": "You are the fork2checkbook printer. Reply with one line: PRINT <integer dollars>.",
                },
                {"role": "user", "content": "bill for $5"},
            ],
            generation_params={
                "temp": 0.1,
                "predict": 48,
                "reasoning_budget": 0,
            },
            capture_thinking=True,
        )
        async for event in run.events:
            if event.type == "contentDelta":
                sys.stdout.write(event.text)
                sys.stdout.flush()
        print()
        final = await run.final
        report["completion"] = {
            "content_text": final.content_text,
            "thinking_text": final.thinking_text,
            "stop_reason": final.stop_reason,
            "stats": _dump(final.stats),
        }

        after = await get_model_info(
            t,
            GetModelInfoRequest.model_validate(
                {"type": "getModelInfo", "name": model.name}
            ),
        )
        report["after"] = {
            "is_cached": after.model_info.is_cached,
            "actual_size": after.model_info.actual_size,
            "cache_files": [
                {
                    "filename": f.filename,
                    "path": f.path,
                    "is_cached": f.is_cached,
                    "actual_size": f.actual_size,
                }
                for f in (after.model_info.cache_files or [])
            ],
        }
        await unload_model(t, model_id)

    return report


def main() -> int:
    cache_dir = _resolve_cache_dir()
    report = asyncio.run(_run(cache_dir))
    print(json.dumps(report, indent=2, default=str))
    stats = report.get("completion", {}).get("stats") or {}
    backend = stats.get("backendDevice") or stats.get("backend_device")
    print(f"backend_device: {backend}", file=sys.stderr)
    if not report.get("after", {}).get("is_cached"):
        print("model did not stay in .qvac cache", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
