# IOSiX PT30 Raw Data — Reverse Engineering

> **🎉 STATUS: PROTOCOL DECODED** (2026-04-25)
>
> Field mapping resolved through statistical analysis of 5,665 CSV
> samples across multiple driving modes. Key finding: **f17 is the
> instantaneous fuel rate** (L/h × 0.1), not f7 as initially assumed
> by the default mobile app SDK. See [Final Field Mapping](#-final-field-mapping-resolved) below.
>
> Detailed write-up: ["How We Reverse-Engineered the IOSiX PT30 Protocol"](https://suverse.io/news/iosix-pt30-protocol-reverse-engineering)

Raw data captured from an IOSiX PT30 OBD-II/J1939 dongle
installed in a 2024 Freightliner Cascadia (Detroit DD15 engine).

The PT30 streams data over BLE in a CSV-like format starting
with `Data: 1,` (engine running) or `Data: 0,` (engine off).
This repo contains both raw BLE fragments and reassembled CSV
lines for protocol analysis.

## ✅ Final Field Mapping (RESOLVED)

| Field | Index | J1939 SPN | Units | Range | Description |
|-------|-------|-----------|-------|-------|-------------|
| f1  | 0  | — | string | — | VIN |
| f2  | 1  | SPN 190 | RPM | 409–1726 | Engine RPM (99999 = no signal) |
| f3  | 2  | — | km/h | 0–114 | GPS speed |
| f4  | 3  | SPN 245 | miles | ~563000 | Lifetime odometer |
| f5  | 4  | SPN 244 | miles | 0–389 | Trip distance (resets per session) |
| f6  | 5  | SPN 247 | hours | 9011–9026 | Lifetime engine hours |
| **f7**  | 6  | proprietary | **gallons** | 0–4.45 | **Cumulative trip fuel** (NOT instantaneous rate) |
| f8  | 7  | SPN 168 | volts | 12.47–14.13 | Battery voltage |
| f9  | 8  | — | MM/DD/YY | — | Date string |
| f10 | 9  | — | HH:MM:SS UTC | — | Time string |
| f11 | 10 | — | degrees | decimal | GPS latitude |
| f12 | 11 | — | degrees | decimal | GPS longitude |
| f13 | 12 | SPN 84  | km/h | 0–119 | Wheel speed (capped at 119) |
| f14 | 13 | — | degrees | 0–358 | Compass heading |
| f15 | 14 | SPN 523 | gear# | 0–10 | Current gear (0 = neutral) |
| f16 | 15 | unknown | ? | -159–1200 | **Unresolved** — possibly multiplexed PGN |
| **f17** | 16 | — | **L/h × 0.1** | 0–39.8 | **Instantaneous fuel rate** (sentinel 99.9 = no data) |
| f18 | 17 | — | seconds | 1398–48000 | Session counter (~1/sec, monotonic) |
| f19 | 18 | — | constant | 349 | Packet type flag (always 349 for `Data: 1`) |

## How to parse fuel rate correctly

The mobile app initially read f7 as `fuelRateGph` — this is wrong.
f7 is a cumulative gallon counter that increments by 0.05 gallons
every few minutes, producing nonsensical instantaneous rates.

The correct field is **f17**, with the formula:

```typescript
const f17 = parseFloat(fields[16]); // 0-based array index

let fuelRateGph: number | null = null;
if (!isNaN(f17) && f17 < 90) {
  // f17 is L/h × 0.1, convert to gal/h
  const litersPerHour = f17 * 10;
  fuelRateGph = litersPerHour / 3.785;

  // Sanity clamp (DD15 max ~12 gal/h at full load)
  if (fuelRateGph > 12 || fuelRateGph < 0) {
    fuelRateGph = null;
  }
}
// f17 >= 90 → sentinel value, data unavailable
```

## Verification: how we know f17 is fuel rate

Statistical correlation across 5,665 samples shows monotonic
relationship between f17 and engine load proxies. Highway cruise
(80–120 km/h), grouped by gear:

| Gear            | f17 median | L/h  | gal/h | Real-world expectation |
|-----------------|------------|------|-------|------------------------|
| 10 (overdrive)  | 0.80       | 8.0  | 2.1   | ✅ Low RPM cruise      |
| 9               | 0.90       | 9.0  | 2.4   | ✅                     |
| 8               | 0.90       | 9.0  | 2.4   | ✅                     |
| 7               | 1.20       | 12.0 | 3.2   | ✅                     |
| 6               | 1.40       | 14.0 | 3.7   | ✅                     |
| 5               | 1.50       | 15.0 | 4.0   | ✅                     |
| 4               | 1.80       | 18.0 | 4.8   | ✅                     |

Lower gear at the same speed = higher RPM = higher fuel
consumption. The pattern matches DD15 specifications exactly.

## Still unresolved: f16

Field f16 shows non-monotonic behavior across all engine states
(range -159 to 1200, including negatives). Hypothesis: it may be
a multiplexed PGN where the source rotates between different SAE
J1939 parameters. Without IOSiX firmware documentation this cannot
be confirmed. PRs welcome.

## Credits

Decoded by [SuVerse](https://suverse.io) team during operational
deployment in Felix Transport fleet. Detailed write-up:
["How we reverse-engineered the IOSiX PT30 protocol"](https://suverse.io/news/iosix-pt30-protocol-reverse-engineering).

## Investigation context

The default mobile app SDK shipped with the PT30 reads field
**f7** and labels it as `fuelRateGph`. On a Detroit DD15 in a
loaded semi-truck, this produced physically impossible readings
— around 3.4 gal/h at idle (real range 0.5–0.9 gal/h) and 2.4
gal/h at 65 mph cruise (real range 3.5–5 gal/h). Investigating
which field actually carries instantaneous fuel rate (SAE J1939
PGN 65266 / SPN 183) was the goal that produced this dataset.

The resolution above (f17 in L/h × 0.1) was confirmed by
correlating field values with engine load proxies across 5,665
samples grouped by gear, RPM, and vehicle speed.

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
