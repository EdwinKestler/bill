#!/usr/bin/env python3
"""Phase-2 QVAC smoke: spawn the bundled worker, no GGUF download.

Confirms the fat linux-x64 wheel, heartbeat, GPU driver flags (cuda/vulkan),
and local catalog constants. Registry list is best-effort (may need network).
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from importlib.metadata import distribution, version
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _cap_value(obj):
    if obj is None:
        return None
    status = getattr(obj, "status", None)
    if status == "supported":
        return getattr(obj, "value", True)
    return {"status": status, "reason": getattr(obj, "reason", None)}


def _gpu_summary(gpu) -> dict:
    drivers = gpu.drivers
    return {
        "id": gpu.id,
        "name": _cap_value(gpu.name),
        "vendor": _cap_value(gpu.vendor),
        "type": _cap_value(gpu.type),
        "driver_name": _cap_value(gpu.driver_name),
        "driver_version": _cap_value(gpu.driver_version),
        "memory_total_bytes": _cap_value(gpu.memory_total_bytes),
        "drivers": {
            "cuda": _cap_value(drivers.cuda),
            "vulkan": _cap_value(drivers.vulkan),
            "opencl": _cap_value(drivers.opencl),
            "metal": _cap_value(drivers.metal),
        },
    }


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


def _assert_fat_wheel() -> dict:
    pkg = version("tetherto-qvac-sdk")
    dist = distribution("tetherto-qvac-sdk")
    import tetherto.qvac_sdk as sdk

    sdk_root = Path(sdk.__file__).resolve().parent
    worker = sdk_root / "_bundle" / "worker" / "dist" / "src" / "worker" / "index.js"
    bare = sdk_root / "_bundle" / "runtime" / "bare"
    if not worker.is_file() or not bare.is_file():
        raise SystemExit(
            "thin wheel installed (no _bundle). Re-run:\n"
            "  pip install --force-reinstall 'tetherto-qvac-sdk==0.21.0' \\\n"
            "    -f https://github.com/tetherto/qvac/releases/expanded_assets/sdk-v0.21.0"
        )
    direct = dist.locate_file("direct_url.json")
    rec = dist.read_text("WHEEL") or ""
    return {
        "package_version": pkg,
        "sdk_root": str(sdk_root),
        "bundled_worker": str(worker),
        "bundled_bare": str(bare),
        "bare_executable": os.access(bare, os.X_OK),
        "wheel_metadata": rec.strip(),
        "direct_url": str(direct) if Path(str(direct)).is_file() else None,
    }


async def _smoke(cache_dir: Path, wheel: dict) -> dict:
    from tetherto.qvac_sdk import (
        Client,
        GetSystemResourcesRequest,
        HeartbeatRequest,
        get_system_resources,
        heartbeat,
        model_registry_list,
    )
    from tetherto.qvac_sdk.models import (
        QWEN3_5_0_8B_MULTIMODAL_Q4_K_M,
        QWEN3_5_2B_MULTIMODAL_Q4_K_M,
    )

    catalog = {
        "QWEN3_5_2B_MULTIMODAL_Q4_K_M": QWEN3_5_2B_MULTIMODAL_Q4_K_M.name,
        "QWEN3_5_0_8B_MULTIMODAL_Q4_K_M": QWEN3_5_0_8B_MULTIMODAL_Q4_K_M.name,
    }

    report: dict = {
        "wheel": wheel,
        "cache_directory": str(cache_dir),
        "catalog": catalog,
    }

    async with Client(config={"cacheDirectory": str(cache_dir), "loggerLevel": "warn"}) as client:
        t = client.transport
        hb = await heartbeat(t, HeartbeatRequest(type="heartbeat"))
        report["heartbeat"] = hb.number

        resources = await get_system_resources(
            t, GetSystemResourcesRequest(type="getSystemResources")
        )
        gpus = resources.capabilities.gpus
        gpu_block: dict = {"status": gpus.status}
        if gpus.status == "supported":
            gpu_block["devices"] = [_gpu_summary(g) for g in gpus.value]
        else:
            gpu_block["reason"] = getattr(gpus, "reason", None)
        report["gpus"] = gpu_block

        try:
            models = await asyncio.wait_for(model_registry_list(t), timeout=45)
            report["registry"] = {
                "ok": True,
                "count": len(models),
                "sample": [m.name for m in models[:8]],
            }
        except Exception as exc:  # noqa: BLE001 — smoke: registry is optional
            report["registry"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    return report


def main() -> int:
    cache_dir = _resolve_cache_dir()
    wheel = _assert_fat_wheel()
    report = asyncio.run(_smoke(cache_dir, wheel))
    print(json.dumps(report, indent=2, default=str))
    gpus = report["gpus"]
    if gpus.get("status") == "supported":
        backends = []
        for dev in gpus.get("devices") or []:
            d = dev.get("drivers") or {}
            if d.get("cuda") is True:
                backends.append("cuda")
            if d.get("vulkan") is True:
                backends.append("vulkan")
        print("resolved_gpu_backends:", sorted(set(backends)) or ["cpu"], file=sys.stderr)
    else:
        print("resolved_gpu_backends: cpu (gpus status", gpus.get("status"), ")", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
