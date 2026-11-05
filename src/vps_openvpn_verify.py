#!/usr/bin/env python3
"""Conservative optional OpenVPN session test; intended for a dedicated self-hosted VPS."""
import argparse, base64, json, re, subprocess, tempfile, time, select
from pathlib import Path

EXACT = {"client", "dev", "nobind", "persist-key", "persist-tun", "remote-cert-tls server",
         "auth-nocache", "tls-client", "route-nopull", "verb 3"}
PREFIX = ("proto ", "remote ", "resolv-retry ", "cipher ", "data-ciphers ", "auth ")
BLOCKED = ("script", "up ", "down ", "route ", "redirect-gateway", "dhcp-option",
           "plugin ", "management ", "config ", "include ", "log ", "status ",
           "daemon", "user ", "group ", "setenv ", "learn-address ")

def sanitize_profile(source):
    kept, block = [], None
    allowed_blocks = {"ca", "cert", "key", "tls-auth", "tls-crypt", "dh"}
    for raw in source.splitlines():
        line = raw.strip()
        if block:
            kept.append(line)
            if line.lower() == f"</{block}>":
                block = None
            continue
        if not line or line.startswith("#") or line.startswith(";"):
            continue
        m = re.fullmatch(r"<([a-zA-Z0-9_-]+)>", line)
        if m and m.group(1).lower() in allowed_blocks:
            block = m.group(1).lower()
            kept.append(line)
            continue
        low = line.lower()
        if any(low.startswith(x) for x in BLOCKED):
            continue
        if line in EXACT or any(low.startswith(x) for x in PREFIX):
            kept.append(line)
    if "client" not in kept: kept.insert(0, "client")
    if "route-nopull" not in kept: kept.append("route-nopull")
    kept += ["connect-retry-max 1", "connect-timeout 12", "resolv-retry 5"]
    return "\n".join(kept) + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="out/vps_candidates.json")
    ap.add_argument("--output", default="out/vps_results.json")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=25)
    args = ap.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    results = []
    for node in data.get("nodes", [])[:max(1, min(args.limit, 10))]:
        rec = {"host": node.get("host"), "port": node.get("port"),
               "tunnel_verified": False, "verification_level": "openvpn_session_test"}
        try:
            raw = base64.b64decode(node["profile_b64"], validate=True).decode("utf-8", "replace")
            safe = sanitize_profile(raw)
            with tempfile.TemporaryDirectory(prefix="aimili-ovpn-") as td:
                cfg = Path(td)/"candidate.ovpn"; cfg.write_text(safe, encoding="utf-8")
                proc = subprocess.Popen(
                    ["sudo", "-n", "openvpn", "--config", str(cfg), "--verb", "3"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
                )
                log_lines = []
                deadline = time.monotonic() + args.timeout
                ok = False
                try:
                    while time.monotonic() < deadline and proc.poll() is None:
                        ready, _, _ = select.select([proc.stdout], [], [], 0.5)
                        if ready:
                            line = proc.stdout.readline()
                            if line:
                                log_lines.append(line)
                                if "Initialization Sequence Completed" in line:
                                    ok = True
                                    break
                    if proc.poll() is None:
                        proc.terminate()
                        try:
                            proc.wait(timeout=3)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                            proc.wait(timeout=3)
                finally:
                    if proc.stdout:
                        proc.stdout.close()
                log = "".join(log_lines)
                rec["tunnel_verified"] = ok
                rec["summary"] = "OpenVPN session established" if ok else "No successful session detected before timeout/exit"
                rec["returncode"] = proc.returncode
                rec["diagnostic"] = re.sub(r"(?i)(password|auth-token)\\s+\\S+", r"\\1 [REDACTED]", log)[-1800:]
        except subprocess.TimeoutExpired:
            rec["summary"] = "Verification timed out"
        except Exception as e:
            rec["summary"] = f"Verification error: {type(e).__name__}: {str(e)[:120]}"
        results.append(rec)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps({"tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                             "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"VPS tests completed: {len(results)}")

if __name__ == "__main__":
    main()
