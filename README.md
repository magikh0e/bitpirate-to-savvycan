# bitpirate-to-savvycan

Two small **Python 3, standard-library-only** tools for getting a CAN capture off an
ESP32 [**Bit-Pirate**](https://github.com/geo-tp/ESP32-Bit-Pirate) sniffer and into [SavvyCAN](https://github.com/collin80/SavvyCAN):

- **`bitpirate_to_savvycan.py`** — convert a Bit-Pirate sniff log into a SavvyCAN-native (GVRET) CSV, with optional DBC decoding.
- **`bp_fetch.py`** — pull a capture straight off the device's LittleFS over Wi-Fi, and (optionally) hand it to the converter in one step.

Nothing to install — both use only Python's standard library.

---

## The one-liner

```
python3 bp_fetch.py 192.168.4.1 --file can_capture.txt --convert
# downloads can_capture.txt off the device, writes can_capture_savvy.csv
```

Then in SavvyCAN: **File → Load Logs → GVRET/CSV**. Or run either tool on its own.

---

## `bitpirate_to_savvycan.py`

Converts a Bit-Pirate CAN sniff log into a SavvyCAN-native (GVRET) CSV.

Bit-Pirate's sniffer prints one frame per line:

```
📥 26 | ID: 0x123 | DLC: 8 | Data: AA BB 01 02 03 04 05 06
```

The parser is deliberately loose — it skips the leading inbox emoji and any non-frame
status lines, keys off the `ID: / DLC: / Data:` fields, trusts the bytes actually present
(clamping a lying DLC down to what's really there), and flags any ID above `0x7FF` as
extended. Output is SavvyCAN native CSV (V2):

```
Time Stamp,ID,Extended,Dir,Bus,LEN,D1,D2,D3,D4,D5,D6,D7,D8
```

with the timestamp in **microseconds**.

```
python3 bitpirate_to_savvycan.py capture.txt -o capture_savvy.csv
python3 bitpirate_to_savvycan.py capture.txt          # writes capture_savvy.csv
python3 bitpirate_to_savvycan.py capture.txt --dbc car.dbc
cat capture.txt | python3 bitpirate_to_savvycan.py -  # stdin -> stdout
```

Flags: `[-o OUT] [--interval US] [--dbc FILE]`

> ⚠️ **Timing is synthetic.** Bit-Pirate doesn't emit a per-frame timestamp, so frames
> are spaced `--interval` microseconds apart (default `1000` = 1 ms). Frame *order* is
> preserved, but absolute and relative timing is fabricated — fine for decoding IDs/data,
> DBC work, and ASCII scans; **not** for bus-timing or inter-frame-gap analysis.

### DBC decoding

`--dbc car.dbc` also writes a `<out>_decoded.txt` sidecar with human-readable signal values:

```
[       0us] 0x123 [8] AA BB 01 02 03 04 05 06  EngineData: RPM=12010.5rpm  Temp=-39degC  Gear=2
[    1000us] 0x456 [3] 11 22 33  (no DBC match)
```

Handles standard scalar signals — Intel (little-endian) and Motorola (big-endian) byte
order, signed/unsigned, factor/offset. It does **not** handle multiplexed signals or
CAN-FD; for the full DBC spec, load the CSV plus your `.dbc` into SavvyCAN, which decodes
everything.

---

## `bp_fetch.py`

Pulls a capture file straight off the Bit-Pirate's LittleFS over its Wi-Fi web interface,
using the device's HTTP API:

```
GET /littlefs/list?dir=/            -> JSON directory listing
GET /littlefs/download?file=<name>  -> raw file stream
```

Run it on a machine on the same network as the device (or joined to the Bit-Pirate's own AP).

```
python3 bp_fetch.py 192.168.4.1 --list                      # list the filesystem
python3 bp_fetch.py 192.168.4.1 --file can_capture.txt       # download one file
python3 bp_fetch.py 192.168.4.1 --file can_capture.txt --convert   # download + convert
```

Flags: `[--list] [--dir DIR] [--file FILE] [-o OUT] [--convert] [--dbc FILE] [--timeout SEC]`

With `--convert` it shells out to `bitpirate_to_savvycan.py` (keep both in the same
directory), passing `--dbc` through if you gave one.

---

## Requirements

- Python 3.6+ — standard library only, no third-party packages.
- [SavvyCAN](https://github.com/collin80/SavvyCAN) to view/analyse the resulting CSV.

## See also

- [magikh0e.pl — Car Hacking scripts](https://magikh0e.pl/pubCarHacking/#scripts) — these
  tools written up alongside the rest of the CAN bus / car-hacking material.

Provided as-is, no warranty. by magikh0e.
