#!/usr/bin/env python3
from __future__ import annotations
import argparse, base64, csv, io, json, re, socket, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests

DEFAULT_URL = "http://www.vpngate.net/api/iphone/"

def parse_vpngate_csv(raw: str):
    lines = [line for line in raw.splitlines() if line and not line.startswith("*")]
    if not lines:
        return []
    reader = csv.DictReader(lines)
    rows = []
    for row in reader:
        try:
            host = (row.get("IP") or "").strip()
            encoded = (row.get("OpenVPN_ConfigData_Base64") or "").strip()
            if not host or not encoded:
                continue
            profile_bytes = base64.b64decode(encoded, validate=True)
            if len(profile_bytes) > 256_000:
                continue
            profile = profile_bytes.decode("utf-8", "replace")
            remotes = re.findall(r"(?im)^\s*remote\s+(\S+)\s+(\d+)", profile)
            if not remotes:
                continue
            remote_host, remote_port = remotes[0]
            # Use the API IP as the endpoint host; keep the profile's port.
            port = int(remote_port)
            if not (1 <= port <= 65535):
                continue
            rows.append({
                "host": host, "port": port,
                "profile_b64": encoded,
                "country": (row.get("CountryLong") or "").strip(),
                "country_short": (row.get("CountryShort") or "").strip(),
                "speed_kbps": int(row.get("Speed") or 0),
                "score": int(row.get("Score") or 0),
            })
        except (ValueError, TypeError, UnicodeError):
            continue
    return rows

def tcp_probe(item, timeout=4):
    start = time.monotonic()
    try:
        with socket.create_connection((item["host"], item["port"]), timeout=timeout):
            item["tcp_reachable"] = True
    except OSError as exc:
        item["tcp_reachable"] = False
        item["tcp_error"] = str(exc)[:160]
    item["tcp_ms"] = round((time.monotonic() - start) * 1000, 1)
    item["verification_level"] = "tcp_connect_only"
    item["tunnel_verified"] = False
    return item

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="out")
    ap.add_argument("--url", default=DEFAULT_URL)
    ap.add_argument("--max-candidates", type=int, default=100)
    ap.add_argument("--timeout", type=float, default=4)
    ap.add_argument("--workers", type=int, default=40)
    args = ap.parse_args()
    out = Path(args.output); out.mkdir(parents=True, exist_ok=True)
    response = requests.get(args.url, timeout=25, headers={"User-Agent": "AimiliVPN-Auto/0.1"})
    response.raise_for_status()
    rows = parse_vpngate_csv(response.text)
    rows.sort(key=lambda x: (x["score"], x["speed_kbps"]), reverse=True)
    rows = rows[:max(1, min(args.max_candidates, 500))]
    results = []
    with ThreadPoolExecutor(max_workers=max(1, min(args.workers, 100))) as pool:
        futures = [pool.submit(tcp_probe, dict(x), args.timeout) for x in rows]
        for f in as_completed(futures):
            results.append(f.result())
    results.sort(key=lambda x: (not x["tcp_reachable"], x["tcp_ms"]))
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    payload = {"generated_at": stamp, "source": args.url, "count": len(results),
               "note": "TCP check only; no VPN tunnel verified by this job.", "nodes": results}
    (out/"data.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    candidates = {"generated_at": stamp, "nodes": [x for x in results if x["tcp_reachable"]][:30]}
    (out/"vps_candidates.json").write_text(json.dumps(candidates, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = ["# TCP reachable candidates only; not tunnel-verified"]
    lines += [f'{x["host"]}:{x["port"]} | {x["country"]} | {x["tcp_ms"]} ms' for x in results if x["tcp_reachable"]]
    (out/"nodes.txt").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print(f'Candidates: {len(results)}; TCP reachable: {sum(x["tcp_reachable"] for x in results)}')

if __name__ == "__main__":
    main()
