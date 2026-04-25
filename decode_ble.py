#!/usr/bin/env python3
"""Reassemble BLE fragments from PingPoint /iosix-raw-log into CSV lines."""
import json, base64, sys
from pathlib import Path

EXPORT_DIR = Path('/tmp/pt30-raw-export')
SOURCES = sorted(EXPORT_DIR.glob('pt30_raw_ble_fragments*.jsonl'))

out_csv = EXPORT_DIR / 'pt30_decoded_csv_lines.txt'
out_frags = EXPORT_DIR / 'pt30_fragments_annotated.txt'

csv_lines = []
frag_log = []

for src in SOURCES:
    buffer = ""
    with src.open() as f:
        for line in f:
            try:
                rec = json.loads(line)
            except Exception:
                continue
            ts = rec.get('timestamp', '')
            raw_b64 = rec.get('raw')
            if not raw_b64:
                continue
            try:
                raw = base64.b64decode(raw_b64)
            except Exception:
                continue
            if len(raw) < 1:
                continue
            seq = raw[0]
            ascii_part = raw[1:].decode('latin1', errors='replace')

            frag_log.append((src.name, ts, seq, len(raw), ascii_part))
            buffer += ascii_part

            while '\n' in buffer:
                idx = buffer.index('\n')
                line_str = buffer[:idx].rstrip('\r')
                buffer = buffer[idx+1:]
                if line_str.strip():
                    csv_lines.append((src.name, ts, line_str))

with out_csv.open('w') as f:
    f.write("# Decoded PT30 CSV lines (BLE fragments reassembled)\n")
    f.write("# Format: source_file\\ttimestamp_ms\\tCSV_line\n")
    f.write(f"# Total: {len(csv_lines)} lines from {len(SOURCES)} source files\n\n")
    for src_name, ts, ln in csv_lines:
        f.write(f"{src_name}\t{ts}\t{ln}\n")

with out_frags.open('w') as f:
    f.write("# BLE fragments with sequence counter and ASCII payload\n")
    f.write("# Format: source_file | timestamp_ms | seq | total_bytes | payload_after_seq_byte\n")
    f.write(f"# Total: {len(frag_log)} fragments (showing first 5000)\n\n")
    for entry in frag_log[:5000]:
        src_name, ts, seq, length, payload = entry
        f.write(f"{src_name} | ts={ts} | seq={seq:3d} | len={length} | {payload!r}\n")
    if len(frag_log) > 5000:
        f.write(f"\n... ({len(frag_log)-5000} more fragments truncated)\n")

print(f"CSV lines: {len(csv_lines)}")
print(f"Fragments: {len(frag_log)}")
print(f"Sources:   {len(SOURCES)}")
print(f"  -> {out_csv}")
print(f"  -> {out_frags}")
