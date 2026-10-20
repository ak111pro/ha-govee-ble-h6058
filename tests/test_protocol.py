"""Frame building, checksums and reply decoding."""

from __future__ import annotations

import pytest

from custom_components.govee_ble_h6058.const import MODELS, model_from_name
from custom_components.govee_ble_h6058.protocol import (
    brightness_frame,
    build_frame,
    checksum,
    color_temp_frame,
    decode_firmware,
    decode_status,
    kelvin_to_rgb,
    parse_frame,
    power_frame,
    query_frame,
    rgb_frame,
)


def test_frame_is_20_bytes_with_xor_checksum():
    frame = build_frame(0x33, 0x01, [0x01])
    assert len(frame) == 20
    assert frame[:3] == bytes([0x33, 0x01, 0x01])
    assert frame[3:19] == bytes(16)
    assert frame[19] == checksum(frame[:19]) == 0x33 ^ 0x01 ^ 0x01


def test_payload_too_long():
    with pytest.raises(ValueError):
        build_frame(0x33, 0x05, range(18))


@pytest.mark.parametrize(
    ("on", "expected"),
    [
        (True, "3301010000000000000000000000000000000033"),
        (False, "3301000000000000000000000000000000000032"),
    ],
)
def test_power(on, expected):
    assert power_frame(on).hex() == expected


@pytest.mark.parametrize(
    ("ha", "maximum", "lamp"),
    [
        (255, 100, 100),
        (128, 100, 50),  # verified on the H6058: 50 % on the lamp
        (26, 100, 10),
        (51, 100, 20),
        (1, 100, 1),  # never 0
        (0, 100, 1),
        (255, 255, 255),
        (128, 255, 128),
    ],
)
def test_brightness_scaling(ha, maximum, lamp):
    frame = brightness_frame(ha, maximum)
    assert frame[:2] == bytes([0x33, 0x04])
    assert frame[2] == lamp
    assert frame[19] == checksum(frame[:19])


def test_rgb_red_matches_the_frame_verified_on_the_lamp():
    assert rgb_frame(255, 0, 0).hex().upper() == "33050DFF000000000000000000000000000000C4"


def test_color_temp_layout():
    frame = color_temp_frame(4000)
    assert frame[:6] == bytes([0x33, 0x05, 0x0D, 0xFF, 0xFF, 0xFF])
    assert frame[6:8] == (4000).to_bytes(2, "big")
    assert tuple(frame[8:11]) == kelvin_to_rgb(4000)
    assert frame[19] == checksum(frame[:19])


def test_color_temp_2700():
    # Warm white as sent to the H6058 (2700 K = 0x0A8C).
    assert color_temp_frame(2700).hex().upper() == "33050DFFFFFF0A8CFFA65700000000000000004C"


@pytest.mark.parametrize(
    ("kelvin", "expected"),
    [
        (6600, (255, 255, 255)),
        (6500, (255, 254, 250)),
        (4000, (255, 205, 166)),
        (2700, (255, 166, 87)),
        (2200, (255, 146, 39)),
        (1000, (255, 67, 0)),
    ],
)
def test_kelvin_to_rgb(kelvin, expected):
    # Same values as the integration this one was built from (Tanner Helland's algorithm).
    assert kelvin_to_rgb(kelvin) == expected


def test_kelvin_to_rgb_warm_is_redder_than_cold():
    warm, cold = kelvin_to_rgb(2200), kelvin_to_rgb(6500)
    assert warm[2] < cold[2]
    assert all(0 <= c <= 255 for c in warm + cold)


def test_query_and_parse_roundtrip():
    assert query_frame(0x01).hex() == "aa010000000000000000000000000000000000ab"
    reply = build_frame(0xAA, 0x01, [0x01, 0x00, 0x5C])
    assert parse_frame(reply) == (0x01, bytes([0x01, 0x00, 0x5C]) + bytes(14))


def test_parse_rejects_bad_frames():
    good = build_frame(0xAA, 0x01, [0x01])
    assert parse_frame(good[:19]) is None
    assert parse_frame(build_frame(0x33, 0x01, [0x01])) is None
    assert parse_frame(good[:19] + bytes([good[19] ^ 0xFF])) is None


@pytest.mark.parametrize(
    ("raw", "power", "battery", "charging", "plugged", "state"),
    [
        # All seven readings taken on a real H6058.
        ("00005c", False, 92, False, True, "full"),
        ("010050", True, 80, False, False, "unplugged"),
        ("0100d4", True, 84, True, True, "charging"),
        ("010040", True, 64, False, False, "unplugged"),
    ],
)
def test_decode_status(raw, power, battery, charging, plugged, state):
    status = decode_status(bytes.fromhex(raw) + bytes(14))
    assert status.power is power
    assert status.battery == battery
    assert status.charging is charging
    assert status.plugged is plugged
    assert status.charge_state == state


def test_decode_status_unknown_values():
    status = decode_status(bytes([0x07, 0x00, 0x7F]) + bytes(14))
    assert status.power is None
    assert status.battery is None


def test_decode_firmware():
    assert decode_firmware(b"1.01.11" + bytes(10)) == "1.01.11"
    assert decode_firmware(bytes(17)) is None


@pytest.mark.parametrize(
    ("name", "model"),
    [
        ("Govee_H6058_E5F6", "H6058"),
        ("ihoment_H6159_1A2B", "H6159"),
        ("GBK_H613A_0001", "H613A"),
        ("govee_h613d_0001", "H613D"),
        ("Govee_H617C_4253", None),
        ("Govee_H60580_1234", None),
        ("H6058", None),
        (None, None),
    ],
)
def test_model_from_name(name, model):
    assert model_from_name(name) == model


def test_only_h6058_is_tested_and_has_a_battery():
    assert [m for m, info in MODELS.items() if info.tested] == ["H6058"]
    assert [m for m, info in MODELS.items() if info.has_battery] == ["H6058"]
