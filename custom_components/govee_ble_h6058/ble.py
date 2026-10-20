"""Persistent BLE link to a Govee lamp: keep-alive and automatic reconnect.

No Home Assistant imports, so the link can be tested on its own.

Why: the H6058 closes every BLE connection after about 8-11 s without traffic. Connecting per
command cost 1.5-8 s each time. A read-only status query every few seconds keeps the link open,
so commands go out at once and the replies report the lamp's power and battery state.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Iterable
import contextlib
import logging
import time

from bleak.backends.device import BLEDevice
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .protocol import CMD_FIRMWARE, CMD_POWER, parse_frame, query_frame

_LOGGER = logging.getLogger(__name__)

UUID_WRITE = "00010203-0405-0607-0809-0a0b0c0d2b11"
UUID_NOTIFY = "00010203-0405-0607-0809-0a0b0c0d2b10"

# The lamp's idle timeout is 8-11 s and a 2 s query kept the link up indefinitely;
# 3 s leaves room for two lost frames on a weak link.
KEEPALIVE_INTERVAL = 3.0
# How long a command waits for the link to come back before it fails.
CONNECT_WAIT = 25.0
# Pause between failed connection rounds (seconds), the last value repeats.
RECONNECT_DELAYS = (1, 3, 5, 10, 20, 30, 60)
# A session shorter than this counts as a failed attempt (avoids a tight connect/drop loop).
MIN_STABLE_SESSION = 3.0


class GoveeBleLink:
    """Keeps one BLE connection to the lamp alive and (re)connects in the background."""

    def __init__(
        self,
        name: str,
        get_device: Callable[[], BLEDevice | None],
        on_frame: Callable[[int, bytes], None] | None = None,
        on_state: Callable[[bool], None] | None = None,
    ) -> None:
        self._name = name
        self._get_device = get_device
        self._on_frame = on_frame
        self._on_state = on_state

        self._client: BleakClientWithServiceCache | None = None
        self._connected = asyncio.Event()
        self._drop = asyncio.Event()
        self._wake = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._last_tx = 0.0
        self._stopping = False

    @property
    def connected(self) -> bool:
        """True while the link is up."""
        return self._connected.is_set()

    # ------------------------------------------------------------------ public API

    async def run(self) -> None:
        """Supervisor loop; run as a background task until cancelled or async_stop()."""
        failures = 0
        try:
            while not self._stopping:
                device = self._get_device()
                if device is None:
                    failures += 1
                    _LOGGER.debug("%s: lamp not seen by any connectable scanner", self._name)
                    await self._backoff(failures)
                    continue
                try:
                    client = await establish_connection(
                        BleakClientWithServiceCache,
                        device,
                        self._name,
                        disconnected_callback=self._handle_disconnect,
                        ble_device_callback=self._get_device,
                        max_attempts=3,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    failures += 1
                    if failures == 5:
                        _LOGGER.warning(
                            "%s: lamp unreachable over BLE (%s), will keep retrying",
                            self._name,
                            exc,
                        )
                    else:
                        _LOGGER.debug("%s: connect failed (#%s): %s", self._name, failures, exc)
                    await self._backoff(failures)
                    continue

                if failures >= 5:
                    _LOGGER.info("%s: BLE link restored", self._name)
                failures = 0
                started = time.monotonic()
                await self._session(client)
                if self._stopping:
                    break
                if time.monotonic() - started < MIN_STABLE_SESSION:
                    # Lamp dropped us almost at once: back off instead of a tight loop.
                    failures = 1
                    await self._backoff(failures)
                else:
                    await asyncio.sleep(0.3)
        finally:
            await self._close_client()

    async def send(self, frames: Iterable[bytes], gap: float = 0.15) -> None:
        """Write frames over the live link, waiting for (re)connection if needed."""
        frames = list(frames)
        last_exc: Exception | None = None
        for _attempt in range(2):
            if not self._connected.is_set():
                self._wake.set()
                try:
                    await asyncio.wait_for(self._connected.wait(), CONNECT_WAIT)
                except TimeoutError:
                    raise ConnectionError(
                        f"{self._name}: no BLE connection after {CONNECT_WAIT:.0f}s"
                    ) from None
            client = self._client
            if client is None:
                continue
            try:
                async with self._write_lock:
                    for frame in frames:
                        await client.write_gatt_char(UUID_WRITE, frame, False)
                        self._last_tx = time.monotonic()
                        if gap:
                            await asyncio.sleep(gap)
                return
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                _LOGGER.debug("%s: write failed: %s", self._name, exc)
                self._drop.set()  # link is bad, the supervisor reconnects
                await asyncio.sleep(0.3)
        raise ConnectionError(f"{self._name}: could not send command: {last_exc}")

    async def async_stop(self) -> None:
        """Stop the supervisor and close the connection."""
        self._stopping = True
        self._wake.set()
        self._drop.set()
        await self._close_client()

    # ------------------------------------------------------------------ internals

    async def _session(self, client: BleakClientWithServiceCache) -> None:
        """Hold one connection: subscribe, query, then keep it alive until it drops."""
        self._client = client
        self._drop.clear()
        if not client.is_connected:
            self._client = None
            return
        try:
            await client.start_notify(UUID_NOTIFY, self._handle_notify)
        except Exception as exc:  # noqa: BLE001 - keep-alive still works without replies
            _LOGGER.debug("%s: could not subscribe to notifications: %s", self._name, exc)
        self._connected.set()
        self._wake.clear()
        self._fire_state(True)
        _LOGGER.debug("%s: BLE link up", self._name)
        try:
            await self._write_query(client, CMD_FIRMWARE)
            await self._write_query(client, CMD_POWER)
            while not self._stopping and not self._drop.is_set() and client.is_connected:
                due = self._last_tx + KEEPALIVE_INTERVAL - time.monotonic()
                if due <= 0:
                    await self._write_query(client, CMD_POWER)
                    continue
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(self._drop.wait(), due)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            _LOGGER.debug("%s: keep-alive failed: %s", self._name, exc)
        finally:
            self._connected.clear()
            self._client = None
            self._fire_state(False)
            _LOGGER.debug("%s: BLE link down", self._name)
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.disconnect(), 5)

    async def _write_query(self, client: BleakClientWithServiceCache, cmd: int) -> None:
        async with self._write_lock:
            await client.write_gatt_char(UUID_WRITE, query_frame(cmd), False)
            self._last_tx = time.monotonic()

    async def _backoff(self, failures: int) -> None:
        delay = RECONNECT_DELAYS[min(failures, len(RECONNECT_DELAYS)) - 1] if failures else 1
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wake.wait(), delay)
        self._wake.clear()

    def _handle_disconnect(self, client) -> None:
        if client is self._client:
            _LOGGER.debug("%s: lamp closed the BLE connection", self._name)
            self._drop.set()

    def _handle_notify(self, _char, data: bytearray) -> None:
        parsed = parse_frame(bytes(data))
        if parsed is not None and self._on_frame is not None:
            try:
                self._on_frame(*parsed)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("%s: error in frame handler", self._name)

    def _fire_state(self, connected: bool) -> None:
        if self._on_state is not None:
            try:
                self._on_state(connected)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("%s: error in state handler", self._name)

    async def _close_client(self) -> None:
        client, self._client = self._client, None
        self._connected.clear()
        if client is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.disconnect(), 5)
