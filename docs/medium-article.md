---
title: "Reverse-Engineering the IOSiX PT30 BLE Protocol: How We Found the Real Fuel Rate Field"
subtitle: "A field-by-field teardown of 5,665 CSV records from a 2024 Freightliner Cascadia's OBD-II dongle — and how we fixed a silent bug that was corrupting our fleet's CO2 data."
author: Dmitrii Sudzerovskii
tags: [j1939, telematics, reverse-engineering, fleet-management, iot, trucking]
canonical_url: https://suverse.io/news/iosix-pt30-protocol-reverse-engineering
---

## The problem

For months our PingPoint dashboard reported fuel rates that looked plausible. Idle: 3.4 gal/h. Highway cruise: 2.4 gal/h. Numbers existed, charts rendered, weekly reports went out. No one caught it — the values were the right order of magnitude, just inverted relative to physics.

The truck is a 2024 Freightliner Cascadia with a Detroit DD15. Idle on a DD15 is 0.5–0.9 gal/h. Cruise at 65 mph in a loaded semi is 3.5–5 gal/h. Climbing a grade is 6–8 gal/h. Our reported numbers were backwards. The default IOSiX SDK was reading the wrong field.

## Why reverse-engineering was necessary

IOSiX does not publish a CSV-over-BLE protocol document for the PT30. We had two options: trust the SDK label, or capture the raw stream and figure it out ourselves.

We hooked the BLE characteristic on the driver phone via `react-native-ble-plx`, logged every notification packet to JSON Lines, and let the truck run. Across three driving sessions we captured **41,836 BLE fragments** (20 bytes each, first byte a sequence counter, 19 bytes ASCII) which reassembled into **5,665 complete CSV records**. Of those, 4,941 are `Data: 1,` records — the only type we needed for fuel analysis.

## Protocol structure

Each `Data: 1,` record is a flat CSV line of 19 fields. Example:

```
Data: 1,VIN,1163,97,563322.875,240.790,9026.20,2.75,14.07,
04/24/26,22:51:25,36.532367,-87.229690,100,313,6,926,1.3,22164,349
```

| Field | J1939 SPN | Units | Status | Notes |
|---|---|---|---|---|
| f1 | — | string | OK | VIN |
| f2 | 190 | RPM | OK | Engine RPM (99999 = no signal) |
| f3 | — | km/h | OK | GPS speed |
| f4 | 245 | miles | OK | Lifetime odometer |
| f5 | 244 | miles | OK | Trip distance (resets per session) |
| f6 | 247 | hours | OK | Lifetime engine hours |
| **f7** | proprietary | **gallons** | **WARN** | **Cumulative trip fuel — NOT a rate** |
| f8 | 168 | volts | OK | Battery voltage |
| f9 | — | MM/DD/YY | OK | Date |
| f10 | — | HH:MM:SS UTC | OK | Time |
| f11 | — | degrees | OK | GPS latitude |
| f12 | — | degrees | OK | GPS longitude |
| f13 | 84 | km/h | OK | Wheel speed (capped at 119) |
| f14 | — | degrees | OK | Compass heading |
| f15 | 523 | gear# | OK | Current gear (0 = neutral) |
| f16 | unknown | ? | **TBD** | Range -159 to 1200, possibly multiplexed |
| **f17** | — | **L/h × 0.1** | **OK** | **Instantaneous fuel rate (sentinel 99.9)** |
| f18 | — | seconds | OK | Session counter (~1/sec) |
| f19 | — | constant | OK | Always 349 for `Data: 1` |

## The f7 trap

The default SDK reads f7. Three properties make the bug subtle.

First, **f7 has only 39 unique values across the entire 5,665-sample dataset**. It's a quantized counter, not a continuous measurement. Every increment is exactly 0.05 gallons.

Second, **the update cadence is irregular**: median 180 seconds, mean roughly 800 seconds. Long stretches of no change followed by sudden steps.

Third, the obvious workaround — derive a rate as Δf7 / Δt — does not work. The quantized 0.05-gallon steps and BLE-fragmentation-aligned irregular cadence mean Δf7/Δt over short windows produces values anywhere from 0 to over 300 gal/h depending on whether your sampling window happens to straddle a step. Smoothing across longer windows just buries real engine-state changes under integration. There is no reliable instantaneous-rate signal recoverable from f7.

f7 is useful as a session-total counter for end-of-trip fuel consumption. As an instantaneous rate it is structurally unfit, and the SDK's label was wrong on first principles.

## Finding the real fuel rate: f17

We grouped the dataset by engine state and looked for any field whose value tracked engine load monotonically. f17 was the only candidate. During sustained highway cruise (80–120 km/h), grouped by gear:

| Gear | f17 median | L/h | gal/h |
|---|---|---|---|
| 10 (overdrive) | 0.80 | 8.0 | 2.1 |
| 9 | 0.90 | 9.0 | 2.4 |
| 8 | 0.90 | 9.0 | 2.4 |
| 7 | 1.20 | 12.0 | 3.2 |
| 6 | 1.40 | 14.0 | 3.7 |
| 5 | 1.50 | 15.0 | 4.0 |
| 4 | 1.80 | 18.0 | 4.8 |

Lower gear at the same vehicle speed means higher engine RPM, which means more fuel per hour. The slope matches a DD15 fuel map exactly. Idle samples land at 1.3–1.9 gal/h; cruise at 2–4 gal/h; heavy-load grades push past 5 gal/h. The encoding is `L/h × 10⁻¹`: multiply f17 by 10 for L/h, divide by 3.785 for gal/h. The value 99.9 is the sentinel for "no fresh PGN reading from the engine bus."

## The formula

```typescript
const f17 = parseFloat(fields[16]);
let fuelRateGph: number | null = null;
if (Number.isFinite(f17) && f17 < 90) {
  const gph = (f17 * 10) / 3.785;
  if (gph >= 0 && gph <= 12) fuelRateGph = gph;
}
```

The clamp at 12 gal/h reflects a DD15's physical ceiling at full throttle uphill. The sentinel check (`< 90`) collapses 99.9 to null. Everything else is unit conversion.

## What this means for AgentOS and PingPoint

Per-shipment CO2 now integrates `fuel_rate_gph` over time and multiplies by the 10.180 kg-per-gallon CO2 factor. The number is grounded in the engine bus, not EPA averages. The same signal feeds driver-behavior scoring (smooth cruise vs. aggressive throttle, fuel/RPM ratio over a window) and a coarse predictive-maintenance channel — sustained anomalies in fuel-per-RPM surface engine issues earlier than service intervals do. None of those are useful with f7-derived garbage; all of them work cleanly with f17.

## Open data, open community

The full dataset, decoded CSV samples, and the Python decoder we used to reassemble fragments are on GitHub at [sudzikcoin/iosix-pt30-protocol](https://github.com/sudzikcoin/iosix-pt30-protocol). VIN is redacted; everything else is preserved. Field f16 remains unresolved — its range (-159 to 1200) and non-monotonic behavior suggest a multiplexed PGN slot, but without IOSiX firmware documentation we cannot confirm. PRs welcome.

## Closing

We trusted a vendor SDK and shipped wrong numbers for months. The fix was one field index. The lesson worth carrying: every primary data source feeding a calculation that anyone reads — emissions, billing, scoring, anything — needs to be audited against physics before the dashboard tells you it's working.

— Dmitrii Sudzerovskii

---

*Originally published in extended form at [suverse.io/news/iosix-pt30-protocol-reverse-engineering](https://suverse.io/news/iosix-pt30-protocol-reverse-engineering). Source code and dataset: [github.com/sudzikcoin/iosix-pt30-protocol](https://github.com/sudzikcoin/iosix-pt30-protocol).*

*Dmitrii Sudzerovskii is the founder of [Suverse LLC](https://suverse.io), where he builds AgentOS (fleet intelligence) and PingPoint (BLE telematics ingestor).*
