"""Constants and the supported model table."""

from __future__ import annotations

from dataclasses import dataclass
import re

DOMAIN = "govee_ble_h6058"

CONF_MODEL = "model"


@dataclass(frozen=True)
class ModelInfo:
    """What the integration knows about one Govee model."""

    model: str
    # True only for models confirmed on real hardware by the maintainer.
    tested: bool
    # Upper end of the brightness command (0x33 0x04 <value>): 100 or 255.
    brightness_max: int
    min_kelvin: int = 2200
    max_kelvin: int = 6500
    # The lamp has a battery and reports it in the third byte of the 0xAA 0x01 reply.
    has_battery: bool = False


# All models use the 0x0D colour mode (RGB plus colour temperature on one command).
# H6058: tested by the maintainer.
# H6008, H613A, H613D: 0x0D mode and 0-100 brightness per hardcpp/GoveeBleMqttServer.
# H6159: 0x0D mode per hardcpp/GoveeBleMqttServer ("H6159r2", second hardware revision), which
#   sends brightness as 0-255 for it. Untested here.
MODELS: dict[str, ModelInfo] = {
    "H6058": ModelInfo("H6058", tested=True, brightness_max=100, has_battery=True),
    "H6008": ModelInfo("H6008", tested=False, brightness_max=100),
    "H613A": ModelInfo("H613A", tested=False, brightness_max=100),
    "H613D": ModelInfo("H613D", tested=False, brightness_max=100),
    "H6159": ModelInfo("H6159", tested=False, brightness_max=255),
}

# Govee lamps advertise "<prefix>_<model>_<last 4 hex digits of the MAC>",
# for example "Govee_H6058_E5F6". Older firmware uses "ihoment_", some models "GBK_".
NAME_PREFIXES = ("Govee", "ihoment", "GBK")
_NAME_RE = re.compile(r"^(?:Govee|ihoment|GBK)_(H[0-9A-Z]{4})(?:_|$)", re.IGNORECASE)


def model_from_name(name: str | None) -> str | None:
    """Return the supported model in an advertised local name, or None."""
    if not name:
        return None
    match = _NAME_RE.match(name)
    if match is None:
        return None
    model = match.group(1).upper()
    return model if model in MODELS else None
