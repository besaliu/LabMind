from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Union

import httpx
from fastapi import FastAPI, HTTPException, Request

from vix.scenario import Scenario
from vix.status import compute_status

logger = logging.getLogger(__name__)

MeasureHandler = Callable[[], dict[str, Any]]
CommandHandler = Union[Callable[[dict[str, Any]], dict[str, Any]],
                       Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]]


class InstrumentBase:
    """Common behaviour for every VIX mock instrument."""

    instrument_type: str = ""
    instrument_id: str = ""
    name: str = ""
    capabilities: list[str] = []

    def __init__(
        self,
        scenario: Scenario,
        port: int,
        backend_client: httpx.AsyncClient,
        interval_seconds: float = 30.0,
    ) -> None:
        if not (self.instrument_type and self.instrument_id and self.name):
            raise ValueError("Subclass must set instrument_type/instrument_id/name")
        self.scenario = scenario
        self.port = port
        self._client = backend_client
        self._interval = interval_seconds
        self._measure_handlers: dict[str, MeasureHandler] = {}
        self._command_handlers: dict[str, CommandHandler] = {}
        self.app = self._build_app()

    def register_measure(self, metric: str, handler: MeasureHandler) -> None:
        self._measure_handlers[metric] = handler

    def register_command(self, action: str, handler: CommandHandler) -> None:
        self._command_handlers[action] = handler

    def build_readings(self) -> dict[str, Any]:
        raise NotImplementedError

    async def register(self) -> None:
        payload = {
            "instrument_id": self.instrument_id,
            "type": self.instrument_type,
            "name": self.name,
            "port": self.port,
            "capabilities": list(self.capabilities),
        }
        while True:
            try:
                r = await self._client.post("/api/instruments/register", json=payload, timeout=5.0)
                if r.status_code < 300:
                    logger.info("Registered %s with backend", self.instrument_id)
                    return
                logger.warning("Register returned %s; retrying in %ss", r.status_code, self._interval)
            except httpx.HTTPError as e:
                logger.warning("Register failed: %s; retrying in %ss", e, self._interval)
            await asyncio.sleep(self._interval)

    async def analytics_loop(self) -> None:
        while True:
            try:
                readings = self.build_readings()
                payload = {
                    "instrument_id": self.instrument_id,
                    "timestamp": self._now(),
                    "readings": readings,
                    "status": compute_status(readings, self.scenario.thresholds),
                }
                r = await self._client.post("/api/analytics", json=payload, timeout=5.0)
                if r.status_code == 409:
                    logger.debug("Analytics 409 (no active experiment) — keep streaming")
                elif r.status_code >= 300:
                    logger.warning("Analytics POST returned %s", r.status_code)
            except httpx.HTTPError as e:
                logger.warning("Analytics POST failed: %s", e)
            except Exception as e:
                logger.exception("Unexpected error in analytics loop: %s", e)
            await asyncio.sleep(self._interval)

    def _build_app(self) -> FastAPI:
        app = FastAPI()

        @app.get("/health")
        def health() -> dict[str, str]:
            return {"status": "ok", "instrument_id": self.instrument_id}

        @app.get("/measure/{metric}")
        def measure(metric: str) -> dict[str, Any]:
            handler = self._measure_handlers.get(metric)
            if handler is None:
                raise HTTPException(404, f"Unknown metric {metric!r}")
            return handler()

        @app.post("/command/{action}")
        async def command(action: str, request: Request) -> dict[str, Any]:
            handler = self._command_handlers.get(action)
            if handler is None:
                raise HTTPException(404, f"Unknown command {action!r}")
            body = await request.json() if await request.body() else {}
            result = handler(body)
            if inspect.isawaitable(result):
                result = await result
            return result

        @app.post("/scenario/phase")
        async def scenario_phase(request: Request) -> dict[str, Any]:
            body = await request.json()
            phase = body.get("phase")
            try:
                self.scenario.set_phase(phase)
            except ValueError as e:
                raise HTTPException(400, str(e))
            return {"ok": True, "phase": phase}

        return app

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
