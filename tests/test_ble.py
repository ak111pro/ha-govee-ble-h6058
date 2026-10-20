"""The persistent BLE link against a fake Bleak client (no Bluetooth needed)."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from bleak.backends.device import BLEDevice
import pytest

from custom_components.govee_ble_h6058 import ble
from custom_components.govee_ble_h6058.protocol import build_frame, power_frame, query_frame


class FakeClient:
    """Records writes; answers the status query like an H6058."""

    def __init__(self, disconnected_callback):
        self.is_connected = True
        self.writes: list[bytes] = []
        self._notify = None
        self._disconnected_callback = disconnected_callback

    async def start_notify(self, _uuid, callback):
        self._notify = callback

    async def write_gatt_char(self, uuid, data, response):
        assert uuid == ble.UUID_WRITE
        self.writes.append(bytes(data))
        if self._notify and bytes(data) == query_frame(0x01):
            self._notify(None, bytearray(build_frame(0xAA, 0x01, [0x01, 0x00, 0x5C])))

    async def disconnect(self):
        self.is_connected = False

    def drop(self):
        self.is_connected = False
        self._disconnected_callback(self)


@pytest.fixture
def fast_keepalive():
    with patch.object(ble, "KEEPALIVE_INTERVAL", 0.05):
        yield


async def _start(frames, states):
    clients: list[FakeClient] = []

    async def fake_establish(_cls, _device, _name, disconnected_callback, **_kwargs):
        client = FakeClient(disconnected_callback)
        clients.append(client)
        return client

    link = ble.GoveeBleLink(
        "Test lamp",
        lambda: BLEDevice("A1:B2:C3:D4:E5:F6", "Govee_H6058_E5F6", None),
        on_frame=lambda cmd, payload: frames.append((cmd, payload)),
        on_state=states.append,
    )
    patcher = patch.object(ble, "establish_connection", fake_establish)
    patcher.start()
    task = asyncio.create_task(link.run())
    for _ in range(100):
        if link.connected:
            break
        await asyncio.sleep(0.01)
    return link, task, clients, patcher


async def _stop(link, task, patcher):
    await link.async_stop()
    await asyncio.wait_for(task, 2)
    patcher.stop()


async def test_connects_queries_and_parses_replies(fast_keepalive):
    frames, states = [], []
    link, task, clients, patcher = await _start(frames, states)
    try:
        assert link.connected
        assert states == [True]
        await asyncio.sleep(0.2)
        writes = clients[0].writes
        assert writes[0] == query_frame(0x06)  # firmware first
        assert writes.count(query_frame(0x01)) >= 3  # keep-alive keeps querying
        assert frames[0] == (0x01, bytes([0x01, 0x00, 0x5C]) + bytes(14))
    finally:
        await _stop(link, task, patcher)
    assert states[-1] is False


async def test_send_writes_frames(fast_keepalive):
    link, task, clients, patcher = await _start([], [])
    try:
        await link.send([power_frame(True)], gap=0)
        assert power_frame(True) in clients[0].writes
    finally:
        await _stop(link, task, patcher)


async def test_reconnects_after_the_lamp_drops_the_link(fast_keepalive):
    states: list[bool] = []
    with patch.object(ble, "MIN_STABLE_SESSION", 0):
        link, task, clients, patcher = await _start([], states)
        try:
            await asyncio.sleep(0.1)
            clients[0].drop()
            for _ in range(200):
                if len(clients) == 2 and link.connected:
                    break
                await asyncio.sleep(0.01)
            assert len(clients) == 2
            assert link.connected
            assert states[:3] == [True, False, True]
            await link.send([power_frame(False)], gap=0)
            assert power_frame(False) in clients[1].writes
        finally:
            await _stop(link, task, patcher)


async def test_send_fails_when_the_lamp_stays_unreachable():
    link = ble.GoveeBleLink("Test lamp", lambda: None)
    with patch.object(ble, "CONNECT_WAIT", 0.05), pytest.raises(ConnectionError):
        await link.send([power_frame(True)])
