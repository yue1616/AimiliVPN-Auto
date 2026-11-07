#!/usr/bin/env python3
"""Bounded OpenVPN session verification for a dedicated Linux VPS runner."""
from __future__ import annotations
import argparse, base64, json, os, re, selectors, subprocess, tempfile, time
from pathlib import Path

EXACT = {"client", "dev tun", "nobind", "persist-key", "persist-tun",
         "remote-cert-tls server", "auth-nocache", "tls-client", "route-nopull"}
PREFIX = ("cipher ", "data-ciphers ", "auth ", "key-direction ")
BLOCKS = {"ca", "cert", "key", "tls-auth", "tls-crypt", "dh"}
BLOCKED = ("script-security", "up ", "down ", "route ", "redirect-gateway",
           "dhcp-option", "plugin ", "management ", "config ", "include ",
           "log ", "status ", "daemon", "user ", "group ", "setenv ",
           "learn-address", "auth-user-pass", "askpass ", "cd ", "chroot ",
           "ipchange ", "client-connect ", "client-disconnect ")

def sanitize_profile(source: str, host: str, port: int) -> str:
    if not host or any(c.isspace() for c in host):
        raise ValueError("invalid candidate host")
    port = int(port)
    if not 1 <= port <= 65535:
        raise ValueError("invalid candidate port")
    kept, block, proto, cipher = [], None, None, None
    for raw in source.splitlines():
        line = raw.strip()
        if block:
            kept.append(line)
            if line.lower() == f"</{block}>":
                block = None
            continue
        if not line or line.startswith(("#", ";")):
            continue
        m = re.fullmatch(r"<([a-zA-Z0-9_-]+)>", line)
        if m:
            tag = m.group(1).lower()
            if tag in BLOCKS:
                block = tag
                kept.append(f"<{tag}>")
            continue
        low = line.lower()
        if low.startswith("proto "):
            candidate = low.split(None, 1)[1]
            if candidate == "tcp":
                proto = "tcp-client"
            elif candidate in {"udp", "udp4", "udp6", "tcp-client", "tcp4-client", "tcp6-client"}:
                proto = candidate
            continue
        if low.startswith("cipher "):
            cipher = line.split(None, 1)[1]
            kept.append(line)
            continue
        # Ignore every source-provided remote: only the collector's endpoint is tested.
        if low.startswith("remote ") or any(low.startswith(x) for x in BLOCKED):
            continue
        if low in EXACT or any(low.startswith(x) for x in PREFIX):
            kept.append(line)
    if block:
        raise ValueError(f"unterminated inline <{block}> block")
    if not any(x.lower() == "client" for x in kept):
        kept.insert(0, "client")
    for directive in ("dev tun", "nobind", "route-nopull"):
        if not any(x.lower() == directive for x in kept):
            kept.append(directive)
    kept.extend([f"proto {proto or 'udp'}", f"remote {host} {port}"])
    # SoftEther-generated VPNGate profiles often use legacy CBC data ciphers.
    if cipher and cipher.upper() not in {"AES-128-GCM", "AES-256-GCM", "CHACHA20-POLY1305"}:
        kept.append(f"data-ciphers-fallback {cipher}")
    kept.extend(["connect-retry-max 1", "connect-timeout 12", "resolv-retry 5", "verb 3"])
    return "\n".join(kept) + "\n"

def redact_log(value: str) -> str:
    value = re.sub(r"(?i)(password|auth-token)(\s+)[^\s]+", r"\1\2[REDACTED]", value)
    return value[-1800:]

def run_openvpn(config_text: str, timeout: int):
    with tempfile.TemporaryDirectory(prefix="aimili-ovpn-") as td:
        cfg = Path(td) / "candidate.ovpn"
        cfg.write_text(config_text, encoding="utf-8")
        proc = subprocess.Popen(["sudo", "-n", "openvpn", "--config", str(cfg), "--verb", "3"],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                bufsize=0, start_new_session=True)
        assert proc.stdout is not None
        output, success = bytearray(), False
        deadline = time.monotonic() + max(5, timeout)
        with selectors.DefaultSelector() as selector:
            selector.register(proc.stdout, selectors.EVENT_READ)
            try:
                while time.monotonic() < deadline:
                    if proc.poll() is not None:
                        events = selector.select(0)
                        if not events:
                            break
                    else:
                        events = selector.select(min(.5, max(0, deadline-time.monotonic())))
                        if not events:
                            continue
                    chunk = os.read(proc.stdout.fileno(), 65536)
                    if not chunk:
                        break
                    output.extend(chunk)
                    if b"Initialization Sequence Completed" in output:
                        success = True
                        break
                    if len(output) > 256_000:
                        del output[:-128_000]
            finally:
                selector.unregister(proc.stdout)
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait(timeout=3)
                proc.stdout.close()
        return success, redact_log(output.decode("utf-8", "replace")), proc.returncode

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="out/vps_candidates.json")
    ap.add_argument("--output", default="out/vps_results.json")
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--timeout", type=int, default=35)
    args = ap.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    results = []
    for node in data.get("nodes", [])[:max(1, min(args.limit, 10))]:
        rec = {"host": node.get("host"), "port": node.get("port"),
               "country": node.get("country"), "tcp_reachable": bool(node.get("tcp_reachable")),
               "tunnel_verified": False,
               "verification_level": "openvpn_initialization_sequence"}
        try:
            encoded = node.get("profile_b64")
            if not encoded:
                raise ValueError("candidate has no embedded OpenVPN profile")
            profile = base64.b64decode(encoded, validate=True).decode("utf-8", "replace")
            config = sanitize_profile(profile, str(node["host"]), int(node["port"]))
            ok, diagnostic, returncode = run_openvpn(config, args.timeout)
            rec.update(tunnel_verified=ok, returncode=returncode, diagnostic=diagnostic,
                       summary=("OpenVPN initialization completed" if ok else
                                "OpenVPN session not established before exit/timeout"))
        except Exception as exc:
            rec["summary"] = f"Verification error: {type(exc).__name__}: {str(exc)[:160]}"
        results.append(rec)
        print(f'{rec["host"]}:{rec["port"]} -> {"TUNNEL_OK" if rec["tunnel_verified"] else "NOT_VERIFIED"}')
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"tested_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "verification_method": "OpenVPN Initialization Sequence Completed",
               "tested_count": len(results),
               "verified_count": sum(bool(x["tunnel_verified"]) for x in results),
               "results": results}
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f'VPS tests completed: {len(results)}; verified: {payload["verified_count"]}')

if __name__ == "__main__":
    main()
