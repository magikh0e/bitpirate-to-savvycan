#!/usr/bin/env python3
"""
bp_fetch.py - Pull a capture file straight off an ESP32-Bit-Pirate's
LittleFS over its Wi-Fi web interface, and optionally convert it to a
SavvyCAN CSV in one step.

by magikh0e -- 07.2026

Bit-Pirate's HTTP API (from src/Servers/HttpServer.cpp):
    GET  /littlefs/list?dir=/            -> JSON directory listing
    GET  /littlefs/download?file=<name>  -> raw file stream

Only Python's standard library is used (urllib), so there is nothing to
install. Run this on a machine that is on the same network as the device
(or joined to the Bit-Pirate's own AP).

Examples:
    # List what's on the device
    python3 bp_fetch.py 192.168.4.1 --list

    # Download a capture
    python3 bp_fetch.py 192.168.4.1 --file can_capture.txt -o can_capture.txt

    # Download AND convert to SavvyCAN CSV in one shot
    python3 bp_fetch.py 192.168.4.1 --file can_capture.txt --convert
"""

import argparse
import json
import subprocess
import sys
import urllib.request
import urllib.parse


def base_url(host):
    if not host.startswith(("http://", "https://")):
        host = "http://" + host
    return host.rstrip("/")


def http_get(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "bp_fetch"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def list_dir(host, directory, timeout):
    url = base_url(host) + "/littlefs/list?" + urllib.parse.urlencode({"dir": directory})
    data = json.loads(http_get(url, timeout).decode("utf-8", "replace"))
    return data


def download(host, filename, out_path, timeout):
    url = base_url(host) + "/littlefs/download?" + urllib.parse.urlencode({"file": filename})
    blob = http_get(url, timeout)
    with open(out_path, "wb") as f:
        f.write(blob)
    return len(blob)


def print_listing(data):
    print(f"dir: {data.get('dir', '/')}   used {data.get('used','?')}/{data.get('total','?')} bytes")
    entries = data.get("entries", [])
    if not entries:
        print("  (empty)")
    for e in entries:
        kind = "DIR " if e.get("isDir") else "file"
        print(f"  [{kind}] {e['name']:<32} {e.get('size', 0):>8} B")


def main():
    ap = argparse.ArgumentParser(description="Fetch a capture off Bit-Pirate LittleFS over HTTP.")
    ap.add_argument("host", help="device IP or URL, e.g. 192.168.4.1")
    ap.add_argument("--list", action="store_true", help="list files and exit")
    ap.add_argument("--dir", default="/", help="directory to list (default /)")
    ap.add_argument("--file", help="filename on the device to download")
    ap.add_argument("-o", "--output", help="local output path (default: same basename)")
    ap.add_argument("--convert", action="store_true",
                    help="after download, run bitpirate_to_savvycan.py to make a SavvyCAN CSV")
    ap.add_argument("--dbc", help="pass a .dbc through to bitpirate_to_savvycan.py for a decoded sidecar")
    ap.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout seconds")
    args = ap.parse_args()

    try:
        if args.list or not args.file:
            print_listing(list_dir(args.host, args.dir, args.timeout))
            if not args.file:
                return
        out_path = args.output or args.file.split("/")[-1]
        n = download(args.host, args.file, out_path, args.timeout)
        print(f"Downloaded {n} bytes -> {out_path}", file=sys.stderr)
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    if args.convert:
        cmd = [sys.executable, "bitpirate_to_savvycan.py", out_path]
        if args.dbc:
            cmd += ["--dbc", args.dbc]
        print("Running:", " ".join(cmd), file=sys.stderr)
        sys.exit(subprocess.call(cmd))


if __name__ == "__main__":
    main()
