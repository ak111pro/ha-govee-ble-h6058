# Changelog

## 0.1.0 – 2026-10-20

First public release. Built from a private single-lamp integration that has controlled a Govee
H6058 on a Home Assistant 2026.9/2026.10 installation since 2026-09-30.

### Added

- Local Bluetooth control of the **Govee H6058**: on/off, brightness (0-100 scale of the lamp),
  RGB colour and colour temperature (2200-6500 K) in colour mode 0x0D.
- **Persistent BLE link**: one connection with a read-only keep-alive every 3 s and automatic
  reconnect with back-off, so commands are instant (the lamp closes idle connections after
  about 8-11 s).
- The light follows the lamp's reported power state (physical button, restarts); the commanded
  state is held for 3.5 s after each command so a stale reply cannot flip it back.
- H6058 only: **Battery**, **Charging** and **Plugged in** diagnostic entities decoded from the
  status reply.
- Firmware version on the device page.
- Config flow with **Bluetooth discovery** (`Govee_`, `ihoment_` and `GBK_` names of the
  supported models), a list of discovered lamps and **manual MAC entry**; one entry per lamp,
  unique id = MAC address.
- **Untested** models H6008, H613A, H613D and H6159 on the same code path, with a *Device
  report* issue template to report results.
- English and German translations, diagnostics download (MAC address redacted), brand icons.

### Changed (compared with the private integration)

- New domain `govee_ble_h6058` (was `govee_ble_lights`); nothing is hardcoded any more (address,
  name, area).
- Scenes/effects removed: the H6058 has no scene data, so the effect list was always empty.
