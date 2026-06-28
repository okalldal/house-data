#!/usr/bin/env python3
"""
build_isochrones.py — Precompute 1h / 2h drive-time boundaries (isochrones)
from Gothenburg and write them as GeoJSON for the static map.

Approach (no API key required): the public OSRM demo server has no isochrone
endpoint, but its `table` service returns the driving duration from one origin
to many destinations in a single call, *and* the road-snap distance for each
destination. We:

  1. Fan out a radial grid of sample points around Gothenburg (every few
     degrees of bearing, stepping outward in distance).
  2. Ask OSRM for the drive time + snap distance to each (batched).
  3. Drop points that snap far from any road (sea / archipelago / across the
     Kattegat to Denmark) so the boundary hugs the real road network.
  4. Per bearing, the isochrone radius is the farthest sampled point still
     reachable within the threshold. Connecting those points per bearing gives
     a star-shaped drive-time polygon.

Output: data/isochrones.json  (GeoJSON FeatureCollection: 60-min and 120-min
polygons + the Gothenburg origin point).

Usage:
    python3 build_isochrones.py
"""

import json
import math
import sys
import time
from pathlib import Path

import requests

OSRM = "https://router.project-osrm.org/table/v1/driving/"

# Gothenburg (Brunnsparken, city centre).
ORIGIN = (57.7089, 11.9746)
ORIGIN_NAME = "Gothenburg"

THRESHOLDS = [60, 120]          # minutes
BEARING_STEP = 5                # degrees between radial spokes
DIST_MIN_KM = 3
DIST_MAX_KM = 230               # 2h by car tops out well under this
DIST_STEP_KM = 4                # radial sampling resolution
SNAP_LIMIT_M = 2500             # discard points this far from any road
BATCH = 90                      # destinations per OSRM table call (demo cap ~100)

OUT_PATH = Path(__file__).parent / "data" / "isochrones.json"
EARTH_R = 6371.0


def destination_point(lat, lon, bearing_deg, dist_km):
    """Great-circle forward: point `dist_km` from (lat,lon) along `bearing`."""
    d = dist_km / EARTH_R
    br = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)
    lat2 = math.asin(
        math.sin(lat1) * math.cos(d) + math.cos(lat1) * math.sin(d) * math.cos(br)
    )
    lon2 = lon1 + math.atan2(
        math.sin(br) * math.sin(d) * math.cos(lat1),
        math.cos(d) - math.sin(lat1) * math.sin(lat2),
    )
    return math.degrees(lat2), math.degrees(lon2)


def osrm_table(origin, dests, *, max_tries=5):
    """Driving duration (s) + snap distance (m) from origin to each dest.

    Returns list of (duration_s_or_None, snap_dist_m_or_None) aligned to dests.
    """
    coords = [origin] + dests
    coord_str = ";".join(f"{lon},{lat}" for lat, lon in coords)
    url = (
        f"{OSRM}{coord_str}"
        f"?sources=0&annotations=duration,distance"
    )
    delay = 1.0
    for attempt in range(max_tries):
        try:
            r = requests.get(url, timeout=60)
            if r.status_code == 200:
                body = r.json()
                if body.get("code") == "Ok":
                    durs = body["durations"][0][1:]  # drop self (source->source)
                    snaps = [w.get("distance") for w in body["destinations"][1:]]
                    return list(zip(durs, snaps))
            # transient: retry
        except requests.RequestException:
            pass
        if attempt == max_tries - 1:
            raise RuntimeError(f"OSRM table failed after {max_tries} tries")
        time.sleep(delay)
        delay *= 2


def main():
    bearings = list(range(0, 360, BEARING_STEP))
    radii = [DIST_MIN_KM + i * DIST_STEP_KM
             for i in range(int((DIST_MAX_KM - DIST_MIN_KM) / DIST_STEP_KM) + 1)]

    # Build every sample point, tagged with its (bearing, radius).
    samples = []  # (bearing, radius_km, lat, lon)
    for b in bearings:
        for rkm in radii:
            lat, lon = destination_point(ORIGIN[0], ORIGIN[1], b, rkm)
            samples.append((b, rkm, lat, lon))

    print(f"[isochrones] {len(samples)} sample points "
          f"({len(bearings)} bearings x {len(radii)} radii)", file=sys.stderr)

    # Query OSRM in batches and record results per sample.
    results = []  # (bearing, radius_km, duration_min, snap_m)
    for i in range(0, len(samples), BATCH):
        batch = samples[i:i + BATCH]
        dests = [(lat, lon) for (_, _, lat, lon) in batch]
        table = osrm_table(ORIGIN, dests)
        for (b, rkm, _, _), (dur, snap) in zip(batch, table):
            dur_min = dur / 60.0 if dur is not None else None
            results.append((b, rkm, dur_min, snap))
        print(f"[isochrones] {min(i + BATCH, len(samples))}/{len(samples)} "
              "points queried", file=sys.stderr)
        time.sleep(0.4)

    # Per bearing, find the boundary radius for each threshold.
    features = []
    for minutes in THRESHOLDS:
        ring = []
        for b in bearings:
            reachable = [
                rkm for (bb, rkm, dur_min, snap) in results
                if bb == b
                and dur_min is not None and dur_min <= minutes
                and snap is not None and snap <= SNAP_LIMIT_M
            ]
            if not reachable:
                continue  # nothing drivable on this spoke (open sea) -> skip vertex
            r_boundary = max(reachable)
            lat, lon = destination_point(ORIGIN[0], ORIGIN[1], b, r_boundary)
            ring.append((b, [round(lon, 5), round(lat, 5)]))

        ring.sort(key=lambda x: x[0])
        coords = [pt for (_, pt) in ring]
        if coords:
            coords.append(coords[0])  # close the ring
        features.append({
            "type": "Feature",
            "properties": {"minutes": minutes,
                           "label": f"{minutes // 60}h drive from {ORIGIN_NAME}"},
            "geometry": {"type": "Polygon", "coordinates": [coords]},
        })

    features.append({
        "type": "Feature",
        "properties": {"name": ORIGIN_NAME, "role": "origin"},
        "geometry": {"type": "Point",
                     "coordinates": [round(ORIGIN[1], 5), round(ORIGIN[0], 5)]},
    })

    fc = {
        "type": "FeatureCollection",
        "source": "OSRM (router.project-osrm.org) driving table; thresholds 60/120 min",
        "origin": {"name": ORIGIN_NAME, "lat": ORIGIN[0], "lon": ORIGIN[1]},
        "features": features,
    }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(fc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"[isochrones] wrote {OUT_PATH}", file=sys.stderr)


if __name__ == "__main__":
    main()
