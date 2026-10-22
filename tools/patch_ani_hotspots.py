#!/usr/bin/env python3
"""Copy .ani files while fixing zeroed small-size hotspots from the largest frame."""
import os
import struct
import sys

ICON_DIR = struct.Struct("<HHH")
ICON_ENTRY = struct.Struct("<BBBBHHII")
CHUNK = struct.Struct("<4sI")


def iter_chunks(blob, start, end):
    off = start
    while off + CHUNK.size <= end:
        fourcc, size = CHUNK.unpack_from(blob, off)
        data = off + CHUNK.size
        yield fourcc, data, size
        off = data + size + (size & 1)


def patch_icon_chunk(blob, data_off, size):
    if size < ICON_DIR.size:
        return 0
    reserved, kind, count = ICON_DIR.unpack_from(blob, data_off)
    if reserved != 0 or kind != 2 or count == 0:
        return 0
    if ICON_DIR.size + count * ICON_ENTRY.size > size:
        return 0

    entries = []
    for i in range(count):
        eoff = data_off + ICON_DIR.size + i * ICON_ENTRY.size
        w, h, _colors, _res, hx, hy, _bytes, _img = ICON_ENTRY.unpack_from(blob, eoff)
        entries.append((w or 256, h or 256, hx, hy, eoff))

    ref = max(entries, key=lambda e: e[0] * e[1])
    if ref[2] == 0 and ref[3] == 0:
        return 0  # nothing useful to scale from

    changed = 0
    for w, h, hx, hy, eoff in entries:
        if (hx, hy) != (0, 0) or (w, h) == (ref[0], ref[1]):
            continue
        nx = min(w - 1, round(ref[2] * w / ref[0]))
        ny = min(h - 1, round(ref[3] * h / ref[1]))
        struct.pack_into("<HH", blob, eoff + 4, nx, ny)
        changed += 1
    return changed


def patch_ani(blob):
    blob = bytearray(blob)
    if blob[:4] != b"RIFF" or blob[8:12] != b"ACON":
        raise ValueError("not an ANI file")
    changed = 0
    for fourcc, data, size in iter_chunks(blob, 12, len(blob)):
        if fourcc == b"LIST":
            for sub, sdata, ssize in iter_chunks(blob, data + 4, data + size):
                if sub == b"icon":
                    changed += patch_icon_chunk(blob, sdata, ssize)
    return bytes(blob), changed


def main():
    if len(sys.argv) != 3:
        print(f"usage: {sys.argv[0]} <input_folder> <output_folder>", file=sys.stderr)
        raise SystemExit(2)
    src, dst = sys.argv[1], sys.argv[2]
    os.makedirs(dst, exist_ok=True)
    for name in sorted(os.listdir(src)):
        if not name.lower().endswith(".ani"):
            continue
        with open(os.path.join(src, name), "rb") as f:
            patched, changed = patch_ani(f.read())
        with open(os.path.join(dst, name), "wb") as f:
            f.write(patched)
        print(f"{name}: patched {changed} hotspot(s)")


if __name__ == "__main__":
    main()
