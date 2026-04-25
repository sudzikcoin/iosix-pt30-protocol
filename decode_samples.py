#!/usr/bin/env python3
"""Group decoded CSV lines by engine mode for reverse-engineering PT30 format."""
from pathlib import Path

src = Path('/tmp/pt30-raw-export/pt30_decoded_csv_lines.txt')
out = Path('/tmp/pt30-raw-export/pt30_samples_by_mode.txt')

records = []
with src.open() as f:
    for line in f:
        if line.startswith('#') or not line.strip():
            continue
        parts = line.rstrip('\n').split('\t')
        if len(parts) < 3:
            continue
        src_name, ts, csv = parts[0], parts[1], parts[2]
        if not csv.startswith('Data: 1,'):
            continue
        fields = csv[len('Data: 1,'):].split(',')
        if len(fields) < 19:
            continue
        try:
            rpm = int(fields[1])
            speed = int(fields[2])
        except Exception:
            continue
        # skip obvious mock data (99999 sentinel)
        if rpm == 99999:
            continue
        records.append((src_name, ts, csv, rpm, speed, fields))

modes = {
    'COLD_START  (rpm 700-800, speed 0)':        [r for r in records if 700 <= r[3] <= 800 and r[4] == 0][:10],
    'IDLE        (rpm 580-650, speed 0)':        [r for r in records if 580 <= r[3] <= 650 and r[4] == 0][:10],
    'LOW_IDLE    (rpm 480-520, speed 0)':        [r for r in records if 480 <= r[3] <= 520 and r[4] == 0][:10],
    'COAST       (rpm 480-520, speed >= 100)':   [r for r in records if 480 <= r[3] <= 520 and r[4] >= 100][:10],
    'CRUISE_LOW  (rpm 1000-1100, speed >= 90)':  [r for r in records if 1000 <= r[3] <= 1100 and r[4] >= 90][:10],
    'CRUISE_HIGH (rpm 1100-1300, speed >= 95)':  [r for r in records if 1100 <= r[3] <= 1300 and r[4] >= 95][:10],
    'HIGH_LOAD   (rpm >= 1400)':                 [r for r in records if r[3] >= 1400][:10],
}

with out.open('w') as f:
    f.write("# PT30 samples grouped by engine mode\n")
    f.write("# CSV prefix 'Data: 1,' stripped. Fields labeled f1..fN for reference.\n")
    f.write("# Known (high confidence, by range analysis):\n")
    f.write("#   f1  = VIN\n")
    f.write("#   f2  = RPM (496-1726 range, matches diesel engine)\n")
    f.write("#   f3  = vehicle speed km/h (0-114)\n")
    f.write("#   f4  = odometer miles (~563000)\n")
    f.write("#   f5  = trip miles (0-242, resets per session)\n")
    f.write("#   f6  = engine hours (~9023-9026)\n")
    f.write("#   f8  = battery voltage (12.47-14.09)\n")
    f.write("#   f9  = date MM/DD/YY\n")
    f.write("#   f10 = time HH:MM:SS (UTC)\n")
    f.write("#   f11 = GPS latitude\n")
    f.write("#   f12 = GPS longitude\n")
    f.write("#   f15 = gear (3-10)\n")
    f.write("#   f19 = constant 349 (packet type flag?)\n")
    f.write("# UNKNOWN (need IOSiX PT30 protocol spec):\n")
    f.write("#   f7  = float 0..2.75, monotonically grows with time (cumulative?)\n")
    f.write("#   f13, f14 = integers, possibly heading/altitude/sat\n")
    f.write("#   f16 = int -159..965 (negatives — not RPM, not throttle%)\n")
    f.write("#   f17 = float 0.8-99.9 mean ~3, 99.9 appears as sentinel\n")
    f.write("#   f18 = large int counter (12000+ monotonic)\n")
    f.write("# QUESTION for IOSiX support:\n")
    f.write("#   Which field carries SAE J1939 PGN 65266 SPN 183 (Instantaneous Fuel Rate)?\n")
    f.write("#   Which field carries SPN 51 (Engine % Torque / Load)?\n")
    f.write("#   Is there coolant temp (SPN 110), boost pressure (SPN 102)?\n")
    f.write("\n")
    for mode, samples in modes.items():
        f.write(f"\n========== {mode} ==========\n")
        f.write(f"Found {len(samples)} samples\n\n")
        for src_name, ts, csv, rpm, speed, fields in samples:
            f.write(f"[source={src_name} ts={ts}] rpm={rpm} speed={speed}km/h gear={fields[14] if len(fields)>14 else '?'}\n")
            f.write(f"  raw:    {csv}\n")
            labeled = " ".join(f"f{i+1}={v}" for i, v in enumerate(fields))
            f.write(f"  fields: {labeled}\n\n")

print(f"Records parsed: {len(records)}")
print(f"Output: {out}")
