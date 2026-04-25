# IOSiX PT30 Raw Data — Reverse Engineering

Raw data captured from an IOSiX PT30 OBD-II/J1939 dongle
installed in a 2024 Freightliner Cascadia (Detroit DD15 engine).

The PT30 streams data over BLE in a CSV-like format starting
with `Data: 1,` (engine running) or `Data: 0,` (engine off).
This repo contains both raw BLE fragments and reassembled CSV
lines for protocol analysis.

## What we know

Each `Data: 1,` line has 19 fields after the prefix:

`Data: 1, VIN, f2, f3, f4, f5, f6, f7, f8, f9, f10, f11, f12, f13, f14, f15, f16, f17, f18, f19`

Identified by value range and behavior:

| Field | Meaning | Range |
|-------|---------|-------|
| f1 | VIN | `3AKJHHDR1RSUX1166` |
| f2 | Engine RPM | 496–1726 |
| f3 | Vehicle speed (km/h) | 0–114 |
| f4 | Odometer (miles) | ~563000 |
| f5 | Trip miles | resets per session |
| f6 | Engine hours (lifetime) | ~9023–9026 |
| **f7** | **UNKNOWN** | float 0–2.75, monotonic over time |
| f8 | Battery voltage | 12.47–14.09 |
| f9 | Date | MM/DD/YY |
| f10 | Time | HH:MM:SS (UTC) |
| f11 | GPS latitude | decimal degrees |
| f12 | GPS longitude | decimal degrees |
| **f13** | **UNKNOWN** (heading?) | 0–119 |
| **f14** | **UNKNOWN** (heading?) | 0–358 |
| f15 | Gear | 3–10 |
| **f16** | **UNKNOWN** | -159 to 965 (negatives present) |
| **f17** | **UNKNOWN** | 0.8–99.9 (sentinel 99.9 frequent) |
| **f18** | **UNKNOWN** | monotonic int counter (12000+) |
| f19 | Constant | always 349 |

## What we need to identify

The primary goal: locate the **instantaneous fuel rate** field
(SAE J1939 PGN 65266 / SPN 183, units L/h, resolution 0.05 L/h).

Currently the mobile app parser reads f7 and labels it as
`fuelRateGph`, but f7 monotonically increases over time (looks
like a cumulative counter, not instantaneous rate). On a Detroit
DD15 with a loaded semi-truck, instantaneous fuel rate should be:

- **Idle:** ~0.5–0.9 gal/h (~2–3.5 L/h)
- **Cruise at 65 mph:** ~3.5–5 gal/h (~13–19 L/h)
- **Heavy load uphill:** ~5–8 gal/h (~19–30 L/h)

No field in the 19 currently shows this exact pattern. Possible
causes:

- PT30 firmware does not subscribe to PGN 65266 by default
- Fuel rate is in one of the unknown fields with non-obvious scaling
- PT30 uses a proprietary subset of J1939 data

Other parameters of interest (J1939 SPNs):

- **SPN 51** — Throttle Position (%)
- **SPN 92** — Engine Percent Load at current speed (%)
- **SPN 110** — Engine Coolant Temperature (°C)
- **SPN 102** — Boost Pressure (kPa)
- **SPN 100** — Engine Oil Pressure (kPa)
- **SPN 3031** — Aftertreatment DEF Tank Volume (%)
- **SPN 3251** — DPF Differential Pressure (kPa)

## BLE protocol notes

- Each BLE notification packet: 20 bytes total
- Byte 0: sequence counter (0–255 wrap)
- Bytes 1–19: ASCII payload (CSV chunk)
- Median fragment payload: 18–19 bytes
- 85% of fragments are exactly 19 bytes
- One CSV line spans approximately 8 BLE fragments
- CSV records are terminated with `\r\n`
- Occasional `Buffer: 0,N,N,0` lines appear between data records

The mobile app (Expo/React Native, `react-native-ble-plx`)
currently uses a `parseCycle` function expecting a 7-line cycle
(`PACKET_CYCLE_SIZE = 7`), but the PT30 emits single-line CSV
per record. The app accidentally works for RPM because BLE
fragmentation aligns with field boundaries by coincidence — but
this is fragile and breaks for fuel rate parsing.

## Files

| File | Description |
|------|-------------|
| `pt30_raw_ble_fragments_active.jsonl` | raw BLE log, active session (1.6 MB) |
| `pt30_raw_ble_fragments_prior_session_2024.jsonl` | prior session (757 KB) |
| `pt30_raw_ble_fragments_prior_session_2023.jsonl` | older session (226 KB) |
| `pt30_decoded_csv_lines.txt` | all 5665 reassembled CSV lines |
| `pt30_fragments_annotated.txt` | first 5000 BLE fragments with seq/len/payload |
| **`pt30_samples_by_mode.txt`** | **most useful** — CSV samples grouped by engine mode (idle, cruise, coast, high_load) with all 19 fields labeled |
| `decode_ble.py` | reassemble CSV from raw BLE fragments |
| `decode_samples.py` | group samples by engine mode |
| `README.txt` | original plaintext README with support-question list |

Each JSON line in the `*.jsonl` files has the shape:

```json
{"timestamp":<unix_ms>,"raw":"<base64 of 20 bytes>"}
```

The first byte of the decoded 20-byte payload is the sequence
counter; the remaining 19 bytes are ASCII characters of the CSV
stream.

## Statistics

- Total BLE fragments captured: **41,836**
- Total decoded CSV lines: **5,665**
- `Data: 1,` (engine running) records: **4,941**
- `Data: 0,` (engine off) records: **~724**

## Hardware

- **Truck:** 2024 Freightliner Cascadia
- **Engine:** Detroit Diesel DD15 (~12.8L displacement)
- **VIN:** `3AKJHHDR1RSUX1166`
- **Dongle:** IOSiX PT30 (BLE-equipped J1939/OBD-II reader)

## Reproducing the decode

```bash
python3 decode_ble.py       # reassembles all three jsonl files
python3 decode_samples.py   # groups by engine mode
```

Both scripts expect the jsonl files in the same directory.

## License

Data published for protocol reverse engineering. No commercial
restrictions. VIN and GPS coordinates are included intentionally —
do not redact for analysis purposes. This trip path is I-40
westbound from Rockwood, TN toward Walthill, NE.

## Contributions welcome

If you recognize the PT30 protocol or have the IOSiX ROM-stream
BLE CSV spec, please open an issue or PR mapping any of the
unknown fields (f7, f13, f14, f16, f17, f18) to J1939 SPN numbers.
