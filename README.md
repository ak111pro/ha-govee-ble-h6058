# Govee BLE H6058 for Home Assistant

[![Validate](https://github.com/ak111pro/ha-govee-ble-h6058/actions/workflows/validate.yml/badge.svg)](https://github.com/ak111pro/ha-govee-ble-h6058/actions/workflows/validate.yml)
[![Tests](https://github.com/ak111pro/ha-govee-ble-h6058/actions/workflows/tests.yml/badge.svg)](https://github.com/ak111pro/ha-govee-ble-h6058/actions/workflows/tests.yml)
[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://hacs.xyz)

> [!NOTE]
> **AI-generated.** This integration was written by an AI assistant (Claude, by Anthropic) for
> its owner [@ak111pro](https://github.com/ak111pro). It has been in daily use with a Govee
> H6058 on a real Home Assistant installation since 2026-09-30 (as a private integration, then
> published as this one). Please report problems as issues.

This integration was built specifically for the **Govee H6058** (StarPal Pro portable table
lamp). That model has **no Govee "LAN control" / local API option**, and the cloud route
(govee2mqtt and the Govee cloud API) was too slow for daily use. So this integration talks to
the lamp **directly over Bluetooth**, fully local, and was tuned for this model to work
reliably: it keeps **one persistent connection** open with a small keep-alive query, so
commands reach the lamp at once instead of after the 4-10 s it took to connect for every
command.

## Features

- Set up in the UI: **Bluetooth discovery**, a list of discovered lamps, or a **manual MAC
  address**; one config entry (and device) per lamp, several lamps supported
- **Light** with on/off, brightness, **RGB colour** and **colour temperature** (2200-6500 K)
- **Persistent BLE link** with a keep-alive every 3 s and automatic reconnect with back-off
  (the H6058 closes an idle connection after about 8-11 s)
- The light **follows the lamp's real power state** (physical button, after a restart); after
  a command the commanded state is held for a few seconds, so a reply already in flight cannot
  flip it back
- H6058 only: **battery**, **charging** and **plugged in** sensors (diagnostic), read from the
  same keep-alive reply
- **Firmware version** on the device page
- English and German translations, diagnostics download (MAC address redacted)

## Supported models

| Model | Status | Notes |
| --- | --- | --- |
| H6058 | **Tested** | Daily use by the maintainer; light, battery, charging, plugged in |
| H6008 | Untested | Same colour mode (0x0D) and 0-100 brightness per the reference projects |
| H613A | Untested | Same colour mode (0x0D) and 0-100 brightness per the reference projects |
| H613D | Untested | Same colour mode (0x0D) and 0-100 brightness per the reference projects |
| H6159 | Untested | 0x0D colour mode is documented for the second hardware revision ("H6159r2"), with 0-255 brightness; the first revision may need a different colour mode |

The untested models use exactly the same code path as the H6058 (except the brightness scale
listed above). They are mains-powered, so they get only the light, no battery entities.

**Please report how your lamp behaves**, whether it works or not: open a
[Device report](https://github.com/ak111pro/ha-govee-ble-h6058/issues/new?template=device_report.yml)
with the model, firmware, what works and what fails, and a debug log. Reports decide which
models get marked as supported. Other Govee models are not discovered and not offered; if you
have one that uses the same protocol, a device report is welcome too.

## Installation

### HACS (custom repository)

1. In HACS open the three-dot menu, choose **Custom repositories**.
2. Add `https://github.com/ak111pro/ha-govee-ble-h6058` with category **Integration**.
3. Search for **Govee BLE H6058** in HACS, download it and restart Home Assistant.

### Manual

Copy the folder `custom_components/govee_ble_h6058` of this repository into the
`custom_components` folder of your Home Assistant configuration and restart Home Assistant.

Requires Home Assistant 2025.8.0 or newer.

## Setup

- **Discovery:** once the lamp is in Bluetooth range, Home Assistant shows a discovered
  *Govee_H6058_XXXX* card under **Settings > Devices & services**. Click **Add** and confirm.
- **By hand:** **Settings > Devices & services > Add integration > Govee BLE H6058**. Pick one
  of the discovered lamps, or enter the MAC address and choose the model. The last four
  characters of the advertised name are the end of the MAC address.

Close the Govee app first: the lamp accepts only one Bluetooth connection at a time.

The device is named like the lamp's advertisement (for example *Govee H6058 E5F6*); rename it
on the device page and Home Assistant offers to rename the entity ids as well.

## Bluetooth requirements

- A **local Bluetooth adapter** of the Home Assistant host, or an **ESPHome Bluetooth proxy
  with active connections** (`bluetooth_proxy: active: true`) in range of the lamp. Passive
  proxies only see the advertisements and cannot control the lamp.
- The integration holds **one connection slot** of that adapter or proxy permanently.
- Because the lamp is connected the whole time, it **stops advertising**: it does not show up
  on Home Assistant's Bluetooth advertisement monitor or map while the integration runs. That
  is expected and not a fault.

## Entities

| Entity | Type | Description |
| --- | --- | --- |
| *(device name)* | light | On/off, brightness, RGB, colour temperature |
| Battery | sensor (diagnostic) | H6058 only. Rough level (the Govee app shows only a coarse icon); plateaus around 84 % while charging and reads 92 % when full on the charger. Attributes `raw_status_byte`, `charge_state` (`charging` / `full` / `unplugged`), `charging` |
| Charging | binary sensor (diagnostic) | H6058 only. Matches the Govee app's charging icon |
| Plugged in | binary sensor (diagnostic) | H6058 only. External power connected; plugged in and not charging means full |

Brightness and colour are not read back from the lamp: after a restart, or when they are
changed with the button or the app, Home Assistant shows the last values it set.

## Limitations

- **One controller at a time.** While Home Assistant holds the connection, the Govee app
  cannot connect to the lamp over Bluetooth (and vice versa). Disable the integration entry
  when you need the app.
- **Responsiveness over battery runtime** (H6058 on battery): the lamp stays connected all the
  time so every command lands at once. That keeps its Bluetooth radio busy, so the battery runs
  down somewhat faster than on an unconnected lamp. This is a deliberate choice.
- **No scenes or effects**, no music mode, no segment control.
- The battery value is a rough, undocumented reading from the lamp's status reply, not a
  calibrated percentage.

## Privacy

Everything stays local between Home Assistant and the lamp. The integration contacts no
external service and has no telemetry or analytics. You can block the lamp's internet access
in your router; Bluetooth control keeps working.

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements_test.txt
pytest
ruff check custom_components tests && ruff format --check custom_components tests
```

The tests use a mocked Bluetooth link and never connect to a real lamp.

## Credits

Thank you to the people whose work made this possible:

- **[Beshelmek/govee_ble_lights](https://github.com/Beshelmek/govee_ble_lights)** (MIT,
  Copyright (c) 2021 Vladimir Votyakov). This integration started as a fork of it. Taken: the
  20-byte frame format with XOR checksum, the command bytes for power, brightness and colour,
  the GATT characteristic and the structure of the original Home Assistant integration. It was
  then rewritten for a single model class (persistent link, colour temperature, battery).
- **[hardcpp/GoveeBleMqttServer](https://github.com/hardcpp/GoveeBleMqttServer)** (MIT,
  Copyright (c) 2022 HardCPP). Taken: colour mode **0x0D** for RGBWW lamps with its payload
  layout (RGB, Kelvin as two bytes, white RGB), the 0-100 brightness scale of this model class
  and the list of models that use this mode (H6008, H613A, H613D, H6159r2). The white tone is
  computed with Tanner Helland's Kelvin-to-RGB algorithm, which that project uses as well.
- **[gilcu3/govee-btled-H613B](https://github.com/gilcu3/govee-btled-H613B)** (Apache-2.0).
  Independently confirmed mode 0x0D and the colour-temperature frame from captured app
  traffic, and documented the 0xAA status queries and replies (power state, brightness,
  colour, firmware) used for the keep-alive. No code was copied.

The battery, charging and plugged-in decoding of the H6058 status byte and the lamp's idle
timeout were measured on a real lamp for this project.

## Disclaimer

This project is AI-generated (see the notice at the top). It is not affiliated with, endorsed
by or connected to Govee or Shenzhen Intellirocks Tech. Co., Ltd. Govee is a trademark of its
owner. Use at your own risk.

## License

[MIT](LICENSE). The original MIT notices of the projects this one is based on are kept in the
license file.
