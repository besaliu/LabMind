"""LabMind FastMCP server.

Exposes core tools to the OpenClaw agent and dynamically registers
instrument-specific tools from YAML catalog entries via a file watcher.
"""
import asyncio
import inspect
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx
import yaml
from fastmcp import FastMCP

import storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")


@asynccontextmanager
async def _lifespan(server):
    for yaml_path in storage.list_catalog_yamls():
        _register_catalog(str(yaml_path))
    asyncio.create_task(_watch_catalog())
    yield


mcp = FastMCP("labmind", lifespan=_lifespan)

# Track which catalog files and tool names have been registered
_registered_catalogs: set = set()
_registered_tool_names: set = set()


def get_registered_tool_names() -> set:
    """Return the set of dynamically registered tool names (for testing)."""
    return _registered_tool_names


# ---------------------------------------------------------------------------
# Core tools — always available at startup
# ---------------------------------------------------------------------------

@mcp.tool()
def get_experiment(run_id: str) -> Dict[str, Any]:
    """Return experiment metadata and current status."""
    try:
        return storage.read_metadata(run_id)
    except FileNotFoundError:
        return {"error": f"Run '{run_id}' not found"}


@mcp.tool()
def get_temperature_curve(run_id: str) -> List[Dict[str, str]]:
    """Return all temperature readings for a run."""
    return storage.read_csv(run_id, "temp.csv")


@mcp.tool()
def get_impurity_log(run_id: str) -> List[Dict[str, str]]:
    """Return all impurity/pH readings for a run."""
    return storage.read_csv(run_id, "impurity.csv")


@mcp.tool()
def get_microscopy_log(run_id: str) -> List[Dict[str, str]]:
    """Return all microscopy quality readings (clarity_pct, defect_count) for a run."""
    return storage.read_csv(run_id, "microscopy.csv")


@mcp.tool()
def get_microscopy_image(run_id: str) -> Dict[str, Any]:
    """Return the latest microscopy image as base64-encoded PNG."""
    b64 = storage.read_image_b64(run_id)
    if b64 is None:
        return {"error": "No microscopy image found for this run"}
    return {"run_id": run_id, "image_b64": b64, "format": "png"}


@mcp.tool()
def compare_runs(run_a: str, run_b: str) -> Dict[str, Any]:
    """Side-by-side comparison of key metrics between two runs."""
    def _summarise(run_id: str) -> Dict[str, Any]:
        try:
            meta = storage.read_metadata(run_id)
            temp_rows = storage.read_csv(run_id, "temp.csv")
            imp_rows = storage.read_csv(run_id, "impurity.csv")
            temps = [float(r["temperature_c"]) for r in temp_rows if r.get("temperature_c")]
            imps = [float(r["impurity_ppm"]) for r in imp_rows if r.get("impurity_ppm")]
            phs = [float(r["ph"]) for r in imp_rows if r.get("ph")]
            return {
                "run_id": run_id,
                "hypothesis": meta.get("hypothesis", ""),
                "status": meta.get("status"),
                "outcome": meta.get("outcome"),
                "interventions": len(storage.read_interventions(run_id)),
                "temp_mean_c": round(sum(temps) / len(temps), 2) if temps else None,
                "temp_max_c": max(temps) if temps else None,
                "impurity_mean_ppm": round(sum(imps) / len(imps), 2) if imps else None,
                "impurity_max_ppm": max(imps) if imps else None,
                "ph_mean": round(sum(phs) / len(phs), 2) if phs else None,
            }
        except Exception as e:
            return {"run_id": run_id, "error": str(e)}

    return {"run_a": _summarise(run_a), "run_b": _summarise(run_b)}



@mcp.tool()
def log_intervention(run_id: str, action: str, reasoning: str) -> Dict[str, Any]:
    """Append an agent action to the experiment's intervention log."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "action": action,
        "reasoning": reasoning,
    }
    try:
        storage.append_intervention(run_id, entry)
        return {"ok": True, "entry": entry}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@mcp.tool()
async def finalize_experiment(
    run_id: str,
    report: str,
    outcome: str,
    key_findings: List[str],
) -> Dict[str, Any]:
    """Persist the morning report with structured front matter and notify the backend.

    Writes report.md with a YAML front matter block (extracted from metadata.yaml)
    prepended to the agent's narrative report. The front matter is what future
    list_experiment_reports() calls use for parameter comparison.

    Args:
        run_id: The experiment run ID to finalize.
        report: Full markdown report text generated by the agent (no front matter needed).
        outcome: One of 'success', 'partial_failure', 'failure'.
        key_findings: 3-5 bullet points summarising the run.
    """
    try:
        meta = storage.read_metadata(run_id)
    except FileNotFoundError:
        return {"ok": False, "error": f"Run '{run_id}' not found"}

    params = meta.get("parameters", {})
    fm: Dict[str, Any] = {
        "run_id": run_id,
        "experiment_type": meta.get("experiment_type", ""),
        "substrate": params.get("substrate"),
        "target_temp_c": params.get("target_temp_c"),
        "cooling_rate_c_per_hour": params.get("cooling_rate_c_per_hour"),
        "buffer_additive": params.get("buffer_additive"),
        "outcome": outcome,
        "key_findings": key_findings,
    }
    fm_yaml = yaml.dump(fm, default_flow_style=False, allow_unicode=True)
    enriched_report = f"---\n{fm_yaml}---\n\n{report}"

    written = storage.write_report(run_id, enriched_report)
    if not written:
        return {"ok": False, "error": "Report already exists — experiment already finalized"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                f"{BACKEND_URL}/api/experiments/{run_id}/finalize",
                json={"report": report, "outcome": outcome, "key_findings": key_findings},
            )
            backend_ok = resp.status_code == 200
    except Exception:
        backend_ok = False

    return {"ok": True, "backend_updated": backend_ok, "run_id": run_id}


@mcp.tool()
def list_experiment_reports() -> List[Dict[str, Any]]:
    """Return all completed experiment reports with structured front matter and narrative body.

    Each entry contains:
      - run_id: str
      - front_matter: dict with keys run_id, experiment_type, substrate, target_temp_c,
                      cooling_rate_c_per_hour, buffer_additive, outcome, key_findings
      - body: str — the full narrative report markdown

    Use this tool for:
    1. Similarity check before starting a new experiment (compare front_matter params)
    2. Answering researcher questions about past experiments (read body content)

    Reports without front matter (legacy format) are returned with an empty front_matter dict.
    """
    results = []
    for run_id in storage.list_run_ids():
        content = storage.read_report(run_id)
        if content is None:
            continue
        front_matter: Dict[str, Any] = {}
        body = content
        if content.startswith("---"):
            parts = content[3:].split("---", 1)
            if len(parts) == 2:
                try:
                    front_matter = yaml.safe_load(parts[0]) or {}
                    body = parts[1].strip()
                except Exception:
                    pass
        results.append({"run_id": run_id, "front_matter": front_matter, "body": body})
    return results


@mcp.tool()
def execute_code(code: str) -> Dict[str, Any]:
    """Define and register a new MCP tool from Python code.

    Write a complete Python function (sync or async). It will be registered
    as an MCP tool under its defined name and immediately callable.

    Available in namespace: httpx, Any, Dict, List, Optional.

    Example:
        async def my_sensor_read() -> Dict[str, Any]:
            async with httpx.AsyncClient() as c:
                r = await c.get("http://localhost:9000/measure")
                return r.json()
    """
    import types

    namespace: Dict[str, Any] = {
        "httpx": httpx,
        "Any": Any,
        "Dict": Dict,
        "List": List,
        "Optional": Optional,
        "asyncio": asyncio,
    }
    before = set(namespace.keys())
    try:
        exec(compile(code, "<dynamic>", "exec"), namespace)
    except SyntaxError as e:
        return {"ok": False, "error": f"Syntax error: {e}"}
    except Exception as e:
        return {"ok": False, "error": f"Exec error: {e}"}

    new_fns = [
        (n, obj)
        for n, obj in namespace.items()
        if n not in before and callable(obj) and isinstance(obj, types.FunctionType)
    ]
    if not new_fns:
        return {"ok": False, "error": "No function defined in submitted code"}

    registered = []
    for name, fn in new_fns:
        mcp.tool()(fn)
        _registered_tool_names.add(name)
        registered.append(name)
        log.info("execute_code registered tool: %s", name)

    return {
        "ok": True,
        "registered_tools": registered,
        "message": f"Registered {len(registered)} tool(s): {registered}. You can call them immediately.",
    }


# ---------------------------------------------------------------------------
# Dynamic instrument tool registration via catalog YAML watcher
# ---------------------------------------------------------------------------

def _register_catalog(path: str) -> None:
    """Parse a catalog YAML and register one MCP tool per command."""
    try:
        spec = yaml.safe_load(open(path))
    except Exception as e:
        log.error("Invalid catalog YAML %s: %s", path, e)
        return

    if not isinstance(spec, dict):
        log.error("Catalog %s did not parse to a dict — skipping", path)
        return

    instrument_type = spec.get("instrument_type")
    endpoint_pattern = spec.get("endpoint_pattern", "http://localhost:{port}")
    port = spec.get("port", 8100)
    commands = spec.get("commands", {})

    if not instrument_type or not commands:
        log.warning("Catalog %s missing instrument_type or commands — skipping", path)
        return

    endpoint = endpoint_pattern.replace("{port}", str(port))

    for cmd_name, cmd_spec in commands.items():
        tool_name = f"{instrument_type}_{cmd_name}"
        method = cmd_spec.get("method", "GET").upper()
        cmd_path = cmd_spec.get("path", "/")
        params = cmd_spec.get("params") or []

        # Build a typed signature string for the docstring
        param_names = [p["name"] if isinstance(p, dict) else p for p in params]

        def _make_tool(
            _endpoint: str = endpoint,
            _method: str = method,
            _path: str = cmd_path,
            _param_names: list = param_names,
            _tool_name: str = tool_name,
        ):
            async def tool_fn(**kwargs: Any) -> Any:
                url = f"{_endpoint}{_path}"
                try:
                    async with httpx.AsyncClient(timeout=10.0) as client:
                        if _method == "GET":
                            r = await client.get(url, params=kwargs)
                        else:
                            r = await client.request(_method, url, json=kwargs)
                        return r.json()
                except Exception as e:
                    return {"error": str(e), "instrument_endpoint": url}

            tool_fn.__name__ = _tool_name
            tool_fn.__doc__ = (
                f"Call {instrument_type} command '{cmd_name}' at {_endpoint}. "
                f"Params: {_param_names or 'none'}."
            )
            # FastMCP rejects **kwargs — patch __signature__ with explicit
            # POSITIONAL_OR_KEYWORD params. inspect.signature() returns this
            # override so validation passes; Python still routes call args into
            # the real **kwargs body at runtime.
            # FastMCP/Pydantic validate via inspect.signature AND __annotations__
            sig_params = [
                inspect.Parameter(n, inspect.Parameter.POSITIONAL_OR_KEYWORD, annotation=Any)
                for n in _param_names
            ]
            tool_fn.__signature__ = inspect.Signature(sig_params)
            tool_fn.__annotations__ = {n: Any for n in _param_names}
            tool_fn.__annotations__["return"] = Any
            return tool_fn

        mcp.tool()(_make_tool())  # FastMCP 2.14+: tool() decorator handles Tool wrapping
        _registered_tool_names.add(tool_name)
        log.info("Registered tool: %s → %s %s%s", tool_name, method, endpoint, cmd_path)

    _registered_catalogs.add(path)


async def _watch_catalog() -> None:
    """Watch the instrument catalog directory for new/changed YAML files."""
    from watchfiles import awatch

    catalog_dir = str(storage._catalog_dir())
    log.info("Watching catalog directory: %s", catalog_dir)

    async for changes in awatch(catalog_dir):
        for _, changed_path in changes:
            if changed_path.endswith((".yaml", ".yml")):
                log.info("Catalog change detected: %s", changed_path)
                _register_catalog(changed_path)


if __name__ == "__main__":
    port = int(os.environ.get("MCP_PORT", "8001"))
    mcp.run(transport="sse", host="0.0.0.0", port=port)
