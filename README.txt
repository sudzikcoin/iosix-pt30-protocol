PT30 Raw Data Export
=====================

Purpose: reverse-engineer the IOSiX PT30 BLE notification protocol
so we can correctly parse instantaneous fuel rate (and other PGN
fields) that are currently being mis-mapped by both the mobile APK
parser and the PingPoint server parser.

Source: IOSiX PT30 OBD-II/J1939 dongle
Truck:  Unit 160, VIN 3AKJHHDR1RSUX1166 (2024 Freightliner)
Captured: 2026-04-23 through 2026-04-25 UTC
Driver tokens captured:
  - drv_ca9537005b892f40396c32cb (active session, 2026-04-24)
  - drv_604cf0a3534330bffb1a9058 (prior session, 2026-04-23/24)

Files in this archive:
----------------------
1. pt30_raw_ble_fragments_active.jsonl
   pt30_raw_ble_fragments_prior_session_2023.jsonl
   pt30_raw_ble_fragments_prior_session_2024.jsonl
      Raw BLE notifications logged by the APK via POST
      /api/driver/:token/iosix-raw-log. Each JSON line has
      {"timestamp": <ms>, "raw": "<base64 of 20 bytes>"}.
      First byte of decoded payload is a sequence counter
      (0..255 wrap); remaining bytes are ASCII characters of a
      CSV stream.

2. pt30_decoded_csv_lines.txt
      BLE fragments reassembled into full CSV lines.
      Format per line: source_file \t timestamp_ms \t CSV_data
      Two CSV record types observed:
        - "Data: 1, VIN, f2..f19"  — engine running
        - "Data: 0, ..."           — engine off (all zeros)
        - "Buffer: 0,N,N,0"        — BLE housekeeping

3. pt30_fragments_annotated.txt
      First 5000 BLE fragments with sequence counter, byte length,
      and decoded ASCII payload. Useful for analyzing the
      20-byte-fragment boundary behavior.

4. pt30_samples_by_mode.txt
      Sampled CSV lines grouped by engine state (idle, cruise,
      coast, high-load, cold-start) with all ~19 fields labeled
      f1..fN. MOST USEFUL file for field-mapping.

Field analysis (all values empirical, no official spec):
--------------------------------------------------------
HIGH CONFIDENCE (derived from value ranges across 4941 samples):
  f1  = VIN (3AKJHHDR1RSUX1166)
  f2  = RPM                     range 496..1726  (diesel idle/redline)
  f3  = vehicle speed km/h      range 0..114
  f4  = odometer miles          range ~563000+
  f5  = trip miles              range 0..242 (resets per session)
  f6  = engine hours            range 9023.45..9026.20 (lifetime)
  f8  = battery voltage         range 12.47..14.09
  f9  = date MM/DD/YY (UTC)
  f10 = time HH:MM:SS (UTC)
  f11 = latitude                decimal degrees
  f12 = longitude               decimal degrees
  f15 = gear                    3..10 (10-speed transmission)
  f19 = constant 349            (likely packet-type / protocol flag)

UNKNOWN — NEED PT30 SPEC:
  f7  = float 0..2.75, monotonically increases throughout the trip.
        Correlates with time, NOT with instantaneous RPM/load.
        Candidates: cumulative fuel used (gal/L), DPF soot %, DEF
        level %, cumulative idle-hours, cumulative trip fuel.
  f13 = int 0..119  (heading? GPS quality? satellite count?)
  f14 = int 0..358  (heading looks right — 358 ≈ North — but
        f13 might overlap)
  f16 = int -159..965  (NEGATIVE values rule out RPM, throttle%,
        load%. Could be intake manifold pressure delta, accel
        vector, or a signed sensor reading)
  f17 = float 0.8..99.9, mean ~3.1, 99.9 appears as "unavailable"
        sentinel. Could be any ratio (boost ratio, air/fuel, etc.)
  f18 = int monotonic counter (12000..22000+). Packet sequence
        or odometer in some alternate unit?

Specific question for IOSiX support:
------------------------------------
1. Please provide the PT30 ROM-stream BLE CSV protocol
   documentation, i.e. a field-by-field description of the
   "Data: 1, ..., f19" packet.

2. Specifically: which field encodes SAE J1939 PGN 65266 SPN 183
   (Engine Fuel Rate, instantaneous, gal/h or L/h)?

3. Does this unit report:
   - SPN 51  (Engine Percent Torque / Load)
   - SPN 110 (Engine Coolant Temperature)
   - SPN 102 (Engine Intake Manifold #1 Pressure / Boost)
   - SPN 100 (Engine Oil Pressure)
   - SPN 52  (Engine Intercooler Temperature)
   - SPN 94  (Engine Fuel Delivery Pressure)
   - SPN 3031 (Aftertreatment DEF Tank Volume)
   - SPN 3251 (DPF Differential Pressure)

   If so, which field index?

4. Is the single-line "Data: 1, VIN, f2..f19" the intended format,
   or should we expect a multi-line cycle (Data: 1..Data: 7)?
   The mobile APK parser was written for a 7-line cycle but we
   observe only single-line records — that may be a firmware
   configuration difference.

Protocol observations:
----------------------
- BLE MTU appears to be 20 bytes per notification
- 85% of notifications are exactly 20 bytes (1 seq + 19 ASCII)
- CSV records are terminated with "\r\n"
- Typical CSV record is ~140-160 ASCII bytes → 8 BLE notifications
- Sequence counter wraps 0..255
- Occasional "Buffer: 0,N,N,0" lines appear between data records

Statistics:
-----------
Total BLE fragments (all 3 sources):   41,836
Total decoded CSV lines:                5,665
  - Data: 1 (engine running) records:  ~4,941 (parsed for samples)
  - Data: 0 (engine off) records:      ~186
  - Buffer: / housekeeping:            ~balance

Sensitive data note:
--------------------
Archive contains the truck VIN (3AKJHHDR1RSUX1166) and GPS
coordinates of the trip (I-40 east of Nashville, heading west).
Safe to share with IOSiX support — they already know this asset.
Do not publish publicly.
