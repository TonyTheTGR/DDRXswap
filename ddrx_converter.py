#!/usr/bin/env python3
"""DDR X USA multi-song ISO converter v0.4 (experimental). Read original ISO, write new ISO.

Requires sn2.py, sm2ddr.py (upstream SN2 converter), numpy and ffmpeg.
Adds translated title cards, X-scale meters, BPM display and optional Shock Arrow events.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import shutil
import struct
import sys
import tempfile
from pathlib import Path

import sn2
import sm2ddr

ARCHIVES = ("SYSTEM.DAT", "IMAGE.DAT", "SOUND.DAT", "MDB_X1.DAT")
ELF = "SLUS_217.67"
SONG_COUNT = 77
RECORD_SIZE = 0x98
CSQ = "mdb/csq_all.bin"
ART = "mdb/music_dt.bin"


class DDRXError(sn2.SN2Error):
    pass


def slot_records(elf: bytes) -> dict:
    """Discover the sequence of 77 DDR X records, checking code and sequence number.

    For the USA executable, consecutive records have stride 0x98; at offsets
    +6 and +8 are matching one-based song numbers, mapping to pack indices.
    No absolute executable address is assumed.
    """
    codes = {x.decode("ascii") for x in re.findall(rb"MUSIC/([a-z0-9]{4,5})\.vig\x00", elf)}
    candidates = []
    pattern = re.compile(rb"([a-z0-9]{4,5})\x00{1,2}")
    for m in pattern.finditer(elf):
        at = m.start()
        if m.group(1).decode("ascii") not in codes or at + 10 > len(elf):
            continue
        first, second = struct.unpack_from("<HH", elf, at + 6)
        if first == second == 1:
            candidates.append(at)
    for start in candidates:
        found = {}
        for i in range(SONG_COUNT):
            at = start + i * RECORD_SIZE
            if at + RECORD_SIZE > len(elf):
                break
            raw = elf[at:at + 6]
            code = raw.split(b"\0", 1)[0]
            if not re.fullmatch(rb"[a-z0-9]{4,5}", code):
                break
            n1, n2 = struct.unpack_from("<HH", elf, at + 6)
            name = code.decode("ascii")
            if n1 != i + 1 or n2 != i + 1 or name not in codes or name in found:
                break
            found[name] = {"index": i, "record_offset": at}
        if len(found) == SONG_COUNT:
            return found
    raise DDRXError("Couldn't identify the 77-record DDR X USA song table; disc revision may differ")


def slot_titles(elf: bytes, records: dict) -> dict:
    """Get the game program's code/title pairs. Incomplete titles fall back to codes."""
    out = {}
    # The USA executable has a separate zero-terminated code/title string table.
    for code in records:
        pat = re.escape(code.encode("ascii")) + rb"\x00"
        for m in re.finditer(pat, elf):
            s = m.end()
            end = elf.find(b"\0", s, min(s + 130, len(elf)))
            if end < 0 or end - s < 3:
                continue
            title = elf[s:end]
            if any(c < 32 for c in title) or not all(c < 127 for c in title):
                continue
            val = title.decode("ascii", "replace")
            if (not val.startswith(("MUSIC/", "SEL/", "MOVIE/")) and
                    (" " in val or len(val) > 12)):
                out[code] = val
                break
    return out


class DDRXGame(sn2.Game):
    def _finish(self):
        if self.elf_name.upper() != ELF:
            raise DDRXError(f"This is not DDR X USA ({ELF}): {self.elf_name}")
        if not self.iso:
            raise DDRXError("Please supply the unmodified DDR X USA ISO, not a disc folder")
        for name in ARCHIVES:
            if "DATA/" + name not in self.files:
                raise DDRXError(f"Missing DATA/{name}")
        self._segments()
        self.toc = self._read_toc()
        self.slot_map = slot_records(bytes(self.elf))
        self.title_map = slot_titles(bytes(self.elf), self.slot_map)
        for code in self.slot_map:
            self.entry(f"MUSIC/{code}.vig")
            self.entry(f"SEL/{code}_s.vig")
        self.entry(CSQ)
        self.entry(ART)

    def dat_lba(self, entry):
        return self.files["DATA/" + ARCHIVES[entry["archive"]]][0]

    def dat_path(self, entry):
        return self.folder / "DATA" / ARCHIVES[entry["archive"]]


def split_pack(data: bytes, count=SONG_COUNT) -> list[bytes]:
    if len(data) < count * 4:
        raise DDRXError("Pack too small for 77-entry offset table")
    offsets = struct.unpack_from(f"<{count}I", data)
    if offsets[0] != 4 * count or offsets[-1] >= len(data) or any(
            a >= b for a, b in zip(offsets, offsets[1:])):
        raise DDRXError("Invalid DDR X packed resource offsets")
    return [data[a:b] for a, b in zip(offsets, offsets[1:] + (len(data),))]


def banner_template_valid(template: bytes) -> bool:
    """Only the verified 256x80, 8-bit/256-color stock layout is safe for the
    SuperNOVA 2 banner writer; other layouts stay untouched.

    76 stock banners use the plain TIM2 layout (picture header at byte 16).
    Here It Goes Again (heit) stores the same 256x80 image in the 128-byte
    aligned layout (TIM2 byte 5 = 1, picture header at byte 128); reading it
    at byte 16 found only padding, which looked like an empty placeholder.
    """
    if len(template) < 64 or template[:4] != b"TIM2":
        return False
    q = sn2.tim2_header_offset(template)
    if len(template) < q + 48:
        return False
    total, clut_size, image_size, header_size = struct.unpack_from("<IIIH", template, q)
    width, height = struct.unpack_from("<HH", template, q + 20)
    return (width == 256 and height == 80 and image_size == width * height
            and clut_size == 1024 and header_size >= 48
            and total >= header_size + image_size + clut_size
            and q + total <= len(template))


def display_metadata(simfile: Path, song) -> tuple[str, str]:
    """Prefer StepMania transliterations, preserving raw titles as fallbacks."""
    fields = {}
    for tag, value in sm2ddr.parse_msd(sm2ddr.read_text(simfile)):
        if tag in ("TITLE", "ARTIST", "TITLETRANSLIT", "ARTISTTRANSLIT"):
            fields.setdefault(tag, value.strip())
    title = fields.get("TITLETRANSLIT") or fields.get("TITLE") or song.title
    artist = fields.get("ARTISTTRANSLIT") or fields.get("ARTIST") or song.artist
    return title, artist


def title_template_valid(template: bytes) -> bool:
    """DDR X stores a version-1 TIM2 title: 128-byte extended header."""
    if len(template) < 192 or template[:4] != b"TIM2" or template[5] != 1:
        return False
    q = 128
    total, clut_size, image_size, header_size = struct.unpack_from("<IIIH", template, q)
    width, height = struct.unpack_from("<HH", template, q + 20)
    return (width == 224 and height == 32 and image_size == 3584
            and clut_size == 128 and header_size >= 48
            and total >= header_size + image_size + clut_size
            and q + total <= len(template))


def render_title_card(template: bytes, title: str, artist: str) -> bytes:
    """Render into DDR X's native extended-header TIM2, retaining original CLUT."""
    if not title_template_valid(template):
        # The final title entry uses ordinary TIM2 v0, not extended v1.
        if (len(template) >= 64 and template[:4] == b"TIM2" and template[5] == 0
                and struct.unpack_from("<HH", template, 36) == (224, 32)
                and struct.unpack_from("<II", template, 20) == (64, 3584)):
            return sn2.title_tim2(template, title, artist)
        raise DDRXError("Unsupported DDR X title card template")
    import numpy as np
    canvas = np.zeros((32, 224), np.uint8)
    canvas[:18, 2:222] = sn2._fit_line(title, 15, 18)
    canvas[18:32, 2:222] = sn2._fit_line(artist, 11, 14)
    level = (canvas.astype(int) * 15 + 127) // 255
    pixels = (level[:, 0::2] | (level[:, 1::2] << 4)).astype(np.uint8).tobytes()
    q = 128
    _, _, img_size, hs = struct.unpack_from("<IIIH", template, q)
    if len(pixels) != img_size:
        raise DDRXError("Wrong title pixel payload length")
    pos = q + hs
    return template[:pos] + pixels + template[pos + img_size:]


# DDR X USA song record rating bytes, confirmed against the stock ELF.
# +36 is NOT a difficulty rating; +42 and +47 are also not ratings.
# The five SP ratings follow at +37..+41 (Beginner, Basic, Difficult,
# Expert, Challenge). DP uses +43..+46 (Basic, Difficult, Expert,
# Challenge). No Double Beginner selection exists.
RATING_OFFSETS = {
    ("dance-single", "beginner"): 37,
    ("dance-single", "easy"): 38,
    ("dance-single", "medium"): 39,
    ("dance-single", "hard"): 40,
    ("dance-single", "challenge"): 41,
    ("dance-double", "easy"): 43,
    ("dance-double", "medium"): 44,
    ("dance-double", "hard"): 45,
    ("dance-double", "challenge"): 46,
}


def chart_meters(song) -> tuple[dict[int, int], list[str]]:
    """Map imported difficulties to native DDR X record-relative rating bytes.

    A missing chart is represented by zero in its corresponding rating.
    The game's selection behavior must still be verified in PCSX2.
    """
    values = {offset: 0 for offset in RATING_OFFSETS.values()}
    warnings = []
    seen = set()
    for chart in song.charts:
        key = (chart.style, chart.difficulty)
        if key not in RATING_OFFSETS:
            if key == ("dance-double", "beginner"):
                warnings.append("Double Beginner ignored: unsupported by DDR X")
            continue
        if key in seen:
            warnings.append(f"Duplicate {chart.style}/{chart.difficulty}: first meter kept")
            continue
        seen.add(key)
        meter = int(chart.meter)
        if meter < 1 or meter > 20:
            warnings.append(f"{chart.style}/{chart.difficulty} meter {meter} outside 1-20; clamped")
            meter = max(1, min(20, meter))
        values[RATING_OFFSETS[key]] = meter
    return values, warnings


def patch_bpm(elf: bytearray, record_offset: int, song) -> dict:
    """Write DDR X song-select maximum/minimum BPM at record +28/+30.

    Only positive finite BPM values representable as unsigned 16-bit ints
    are accepted; actual beat timing remains in the chart's tempo chunk.
    """
    bpms = [float(bpm) for _, bpm in song.bpms]
    if not bpms or any(not math.isfinite(v) or v <= 0 or v > 65535 for v in bpms):
        raise DDRXError("BPM metadata requires positive finite BPM values <= 65535")
    old = struct.unpack_from("<HH", elf, record_offset + 28)
    maximum, minimum = round(max(bpms)), round(min(bpms))
    maximum, minimum = max(1, maximum), max(1, minimum)
    struct.pack_into("<HH", elf, record_offset + 28, maximum, minimum)
    return {"old": old, "new": (maximum, minimum)}


def patch_ratings(elf: bytearray, record_offset: int, song) -> dict:
    """Write only the nine mapped difficulty-rating bytes of a DDR X record.

    The previous v0.3 accidentally treated +36 as SP Beginner; this shifted
    the five SP levels and left the stock Challenge rating at +41.
    Bytes +36, +42 and +47 must not be changed by this function.
    """
    values, warnings = chart_meters(song)
    before = bytes(elf[record_offset + 36:record_offset + 48])
    for offset, meter in values.items():
        elf[record_offset + offset] = meter
    after = bytes(elf[record_offset + 36:record_offset + 48])
    return {"before": list(before), "after": list(after), "warnings": warnings,
            "levels": {f"{style}/{diff}": values[offset]
                       for (style, diff), offset in RATING_OFFSETS.items()}}


def build_art_entry(stock: bytes, song, simfile: Path, warnings=None, *, slot="", replace_banner=True) -> bytes:
    if len(stock) < 8:
        raise DDRXError("Invalid stock artwork entry")
    start, end = struct.unpack_from("<II", stock)
    if start != 8 or not 8 < end < len(stock):
        raise DDRXError("Invalid stock artwork offsets")
    title = sn2.lz_decompress(stock[start:end])
    banner = sn2.lz_decompress(stock[end:])
    if not title.startswith(b"TIM2") or not banner.startswith(b"TIM2"):
        raise DDRXError("Stock artwork entry does not contain TIM2 images")
    new_title, new_artist = display_metadata(simfile, song)
    try:
        title = render_title_card(title, new_title, new_artist)
    except DDRXError:
        warning = f"WARNING: {slot or 'song'} title template unsupported; original title retained"
        print(warning)
        if warnings is not None:
            warnings.append(warning)
    if replace_banner:
        if banner_template_valid(banner):
            image = sn2.song_art(song, simfile)
            if image:
                banner = sn2.banner_tim2(banner, image)
        else:
            warning = (f"WARNING: {slot or 'song'} has an unsupported stock "
                       "TIM2 banner template; banner preserved but title card updated")
            print(warning)
            if warnings is not None:
                warnings.append(warning)
    encoded_title = sn2.lz_compress(title)
    encoded_banner = sn2.lz_compress(banner)
    return struct.pack("<II", 8, 8 + len(encoded_title)) + encoded_title + encoded_banner


def repack(original: bytes, items: list[bytes], changed: set[int],
           *, align: int, images: bool) -> bytes:
    result = sn2.fit_pack(items, changed, len(original), align, images, lambda x: print(x))
    check = split_pack(result)
    for idx in changed:
        if images:
            a, b = struct.unpack_from("<II", check[idx])
            if a != 8 or b <= a:
                raise DDRXError(f"Art entry {idx} did not roundtrip")
            for s in (check[idx][a:b], check[idx][b:]):
                if not sn2.lz_decompress(s).startswith(b"TIM2"):
                    raise DDRXError(f"Artwork for index {idx} decompression failed")
        elif sn2.lz_decompress(check[idx]) != sn2.lz_decompress(items[idx]):
            raise DDRXError(f"Chart entry {idx} decompression failed")
    return result


def normalize_jobs(payload, game: DDRXGame) -> list[dict]:
    if not isinstance(payload, list) or not payload:
        raise DDRXError("Jobs must be a nonempty JSON list")
    out = []
    used = set()
    for i, job in enumerate(payload, 1):
        if not isinstance(job, dict) or not isinstance(job.get("slot"), str) or not isinstance(job.get("song"), str):
            raise DDRXError(f"Job {i}: each job needs a slot code and song path")
        code = job["slot"].lower().strip()
        if code not in game.slot_map:
            raise DDRXError(f"Job {i}: unknown DDR X slot '{code}'")
        if code in used:
            raise DDRXError(f"Job {i}: duplicate target slot '{code}'")
        used.add(code)
        source = Path(job["song"]).expanduser().resolve()
        if not source.exists():
            raise DDRXError(f"Job {i}: missing song {source}")
        out.append({"slot": code, "song": source,
                    "banner": bool(job.get("banner", False))})
    return out


def make_iso(iso: Path, output: Path, payload: list, *, charts_only=False, update_ratings=True,
             update_bpm=True, shock_mode="ignore"):
    if shock_mode not in ("ignore", "all", "any"):
        raise DDRXError("Shock mode must be ignore, all, or any")
    iso, output = iso.expanduser().resolve(), output.expanduser().resolve()
    if not iso.is_file() or iso.suffix.lower() != ".iso":
        raise DDRXError("Input must be an existing .iso")
    if iso == output or output.exists():
        raise DDRXError("Output must be a NEW, unused ISO path (input is never overwritten)")
    if not output.parent.is_dir():
        raise DDRXError("Output folder does not exist")
    if shutil.disk_usage(output.parent).free < iso.stat().st_size + 256 * 1024 * 1024:
        raise DDRXError("Not enough free space for a copy of the original ISO plus growth")
    game = DDRXGame(iso)
    jobs = normalize_jobs(payload, game)
    if not charts_only:
        sn2.need_ffmpeg()
    print(f"DDR X USA: {len(game.slot_map)} stock slots; {len(jobs)} replacements queued")
    chartpack = game.read(CSQ)
    chart_items = split_pack(chartpack)
    artpack, art_items = None, None
    changed_chart, changed_art = set(), set()
    warnings = []
    audio_changes = []
    keeps = []
    try:
        for number, job in enumerate(jobs, 1):
            code = job["slot"]
            index = game.slot_map[code]["index"]
            print(f"[{number}/{len(jobs)}] {code} index {index}: {job['song'].name}")
            simfile = sn2.open_song(job["song"], keeps)
            song = sm2ddr.parse_simfile(simfile)
            mines = sum(c.notes.upper().count("M") for c in song.charts
                        if c.style in ("dance-single", "dance-double"))
            if mines and shock_mode == "ignore":
                print(f"WARNING: {mines} mine panels omitted (Shock Arrows disabled).")
            messages = []
            chart, _, shift = sn2.ps2_chart(song, messages, shock_mode=shock_mode)
            for message in messages:
                print("WARNING:", message)
            enc = sn2.lz_compress(chart)
            if sn2.lz_decompress(enc) != chart:
                raise DDRXError(f"Chart failed compression roundtrip for {code}")
            chart_items[index] = enc
            changed_chart.add(index)
            if not charts_only:
                if art_items is None:
                    artpack = game.read(ART)
                    art_items = split_pack(artpack)
                original_art = art_items[index]
                candidate_art = build_art_entry(original_art, song, simfile,
                                               warnings, slot=code,
                                               replace_banner=job["banner"])
                if candidate_art != original_art:
                    art_items[index] = candidate_art
                    changed_art.add(index)
            if update_bpm:
                bpm_change = patch_bpm(game.elf, game.slot_map[code]["record_offset"], song)
                print(f"Updated BPM range for {code}: {bpm_change['old']} -> {bpm_change['new']}")
            if update_ratings:
                result = patch_ratings(game.elf, game.slot_map[code]["record_offset"], song)
                for message in result["warnings"]:
                    warnings.append(f"WARNING: {code}: {message}")
                print(f"Updated X-scale difficulty meters for {code}: {result['levels']}")
                # Chart-selection availability is independent of these meters.
                old = result["before"]
                new = result["after"]
                if any(bool(old[k - 36]) != bool(new[k - 36]) for k in RATING_OFFSETS.values()):
                    msg = (f"WARNING: {code} chart availability changed in simfile; "
                           "difficulty values updated; verify DDR X selection behavior "
                           "for Challenge and absent charts")
                    print(msg)
                    warnings.append(msg)
            if not charts_only:
                audiofile = sm2ddr.find_file(simfile.parent, song.music,
                                               ["*.ogg", "*.mp3", "*.wav", "*.flac"])
                if not audiofile:
                    raise DDRXError(f"No music file located for {song.title} in {simfile.parent}")
                full_name, sel_name = f"MUSIC/{code}.vig", f"SEL/{code}_s.vig"
                print(f"Encoding audio for {code} ...")
                pcm = sm2ddr.decode_audio(audiofile, shift)
                full = sn2.pad(sn2.vig_encode(pcm, game.read(full_name)[:sn2.SECTOR]))
                del pcm
                start = song.sample_start if song.sample_start >= 0 else 30.0
                preview = sm2ddr.decode_audio(audiofile, 0, start, 15.0, fade=True)
                sel = sn2.pad(sn2.vig_encode(preview[:15 * 44100], game.read(sel_name)[:sn2.SECTOR]))
                del preview
                audio_changes += [(full_name, full), (sel_name, sel)]
        patches = [(CSQ, sn2.pad(repack(chartpack, chart_items, changed_chart,
                                         align=1, images=False)))]
        if changed_art:
            patches.append((ART, sn2.pad(repack(artpack, art_items, changed_art,
                                              align=4, images=True))))
        # All input parsing, encoding and archive assembly completes before copying.
        print("Copying original ISO; original input is never modified ...")
        shutil.copyfile(iso, output)
        try:
            with output.open("r+b") as f:
                placer = sn2.Placer(game, f)
                for name, content in audio_changes + patches:
                    print(f"Patching {name} ({len(content):,} bytes)")
                    placer.put(name, content, print)
                elf_lba, elf_size = game.files[game.elf_name.upper()]
                if len(game.elf) != elf_size:
                    raise DDRXError("Game executable length changed")
                f.seek(elf_lba * sn2.SECTOR)
                f.write(game.elf)
                if placer.finish():
                    print("INFO: ISO was extended for relocated resources")
        except BaseException:
            output.unlink(missing_ok=True)
            raise
    finally:
        for k in keeps:
            k.cleanup()
    print(f"DONE: {output}")
    print("WARNING: Unlocks and background movies remain stock; Shock Arrows are experimental.")
    print("WARNING: PCSX2 boot compatibility has not yet been verified.")
    return warnings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("slots", help="List every selectable slot and correct chart index")
    s.add_argument("iso", type=Path)
    s.add_argument("--json", type=Path, help="Save JSON slot list")
    r = sub.add_parser("replace", help="Replace a StepMania song in one stock slot")
    r.add_argument("iso", type=Path)
    r.add_argument("song", help="Song ZIP, .sm/.ssc, or folder")
    r.add_argument("--slot", required=True, help="Target song code from slots command")
    r.add_argument("--out", required=True, type=Path)
    r.add_argument("--banner", action="store_true")
    r.add_argument("--charts-only", action="store_true")
    r.add_argument("--keep-ratings", action="store_true", help="Keep stock difficulty metadata")
    r.add_argument("--keep-bpm", action="store_true", help="Keep stock BPM display")
    r.add_argument("--shock", choices=("ignore", "all", "any"), default="ignore")
    b = sub.add_parser("batch", help="Replace several slots with one ISO rebuild")
    b.add_argument("iso", type=Path)
    b.add_argument("jobs", type=Path, help="JSON list of {slot, song, banner?} objects")
    b.add_argument("--out", required=True, type=Path)
    b.add_argument("--charts-only", action="store_true")
    b.add_argument("--keep-ratings", action="store_true", help="Keep stock difficulty metadata")
    b.add_argument("--keep-bpm", action="store_true", help="Keep stock BPM display")
    b.add_argument("--shock", choices=("ignore", "all", "any"), default="ignore")
    try:
        args = parser.parse_args(argv)
        if args.cmd == "slots":
            game = DDRXGame(args.iso)
            rows = [{"slot": code, "index": rec["index"],
                     "title": game.title_map.get(code, code)}
                    for code, rec in sorted(game.slot_map.items(), key=lambda x: x[1]["index"])]
            for r in rows:
                print(f"{r['index']:>2}  {r['slot']:<5}  {r['title']}")
            if args.json:
                args.json.write_text(json.dumps(rows, indent=2) + "\n", encoding="utf-8")
        elif args.cmd == "replace":
            make_iso(args.iso, args.out, [{"slot": args.slot, "song": args.song,
                                          "banner": args.banner}], charts_only=args.charts_only,
                     update_ratings=not args.keep_ratings,
                     update_bpm=not args.keep_bpm, shock_mode=args.shock)
        else:
            jobs = json.loads(args.jobs.read_text(encoding="utf-8"))
            make_iso(args.iso, args.out, jobs, charts_only=args.charts_only,
                     update_ratings=not args.keep_ratings,
                     update_bpm=not args.keep_bpm, shock_mode=args.shock)
    except (DDRXError, sn2.SN2Error, sm2ddr.ConvertError, OSError, ValueError,
            struct.error, IndexError, KeyError) as e:
        print("ERROR:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
