#!/usr/bin/env python3
"""
bitpirate_to_savvycan.py - Convert an ESP32-Bit-Pirate CAN 'sniff' log
into a SavvyCAN-native (GVRET) CSV file, with optional DBC decoding.

by magikh0e -- 07.2026

Bit-Pirate's CAN sniffer prints frames like:

     26 | ID: 0x123 | DLC: 8 | Data: AA BB 01 02 03 04 05 06

(the leading inbox emoji and any non-frame status lines are ignored).

SavvyCAN native CSV (V2) columns:
    Time Stamp,ID,Extended,Dir,Bus,LEN,D1,D2,D3,D4,D5,D6,D7,D8
with Time Stamp in MICROSECONDS.

TIMING LIMITATION: Bit-Pirate does not emit a per-frame timestamp, so
timing is synthesized. Frames are spaced --interval microseconds apart
(default 1000 = 1 ms). Order is preserved; timing is NOT real. Fine for
decoding IDs/data, DBC work and ASCII scans; not for bus-timing analysis.

DBC DECODING (--dbc): also writes <out>_decoded.txt with human-readable
signal values. Handles standard scalar signals, Intel (little-endian) and
Motorola (big-endian) byte order, signed/unsigned, factor/offset. It does
NOT handle multiplexed signals or CAN-FD. For the full DBC spec, load the
CSV plus your .dbc into SavvyCAN, which decodes everything.

Usage:
    python3 bitpirate_to_savvycan.py capture.txt -o capture_savvy.csv
    python3 bitpirate_to_savvycan.py capture.txt
    python3 bitpirate_to_savvycan.py capture.txt --dbc car.dbc
    cat capture.txt | python3 bitpirate_to_savvycan.py -
"""

import argparse
import re
import sys

FRAME_RE = re.compile(
    r"ID:\s*0x([0-9A-Fa-f]+)\s*\|\s*DLC:\s*(\d+)\s*\|\s*Data:\s*([0-9A-Fa-f\s]*)",
)


def parse_line(line):
    m = FRAME_RE.search(line)
    if not m:
        return None
    frame_id = int(m.group(1), 16)
    dlc = int(m.group(2))
    data = [int(b, 16) for b in m.group(3).split()]
    if dlc > len(data):
        dlc = len(data)
    dlc = max(0, min(dlc, 8))
    data = data[:dlc]
    return frame_id, dlc, data


def to_csv_row(ts_us, frame_id, dlc, data):
    extended = "true" if frame_id > 0x7FF else "false"
    id_hex = "%08X" % frame_id
    bytes_hex = "".join("%02X," % b for b in data)  # trailing comma matches SavvyCAN
    return "%d,%s,%s,Rx,0,%d,%s" % (ts_us, id_hex, extended, dlc, bytes_hex)


# ---------------- Minimal DBC support ----------------

class Signal:
    __slots__ = ("name", "start", "length", "little_endian", "signed",
                 "factor", "offset", "unit")

    def __init__(self, name, start, length, little_endian, signed, factor, offset, unit):
        self.name = name
        self.start = start
        self.length = length
        self.little_endian = little_endian
        self.signed = signed
        self.factor = factor
        self.offset = offset
        self.unit = unit

    def decode(self, data):
        raw = extract_raw(data, self.start, self.length, self.little_endian)
        if self.signed and (raw & (1 << (self.length - 1))):
            raw -= (1 << self.length)
        return raw * self.factor + self.offset


def extract_raw(data, start, length, little_endian):
    """Unsigned raw integer from an 8-byte payload. DBC LSB0 bit numbering:
    bit = byte*8 + bit_in_byte."""
    buf = list(data) + [0] * (8 - len(data))
    raw = 0
    if little_endian:
        for i in range(length):
            pos = start + i
            if (buf[pos >> 3] >> (pos & 7)) & 1:
                raw |= (1 << i)
    else:
        # Motorola forward sawtooth: start bit is the MSB.
        pos = start
        for _ in range(length):
            bit = (buf[pos >> 3] >> (pos & 7)) & 1
            raw = (raw << 1) | bit
            if (pos & 7) == 0:
                pos += 15
            else:
                pos -= 1
    return raw


SG_RE = re.compile(
    r'SG_\s+(\w+)\s*(?:m\d+|M)?\s*:\s*(\d+)\|(\d+)@([01])([+-])\s*'
    r'\(([^,]+),([^)]+)\)\s*\[[^\]]*\]\s*"([^"]*)"'
)


def load_dbc(path):
    """Return {message_id:int -> (name, [Signal,...])}. Ignores multiplexing."""
    messages = {}
    current = None
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if s.startswith("BO_"):
                parts = s.split()
                mid = int(parts[1]) & 0x1FFFFFFF  # strip extended flag bit
                name = parts[2].rstrip(":")
                current = (name, [])
                messages[mid] = current
            elif s.startswith("SG_") and current is not None:
                m = SG_RE.search(s)
                if not m:
                    continue
                name, start, length, order, sign, factor, offset, unit = m.groups()
                current[1].append(Signal(
                    name, int(start), int(length),
                    little_endian=(order == "1"),
                    signed=(sign == "-"),
                    factor=float(factor), offset=float(offset), unit=unit,
                ))
    return messages


def fmt_val(v):
    return "%.6g" % v


def convert(infile, csv_out, interval, dbc=None, decoded_out=None):
    csv_out.write("Time Stamp,ID,Extended,Dir,Bus,LEN,D1,D2,D3,D4,D5,D6,D7,D8\n")
    ts = 0
    n = 0
    for line in infile:
        parsed = parse_line(line)
        if parsed is None:
            continue
        frame_id, dlc, data = parsed
        csv_out.write(to_csv_row(ts, frame_id, dlc, data) + "\n")
        if decoded_out is not None:
            hexs = " ".join("%02X" % b for b in data)
            head = "[%8dus] 0x%03X [%d] %s" % (ts, frame_id, dlc, hexs)
            msg = dbc.get(frame_id)
            if msg:
                sigs = "  ".join(
                    "%s=%s%s" % (s.name, fmt_val(s.decode(data)), s.unit) for s in msg[1]
                )
                decoded_out.write("%s  %s: %s\n" % (head, msg[0], sigs))
            else:
                decoded_out.write("%s  (no DBC match)\n" % head)
        ts += interval
        n += 1
    return n


def main():
    ap = argparse.ArgumentParser(description="Convert Bit-Pirate CAN sniff log to SavvyCAN CSV.")
    ap.add_argument("input", help="Bit-Pirate capture .txt, or '-' for stdin")
    ap.add_argument("-o", "--output", help="output CSV (default: <input>_savvy.csv, or stdout for '-')")
    ap.add_argument("--interval", type=int, default=1000,
                    help="synthetic microseconds between frames (default 1000)")
    ap.add_argument("--dbc", help="optional .dbc file for a decoded sidecar log")
    args = ap.parse_args()

    if args.input == "-":
        infile = sys.stdin
        csv_out = open(args.output, "w") if args.output else sys.stdout
        out_base = args.output or None
    else:
        infile = open(args.input, "r", encoding="utf-8", errors="replace")
        out_path = args.output or re.sub(r"\.[^.]*$", "", args.input) + "_savvy.csv"
        csv_out = open(out_path, "w")
        out_base = out_path

    dbc = load_dbc(args.dbc) if args.dbc else None
    decoded_out = None
    dec_path = None
    if dbc is not None and out_base:
        dec_path = re.sub(r"\.[^.]*$", "", out_base) + "_decoded.txt"
        decoded_out = open(dec_path, "w")

    try:
        n = convert(infile, csv_out, args.interval, dbc, decoded_out)
    finally:
        if infile is not sys.stdin:
            infile.close()
        if csv_out is not sys.stdout:
            csv_out.close()
        if decoded_out is not None:
            decoded_out.close()

    if csv_out is not sys.stdout:
        print("Wrote %d frames -> %s" % (n, out_base), file=sys.stderr)
        if dec_path:
            print("Wrote decoded sidecar -> %s" % dec_path, file=sys.stderr)


if __name__ == "__main__":
    main()
