"""Govee BLE frame format and command builders. No Home Assistant imports.

Every frame is 20 bytes: a head byte (0x33 command, 0xAA query/reply), a command byte, the
payload, zero padding and an XOR checksum over the first 19 bytes.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import math

HEAD_COMMAND = 0x33
HEAD_QUERY = 0xAA

CMD_POWER = 0x01
CMD_BRIGHTNESS = 0x04
CMD_COLOR = 0x05
CMD_FIRMWARE = 0x06

# Colour mode "manual 2" of the RGBWW lamps: RGB and colour temperature in one command.
MODE_RGBWW = 0x0D


def checksum(data: Iterable[int]) -> int:
    """XOR of all bytes."""
    value = 0
    for byte in data:
        value ^= byte
    return value & 0xFF


def build_frame(head: int, cmd: int, payload: Iterable[int] = ()) -> bytes:
    """Build a 20-byte frame: head, cmd, payload, zero padding, XOR checksum."""
    body = bytes([head & 0xFF, cmd & 0xFF]) + bytes(payload)
    if len(body) > 19:
        raise ValueError("payload too long")
    body += bytes(19 - len(body))
    return body + bytes([checksum(body)])


def parse_frame(data: bytes) -> tuple[int, bytes] | None:
    """Return (cmd, 17-byte payload) for a valid 0xAA reply, else None."""
    if len(data) != 20 or data[0] != HEAD_QUERY:
        return None
    if checksum(data[:19]) != data[19]:
        return None
    return data[1], bytes(data[2:19])


def query_frame(cmd: int) -> bytes:
    """Read-only query; the lamp answers with a 0xAA frame of the same command."""
    return build_frame(HEAD_QUERY, cmd)


def power_frame(on: bool) -> bytes:
    """Switch the lamp on or off."""
    return build_frame(HEAD_COMMAND, CMD_POWER, [0x01 if on else 0x00])


def brightness_frame(brightness: int, brightness_max: int) -> bytes:
    """Brightness from Home Assistant's 1-255 scale to the lamp's 1-`brightness_max` scale.

    Never sends 0, so the lowest Home Assistant brightness stays the lamp's lowest step.
    """
    brightness = max(0, min(255, int(brightness)))
    value = round(brightness / 255 * brightness_max)
    return build_frame(HEAD_COMMAND, CMD_BRIGHTNESS, [max(1, min(brightness_max, value))])


def rgb_frame(red: int, green: int, blue: int) -> bytes:
    """RGB colour in mode 0x0D."""
    return build_frame(HEAD_COMMAND, CMD_COLOR, [MODE_RGBWW, red & 0xFF, green & 0xFF, blue & 0xFF])


def kelvin_to_rgb(kelvin: int) -> tuple[int, int, int]:
    """Approximate RGB of a colour temperature (Tanner Helland's algorithm)."""
    temp = max(1000, min(40000, kelvin)) / 100.0

    if temp <= 66:
        red = 255.0
        green = 99.4708025861 * math.log(temp) - 161.1195681661
    else:
        red = 329.698727446 * ((temp - 60) ** -0.1332047592)
        green = 288.1221695283 * ((temp - 60) ** -0.0755148492)

    if temp >= 66:
        blue = 255.0
    elif temp <= 19:
        blue = 0.0
    else:
        blue = 138.5177312231 * math.log(temp - 10) - 305.0447927307

    return tuple(int(max(0, min(255, c))) for c in (red, green, blue))  # type: ignore[return-value]


def color_temp_frame(kelvin: int) -> bytes:
    """White at a colour temperature in mode 0x0D.

    Layout: RGB forced to white, Kelvin as two bytes (big endian), then the white tone as RGB.
    """
    kelvin = max(0, min(0xFFFF, int(kelvin)))
    white = kelvin_to_rgb(kelvin)
    return build_frame(
        HEAD_COMMAND,
        CMD_COLOR,
        [MODE_RGBWW, 0xFF, 0xFF, 0xFF, (kelvin >> 8) & 0xFF, kelvin & 0xFF, *white],
    )


@dataclass(frozen=True)
class StatusReading:
    """Decoded reply to the 0xAA 0x01 query."""

    power: bool | None
    # Third payload byte, only meaningful on battery lamps (H6058).
    status_byte: int
    battery: int | None
    charging: bool
    plugged: bool

    @property
    def charge_state(self) -> str:
        """'charging', 'full' (plugged in, not charging) or 'unplugged'."""
        if self.charging:
            return "charging"
        return "full" if self.plugged else "unplugged"


def decode_status(payload: bytes) -> StatusReading:
    """Decode the payload of a 0xAA 0x01 reply.

    Byte 0 is the power state (1 on, 0 off). On the H6058 byte 2 is a status byte, measured
    on a real lamp: bit 7 = charging, bit 2 = external power connected, low 7 bits = a rough
    battery level (it plateaus around 84 while charging and reads 92 when full on the charger).
    """
    power = bool(payload[0]) if payload[0] in (0, 1) else None
    status = payload[2]
    level = status & 0x7F
    return StatusReading(
        power=power,
        status_byte=status,
        battery=level if level <= 100 else None,
        charging=bool(status & 0x80),
        plugged=bool(status & 0x04),
    )


def decode_firmware(payload: bytes) -> str | None:
    """ASCII version string of a 0xAA 0x06 reply, for example '1.01.11'."""
    text = bytes(payload).split(b"\x00")[0].decode("ascii", errors="ignore").strip()
    return text if text and text.isprintable() else None
