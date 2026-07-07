#!/usr/bin/env python3
import argparse
import binascii
import collections
import os
import re
import shutil
import sqlite3
import struct
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zlib
from pathlib import Path


PNG_SIG = b"\x89PNG\r\n\x1a\n"
EXPECTED_DRAFT1_CRC32 = 0xA5F66B45
EXPECTED_DRAFT1_SIZE = 787840
HISTORY_REL = (
    "Users/verso/AppData/Local/Microsoft/Edge/User Data/Default/History"
)
DROPBOX_RE = re.compile(rb"https://www\.dropbox\.com/scl/fi/[^\s\"'<>\\]+")
EWF_SECTION_HEADER_SIZE = 76
EWF_SIGNATURE = b"EVF\t\r\n\xff\x00"


class SolveError(RuntimeError):
    pass


def log(msg: str) -> None:
    print(f"[+] {msg}")


def recover_draft1(zip_path: Path, out_dir: Path) -> Path:
    blob = zip_path.read_bytes()
    header = blob.find(b"PK\x03\x04")
    if header < 0:
        raise SolveError(f"local ZIP header not found in {zip_path}")

    method = struct.unpack_from("<H", blob, header + 8)[0]
    if method != 8:
        raise SolveError(f"unexpected ZIP compression method: {method}")

    name_len = struct.unpack_from("<H", blob, header + 26)[0]
    extra_len = struct.unpack_from("<H", blob, header + 28)[0]
    name_start = header + 30
    name = blob[name_start : name_start + name_len].decode("utf-8")
    data_start = name_start + name_len + extra_len

    inflater = zlib.decompressobj(-15)
    recovered = inflater.decompress(blob[data_start:]) + inflater.flush()
    if not inflater.eof:
        raise SolveError("raw DEFLATE stream did not terminate cleanly")

    crc = binascii.crc32(recovered) & 0xFFFFFFFF
    if len(recovered) != EXPECTED_DRAFT1_SIZE:
        raise SolveError(f"draft 1 size mismatch: {len(recovered)}")
    if crc != EXPECTED_DRAFT1_CRC32:
        raise SolveError(f"draft 1 CRC mismatch: {crc:08x}")
    if not recovered.startswith(PNG_SIG):
        raise SolveError("draft 1 is not a PNG")

    out_path = out_dir / Path(name).name
    out_path.write_bytes(recovered)
    log(f"recovered draft 1: {out_path}")
    return out_path


def normalize_dropbox_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    query = [(k, v) for k, v in query if k != "dl"]
    query.append(("dl", "1"))
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(query), "")
    )


def extract_urls_from_history(history_db: Path) -> list[str]:
    con = sqlite3.connect(f"file:{history_db}?mode=ro", uri=True)
    try:
        rows = con.execute(
            "select url from urls where url like '%dropbox.com/scl/fi/%'"
        ).fetchall()
    finally:
        con.close()

    urls: list[str] = []
    seen: set[str] = set()
    for (url,) in rows:
        cleaned = str(url).strip()
        if cleaned not in seen:
            seen.add(cleaned)
            urls.append(cleaned)
    if len(urls) < 3:
        raise SolveError(f"expected at least 3 Dropbox URLs, found {len(urls)}")
    log(f"found {len(urls)} Dropbox URL(s) in Edge History")
    return urls


def extract_urls_by_strings(image_path: Path) -> list[str]:
    # Fallback for environments without libewf/tsk tooling. It is slower and
    # less forensically pure, but useful when the SQLite page is unallocated.
    seen: set[str] = set()
    urls: list[str] = []
    carry = b""
    with image_path.open("rb") as f:
        while True:
            chunk = f.read(16 * 1024 * 1024)
            if not chunk:
                break
            buf = carry + chunk
            for match in DROPBOX_RE.finditer(buf):
                url = match.group(0).decode("utf-8", "ignore")
                url = url.rstrip(").,;]")
                if url not in seen:
                    seen.add(url)
                    urls.append(url)
            carry = buf[-4096:]
    if len(urls) < 3:
        raise SolveError(f"string scan found only {len(urls)} Dropbox URL(s)")
    log(f"found {len(urls)} Dropbox URL(s) by string scan")
    return urls


class EwfImage:
    """Small EWF/E01 reader for this challenge's single-segment EWF v1 image."""

    def __init__(self, path: Path):
        self.path = path
        self._fh = path.open("rb")
        self.chunk_size = 32 * 1024
        self.media_size = 0
        self._chunks: list[tuple[int, int, bool]] = []
        self._cache: collections.OrderedDict[int, bytes] = collections.OrderedDict()
        self._parse()

    def close(self) -> None:
        self._fh.close()

    def _read_section_header(self, offset: int) -> tuple[bytes, int, int]:
        self._fh.seek(offset)
        header = self._fh.read(EWF_SECTION_HEADER_SIZE)
        if len(header) != EWF_SECTION_HEADER_SIZE:
            raise SolveError(f"short EWF section header at {offset}")
        section_type = header[:16].rstrip(b"\0")
        next_offset, size = struct.unpack_from("<QQ", header, 16)
        return section_type, next_offset, size

    def _parse(self) -> None:
        self._fh.seek(0)
        if self._fh.read(len(EWF_SIGNATURE)) != EWF_SIGNATURE:
            raise SolveError(f"{self.path} is not an EWF/E01 image")

        section_offset = len(EWF_SIGNATURE) + 5
        pending_sectors: tuple[int, int] | None = None
        sector_tables: list[tuple[int, int, int, int]] = []

        while section_offset:
            section_type, next_offset, size = self._read_section_header(section_offset)

            if section_type == b"disk":
                self._fh.seek(section_offset + EWF_SECTION_HEADER_SIZE)
                disk = self._fh.read(24)
                if len(disk) < 24:
                    raise SolveError("short EWF disk section")
                chunk_count = struct.unpack_from("<I", disk, 4)[0]
                sectors_per_chunk = struct.unpack_from("<I", disk, 8)[0]
                bytes_per_sector = struct.unpack_from("<I", disk, 12)[0]
                sector_count = struct.unpack_from("<I", disk, 16)[0]
                self.chunk_size = sectors_per_chunk * bytes_per_sector
                self.media_size = sector_count * bytes_per_sector
                if chunk_count == 0 or self.chunk_size == 0:
                    raise SolveError("invalid EWF disk geometry")
            elif section_type == b"sectors":
                pending_sectors = (section_offset, next_offset)
            elif section_type == b"table" and pending_sectors is not None:
                sector_start, sector_end = pending_sectors
                sector_tables.append((sector_start, sector_end, section_offset, size))
                pending_sectors = None

            if next_offset == 0 or next_offset == section_offset:
                break
            section_offset = next_offset

        if not sector_tables:
            raise SolveError("EWF image has no sector tables")

        for sector_start, sector_end, table_offset, table_size in sector_tables:
            self._fh.seek(table_offset + EWF_SECTION_HEADER_SIZE)
            body = self._fh.read(table_size - EWF_SECTION_HEADER_SIZE)
            if len(body) < 28:
                raise SolveError(f"short EWF table at {table_offset}")
            count = struct.unpack_from("<I", body, 0)[0]
            if len(body) < 24 + count * 4:
                raise SolveError(f"truncated EWF chunk table at {table_offset}")

            raw_offsets = [
                struct.unpack_from("<I", body, 24 + i * 4)[0] for i in range(count)
            ]
            masked_offsets = [raw & 0x7FFFFFFF for raw in raw_offsets]
            data_start = sector_start + EWF_SECTION_HEADER_SIZE

            # Early EWF tables in this image use absolute file offsets. Once
            # the table wraps near the 2 GiB boundary, offsets become relative
            # to the containing sectors section.
            base = 0 if masked_offsets and masked_offsets[0] >= data_start else data_start

            for idx, raw in enumerate(raw_offsets):
                chunk_start = base + (raw & 0x7FFFFFFF)
                if idx + 1 < count:
                    chunk_end = base + (raw_offsets[idx + 1] & 0x7FFFFFFF)
                else:
                    chunk_end = sector_end
                if chunk_end < chunk_start:
                    raise SolveError("EWF chunk offsets are not monotonic")
                self._chunks.append((chunk_start, chunk_end - chunk_start, bool(raw & 0x80000000)))

        if not self._chunks:
            raise SolveError("EWF image has no chunks")

    def _read_chunk(self, chunk_index: int) -> bytes:
        cached = self._cache.pop(chunk_index, None)
        if cached is not None:
            self._cache[chunk_index] = cached
            return cached

        try:
            chunk_start, chunk_size, compressed = self._chunks[chunk_index]
        except IndexError as exc:
            raise SolveError(f"EWF read past image chunk {chunk_index}") from exc

        self._fh.seek(chunk_start)
        data = self._fh.read(chunk_size)
        chunk = None
        if compressed:
            try:
                chunk = zlib.decompress(data)
            except zlib.error:
                chunk = None
        if chunk is None:
            if len(data) == self.chunk_size:
                chunk = data
            else:
                chunk = zlib.decompress(data)
        if len(chunk) < self.chunk_size:
            chunk += b"\0" * (self.chunk_size - len(chunk))

        self._cache[chunk_index] = chunk
        if len(self._cache) > 128:
            self._cache.popitem(last=False)
        return chunk

    def read(self, offset: int, size: int) -> bytes:
        if offset < 0 or size < 0:
            raise SolveError("negative EWF read")
        out = bytearray()
        while size:
            chunk_index = offset // self.chunk_size
            chunk_offset = offset % self.chunk_size
            take = min(size, self.chunk_size - chunk_offset)
            out.extend(self._read_chunk(chunk_index)[chunk_offset : chunk_offset + take])
            offset += take
            size -= take
        return bytes(out)


def ntfs_apply_fixup(record: bytes, bytes_per_sector: int) -> bytes:
    fixed = bytearray(record)
    usa_offset, usa_count = struct.unpack_from("<HH", fixed, 4)
    usa = fixed[usa_offset : usa_offset + usa_count * 2]
    if len(usa) != usa_count * 2:
        raise SolveError("invalid NTFS update sequence array")
    sequence = usa[:2]
    for idx in range(1, usa_count):
        sector_tail = idx * bytes_per_sector - 2
        if sector_tail + 2 > len(fixed):
            raise SolveError("NTFS fixup extends past record")
        if fixed[sector_tail : sector_tail + 2] != sequence:
            raise SolveError("NTFS record fixup sequence mismatch")
        fixed[sector_tail : sector_tail + 2] = usa[idx * 2 : idx * 2 + 2]
    return bytes(fixed)


def ntfs_attributes(record: bytes):
    offset = struct.unpack_from("<H", record, 20)[0]
    while offset + 8 <= len(record):
        attr_type = struct.unpack_from("<I", record, offset)[0]
        if attr_type == 0xFFFFFFFF:
            break
        attr_len = struct.unpack_from("<I", record, offset + 4)[0]
        if attr_len < 16 or offset + attr_len > len(record):
            break
        yield attr_type, record[offset : offset + attr_len]
        offset += attr_len


def ntfs_parse_data_runs(runlist: bytes) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    offset = 0
    lcn = 0
    while offset < len(runlist) and runlist[offset] != 0:
        header = runlist[offset]
        offset += 1
        length_size = header & 0x0F
        offset_size = header >> 4
        cluster_count = int.from_bytes(runlist[offset : offset + length_size], "little")
        offset += length_size
        lcn_delta = int.from_bytes(
            runlist[offset : offset + offset_size], "little", signed=True
        )
        offset += offset_size
        lcn += lcn_delta
        runs.append((lcn, cluster_count))
    return runs


def ntfs_file_names(record: bytes) -> list[tuple[int, str, int]]:
    names: list[tuple[int, str, int]] = []
    for attr_type, attr in ntfs_attributes(record):
        if attr_type != 0x30 or attr[8] != 0:
            continue
        value_len = struct.unpack_from("<I", attr, 16)[0]
        value_offset = struct.unpack_from("<H", attr, 20)[0]
        value = attr[value_offset : value_offset + value_len]
        if len(value) < 66:
            continue
        parent = struct.unpack_from("<Q", value, 0)[0] & 0xFFFFFFFFFFFF
        name_len = value[64]
        namespace = value[65]
        name = value[66 : 66 + name_len * 2].decode("utf-16le", "ignore")
        names.append((parent, name, namespace))
    return names


class NtfsVolume:
    def __init__(self, image: EwfImage, partition_offset: int):
        self.image = image
        self.partition_offset = partition_offset
        boot = image.read(partition_offset, 512)
        if b"NTFS" not in boot[3:11]:
            raise SolveError("partition is not NTFS")
        self.bytes_per_sector = struct.unpack_from("<H", boot, 11)[0]
        sectors_per_cluster = boot[13]
        self.cluster_size = self.bytes_per_sector * sectors_per_cluster
        mft_lcn = struct.unpack_from("<Q", boot, 48)[0]
        clusters_per_record = struct.unpack_from("b", boot, 64)[0]
        self.record_size = (
            self.cluster_size * clusters_per_record
            if clusters_per_record > 0
            else 1 << (-clusters_per_record)
        )
        self.mft_offset = partition_offset + mft_lcn * self.cluster_size
        mft_record = self.read_mft_record_by_offset(self.mft_offset)
        self.mft_runs, self.mft_size = self._mft_data_runs(mft_record)

    def read_mft_record_by_offset(self, offset: int) -> bytes:
        record = self.image.read(offset, self.record_size)
        if not record.startswith(b"FILE"):
            raise SolveError("invalid NTFS file record")
        return ntfs_apply_fixup(record, self.bytes_per_sector)

    def _mft_data_runs(self, mft_record: bytes) -> tuple[list[tuple[int, int]], int]:
        for attr_type, attr in ntfs_attributes(mft_record):
            if attr_type == 0x80 and attr[8] != 0:
                run_offset = struct.unpack_from("<H", attr, 32)[0]
                real_size = struct.unpack_from("<Q", attr, 48)[0]
                return ntfs_parse_data_runs(attr[run_offset:]), real_size
        raise SolveError("$MFT has no non-resident DATA attribute")

    def read_mft_record(self, record_number: int) -> bytes:
        logical_offset = record_number * self.record_size
        for lcn, cluster_count in self.mft_runs:
            run_size = cluster_count * self.cluster_size
            if logical_offset < run_size:
                return self.read_mft_record_by_offset(
                    self.partition_offset
                    + lcn * self.cluster_size
                    + logical_offset
                )
            logical_offset -= run_size
        raise SolveError(f"MFT record {record_number} is outside $MFT")

    def read_data_attribute(self, attr: bytes) -> bytes:
        if attr[8] == 0:
            value_len = struct.unpack_from("<I", attr, 16)[0]
            value_offset = struct.unpack_from("<H", attr, 20)[0]
            return attr[value_offset : value_offset + value_len]

        run_offset = struct.unpack_from("<H", attr, 32)[0]
        real_size = struct.unpack_from("<Q", attr, 48)[0]
        out = bytearray()
        for lcn, cluster_count in ntfs_parse_data_runs(attr[run_offset:]):
            run_size = cluster_count * self.cluster_size
            if lcn == 0:
                data = b"\0" * run_size
            else:
                data = self.image.read(
                    self.partition_offset + lcn * self.cluster_size, run_size
                )
            need = real_size - len(out)
            out.extend(data[:need])
            if len(out) >= real_size:
                break
        return bytes(out)

    def iter_mft_records(self):
        max_records = self.mft_size // self.record_size
        record_number = 0
        for lcn, cluster_count in self.mft_runs:
            run_records = (cluster_count * self.cluster_size) // self.record_size
            for idx in range(run_records):
                if record_number >= max_records:
                    return
                record = self.image.read(
                    self.partition_offset
                    + lcn * self.cluster_size
                    + idx * self.record_size,
                    self.record_size,
                )
                if record.startswith(b"FILE"):
                    try:
                        yield record_number, ntfs_apply_fixup(
                            record, self.bytes_per_sector
                        )
                    except SolveError:
                        pass
                record_number += 1


def find_ntfs_partition_offset(image: EwfImage) -> int:
    mbr = image.read(0, 512)
    for idx in range(4):
        entry = mbr[446 + idx * 16 : 446 + (idx + 1) * 16]
        part_type = entry[4]
        if part_type == 0x07:
            return struct.unpack_from("<I", entry, 8)[0] * 512

    if mbr[446 + 4] != 0xEE:
        raise SolveError("no NTFS MBR partition or GPT protective MBR found")

    gpt = image.read(512, 512)
    if gpt[:8] != b"EFI PART":
        raise SolveError("protective MBR found but GPT header is missing")
    entry_lba = struct.unpack_from("<Q", gpt, 72)[0]
    entry_count = struct.unpack_from("<I", gpt, 80)[0]
    entry_size = struct.unpack_from("<I", gpt, 84)[0]
    entries = image.read(entry_lba * 512, entry_count * entry_size)
    for idx in range(entry_count):
        entry = entries[idx * entry_size : (idx + 1) * entry_size]
        if entry[:16] == b"\0" * 16:
            continue
        first_lba = struct.unpack_from("<Q", entry, 32)[0]
        boot = image.read(first_lba * 512, 512)
        if b"NTFS" in boot[3:11]:
            return first_lba * 512
    raise SolveError("no NTFS partition found in GPT")


def extract_history_with_ewf_ntfs(e01_path: Path, out_dir: Path) -> Path:
    target_parts = [part.lower() for part in HISTORY_REL.split("/")]
    image = EwfImage(e01_path)
    try:
        volume = NtfsVolume(image, find_ntfs_partition_offset(image))
        entries: dict[int, list[tuple[int, str, int]]] = {}
        history_candidates: list[int] = []

        for record_number, record in volume.iter_mft_records():
            names = ntfs_file_names(record)
            if not names:
                continue
            entries[record_number] = names
            if any(name.lower() == "history" for _parent, name, _ns in names):
                history_candidates.append(record_number)

        def path_for(record_number: int) -> list[str]:
            parts: list[str] = []
            seen: set[int] = set()
            while record_number in entries and record_number not in seen:
                seen.add(record_number)
                names = entries[record_number]
                parent, name, _ns = next(
                    ((p, n, ns) for p, n, ns in names if ns != 2), names[0]
                )
                parts.append(name)
                record_number = parent
                if record_number == 5:
                    break
            return list(reversed(parts))

        target_record = None
        for candidate in history_candidates:
            if [part.lower() for part in path_for(candidate)] == target_parts:
                target_record = candidate
                break
        if target_record is None:
            raise SolveError("Edge History path was not found in NTFS")

        record = volume.read_mft_record(target_record)
        for attr_type, attr in ntfs_attributes(record):
            if attr_type == 0x80:
                data = volume.read_data_attribute(attr)
                if not data.startswith(b"SQLite format 3\0"):
                    continue
                out_path = out_dir / "History"
                out_path.write_bytes(data)
                log(f"extracted Edge History directly from E01: {out_path}")
                return out_path
        raise SolveError("Edge History record has no SQLite DATA attribute")
    finally:
        image.close()


def _walk_pytsk_directory(fs, directory, wanted_parts: list[str]):
    for entry in directory:
        name = entry.info.name.name
        if name in (b".", b".."):
            continue
        decoded = name.decode("utf-8", "ignore")
        if decoded.lower() != wanted_parts[0].lower():
            continue
        if len(wanted_parts) == 1:
            return entry
        sub = entry.as_directory()
        return _walk_pytsk_directory(fs, sub, wanted_parts[1:])
    return None


def extract_history_with_pytsk(e01_path: Path, out_dir: Path) -> Path:
    try:
        import pyewf  # type: ignore
        import pytsk3  # type: ignore
    except ImportError as exc:
        raise SolveError("pyewf and pytsk3 are not installed") from exc

    class EwfImgInfo(pytsk3.Img_Info):
        def __init__(self, filenames):
            self._ewf = pyewf.handle()
            self._ewf.open(filenames)
            super().__init__(url="", type=pytsk3.TSK_IMG_TYPE_EXTERNAL)

        def close(self):
            self._ewf.close()

        def read(self, offset, size):
            self._ewf.seek(offset)
            return self._ewf.read(size)

        def get_size(self):
            return self._ewf.get_media_size()

    filenames = pyewf.glob(str(e01_path))
    img = EwfImgInfo(filenames)
    try:
        offsets = [0]
        try:
            volume = pytsk3.Volume_Info(img)
            offsets = [
                part.start * 512
                for part in volume
                if b"NTFS" in bytes(part.desc).upper()
            ] or offsets
        except Exception:
            pass

        wanted = HISTORY_REL.split("/")
        for offset in offsets:
            try:
                fs = pytsk3.FS_Info(img, offset=offset)
                entry = _walk_pytsk_directory(fs, fs.open_dir(path="/"), wanted)
                if entry is None:
                    continue
                data = entry.read_random(0, entry.info.meta.size)
                out_path = out_dir / "History"
                out_path.write_bytes(data)
                log(f"extracted Edge History with pytsk3: {out_path}")
                return out_path
            except Exception:
                continue
    finally:
        img.close()
    raise SolveError("Edge History was not found in the E01 image")


def extract_history_with_sleuthkit(e01_path: Path, out_dir: Path) -> Path:
    for exe in ("mmls", "fls", "icat"):
        if shutil.which(exe) is None:
            raise SolveError("Sleuth Kit tools mmls/fls/icat are not on PATH")
    ewfmount = shutil.which("ewfmount")
    if ewfmount is None:
        raise SolveError("ewfmount is not on PATH")

    mount_dir = Path(tempfile.mkdtemp(prefix="our_drafts_ewf_"))
    try:
        subprocess.run([ewfmount, str(e01_path), str(mount_dir)], check=True)
        raw_image = mount_dir / "ewf1"
        mmls = subprocess.run(
            ["mmls", str(raw_image)],
            text=True,
            capture_output=True,
            check=True,
        )
        start_sector = None
        for line in mmls.stdout.splitlines():
            if "NTFS" not in line.upper():
                continue
            cols = line.split()
            for col in cols:
                if col.isdigit():
                    start_sector = int(col)
                    break
            if start_sector is not None:
                break
        if start_sector is None:
            raise SolveError("mmls did not report an NTFS partition")
        offset = str(start_sector * 512)

        inode = None
        current = "2"
        for part in HISTORY_REL.split("/"):
            fls = subprocess.run(
                ["fls", "-o", offset, str(raw_image), current],
                text=True,
                capture_output=True,
                check=True,
            )
            needle = part.lower()
            for line in fls.stdout.splitlines():
                if line.lower().rstrip().endswith(needle):
                    inode = line.split()[1].rstrip(":")
                    current = inode
                    break
            else:
                raise SolveError(f"Sleuth Kit could not find {part}")

        out_path = out_dir / "History"
        with out_path.open("wb") as out:
            subprocess.run(
                ["icat", "-o", offset, str(raw_image), current],
                stdout=out,
                check=True,
            )
        log(f"extracted Edge History with Sleuth Kit: {out_path}")
        return out_path
    finally:
        # Leave a clear best effort cleanup path for Linux/macOS challenge boxes.
        if shutil.which("fusermount"):
            subprocess.run(["fusermount", "-u", str(mount_dir)], check=False)


def get_history_db(args, out_dir: Path) -> Path | None:
    if args.history_db:
        return Path(args.history_db)
    if not args.e01:
        return None
    e01_path = Path(args.e01)

    for extractor in (
        extract_history_with_ewf_ntfs,
        extract_history_with_pytsk,
        extract_history_with_sleuthkit,
    ):
        try:
            return extractor(e01_path, out_dir)
        except SolveError as exc:
            log(f"{extractor.__name__} skipped: {exc}")
    return None


def download_dropbox_files(urls: list[str], out_dir: Path) -> dict[str, Path]:
    download_dir = out_dir / "downloads"
    download_dir.mkdir(exist_ok=True)
    downloaded: dict[str, Path] = {}
    for url in urls:
        direct = normalize_dropbox_url(url)
        filename = Path(urllib.parse.unquote(urllib.parse.urlsplit(url).path)).name
        if not filename:
            continue
        if filename in downloaded:
            continue
        out_path = download_dir / filename
        with urllib.request.urlopen(direct, timeout=120) as resp:
            out_path.write_bytes(resp.read())
        downloaded[filename] = out_path
        log(f"downloaded {filename}: {out_path}")
    return downloaded


def openstego_commands(args, stego_file: Path, extract_dir: Path) -> list[list[str]]:
    commands: list[list[str]] = []
    algorithms = ["randomlsb", ""]
    password = args.openstego_password

    if args.openstego_jar:
        jar = str(Path(args.openstego_jar))
        for alg in algorithms:
            cmd = ["java", "-jar", jar, "extract"]
            if alg:
                cmd += ["-a", alg]
            cmd += ["-sf", str(stego_file), "-xd", str(extract_dir), "-p", password]
            commands.append(cmd)

    env_jar = os.environ.get("OPENSTEGO_JAR")
    if env_jar:
        for alg in algorithms:
            cmd = ["java", "-jar", env_jar, "extract"]
            if alg:
                cmd += ["-a", alg]
            cmd += ["-sf", str(stego_file), "-xd", str(extract_dir), "-p", password]
            commands.append(cmd)

    openstego = shutil.which("openstego")
    if openstego:
        for alg in algorithms:
            cmd = [openstego, "extract"]
            if alg:
                cmd += ["-a", alg]
            cmd += ["-sf", str(stego_file), "-xd", str(extract_dir), "-p", password]
            commands.append(cmd)

    return commands


def extract_draft2_with_openstego(stego_file: Path, out_dir: Path, args) -> Path:
    extract_dir = out_dir / "openstego_extract"
    if extract_dir.exists():
        shutil.rmtree(extract_dir)
    extract_dir.mkdir(exist_ok=True)

    commands = openstego_commands(args, stego_file, extract_dir)
    if not commands:
        raise SolveError(
            "OpenStego not found. Pass --openstego-jar openstego.jar or set "
            "OPENSTEGO_JAR."
        )

    errors: list[str] = []
    before = {p.resolve() for p in extract_dir.rglob("*") if p.is_file()}
    for cmd in commands:
        proc = subprocess.run(cmd, text=True, capture_output=True)
        after = [p for p in extract_dir.rglob("*") if p.is_file()]
        new_files = [p for p in after if p.resolve() not in before]
        pngs = [p for p in new_files if p.read_bytes().startswith(PNG_SIG)]
        if proc.returncode == 0 and pngs:
            draft2 = out_dir / "a_life_to_paint.png"
            draft2.write_bytes(pngs[0].read_bytes())
            log(f"extracted draft 2 with OpenStego: {draft2}")
            return draft2
        errors.append(
            "$ "
            + " ".join(cmd)
            + "\n"
            + (proc.stdout or "")
            + (proc.stderr or "")
        )
    raise SolveError("OpenStego extraction failed:\n" + "\n".join(errors[-3:]))


def parse_png(path: Path):
    data = path.read_bytes()
    if not data.startswith(PNG_SIG):
        raise SolveError(f"{path} is not a PNG")
    off = len(PNG_SIG)
    ihdr = None
    idat = bytearray()
    while off + 8 <= len(data):
        length = struct.unpack(">I", data[off : off + 4])[0]
        typ = data[off + 4 : off + 8]
        body = data[off + 8 : off + 8 + length]
        off += 12 + length
        if typ == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif typ == b"IDAT":
            idat.extend(body)
        elif typ == b"IEND":
            break
    if ihdr is None:
        raise SolveError(f"{path} has no IHDR")
    return ihdr, zlib.decompress(bytes(idat))


def paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def bytes_per_pixel(color_type: int, bit_depth: int) -> int:
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color_type]
    return max(1, (channels * bit_depth + 7) // 8)


def png_to_rgb(path: Path) -> tuple[tuple[int, int], bytes]:
    ihdr, raw = parse_png(path)
    width, height, bit_depth, color_type, compression, filter_method, interlace = ihdr
    if (bit_depth, color_type, compression, filter_method, interlace) != (8, 2, 0, 0, 0):
        raise SolveError(f"{path} must be a non-interlaced 8-bit RGB PNG")

    bpp = bytes_per_pixel(color_type, bit_depth)
    stride = width * 3
    pos = 0
    prev = bytearray(stride)
    pixels = bytearray()
    for _y in range(height):
        filter_type = raw[pos]
        pos += 1
        scan = bytearray(raw[pos : pos + stride])
        pos += stride
        for i in range(stride):
            left = scan[i - bpp] if i >= bpp else 0
            up = prev[i]
            up_left = prev[i - bpp] if i >= bpp else 0
            if filter_type == 1:
                scan[i] = (scan[i] + left) & 0xFF
            elif filter_type == 2:
                scan[i] = (scan[i] + up) & 0xFF
            elif filter_type == 3:
                scan[i] = (scan[i] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                scan[i] = (scan[i] + paeth(left, up, up_left)) & 0xFF
            elif filter_type != 0:
                raise SolveError(f"unsupported PNG filter type {filter_type}")
        pixels.extend(scan)
        prev = scan
    return (width, height), bytes(pixels)


def write_rgb_png(path: Path, size: tuple[int, int], pixels: bytes) -> None:
    width, height = size
    stride = width * 3
    if len(pixels) != stride * height:
        raise SolveError("pixel buffer size does not match image dimensions")

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        start = y * stride
        raw.extend(pixels[start : start + stride])

    def chunk(typ: bytes, body: bytes) -> bytes:
        crc = binascii.crc32(typ + body) & 0xFFFFFFFF
        return struct.pack(">I", len(body)) + typ + body + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        PNG_SIG
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def xor_drafts(draft1: Path, draft2: Path, out_path: Path) -> Path:
    size1, rgb1 = png_to_rgb(draft1)
    size2, rgb2 = png_to_rgb(draft2)
    if size1 != size2 or len(rgb1) != len(rgb2):
        raise SolveError("draft PNG dimensions do not match")
    flag_rgb = bytes(a ^ b for a, b in zip(rgb1, rgb2))
    write_rgb_png(out_path, size1, flag_rgb)
    log(f"wrote final flag PNG: {out_path}")
    return out_path


def parse_args() -> argparse.Namespace:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(
        description="Solve Our Drafts Unite from the distributed challenge files."
    )
    parser.add_argument("--dist", type=Path, default=root / "dist")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "out")
    parser.add_argument("--history-db", type=Path, help="pre-extracted Edge History sqlite DB")
    parser.add_argument(
        "--e01",
        type=Path,
        default=root / "dist" / "seized_laptop_image" / "saved_c_image.E01",
        help="E01 image to inspect for Edge History",
    )
    parser.add_argument(
        "--openstego-jar",
        type=Path,
        default=Path(__file__).resolve().parent / "openstego.jar",
        help="path to openstego.jar",
    )
    parser.add_argument(
        "--stego-png",
        type=Path,
        help="already-downloaded OpenStego carrier PNG, usually a_life_to_paint.png",
    )
    parser.add_argument(
        "--openstego-password",
        default="",
        help="password for OpenStego extraction; this challenge uses an empty password",
    )
    parser.add_argument(
        "--draft2",
        type=Path,
        help="already-extracted second draft PNG; skips History/Dropbox/OpenStego",
    )
    parser.add_argument(
        "--string-scan-e01",
        action="store_true",
        help="scan the E01 bytes directly for Dropbox URLs if History extraction is unavailable",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    draft1_zip = args.dist / "draft_1_remains" / "broken_draft.zip"
    draft1 = recover_draft1(draft1_zip, args.out)

    if args.draft2:
        draft2 = args.draft2
    else:
        stego_png = args.stego_png
        if stego_png is None:
            history = get_history_db(args, args.out)
            if history is not None:
                urls = extract_urls_from_history(history)
            elif args.string_scan_e01 and args.e01:
                urls = extract_urls_by_strings(Path(args.e01))
            else:
                raise SolveError(
                    "could not get Edge History. Provide --history-db, install "
                    "pyewf/pytsk3 or Sleuth Kit+libewf, or use --string-scan-e01."
                )
            downloaded = download_dropbox_files(urls, args.out)
            stego_png = downloaded.get("a_life_to_paint.png")
            if stego_png is None:
                raise SolveError("a_life_to_paint.png was not among downloaded URLs")
        draft2 = extract_draft2_with_openstego(Path(stego_png), args.out, args)

    xor_drafts(draft1, Path(draft2), args.out / "flag.png")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SolveError as exc:
        print(f"[-] {exc}", file=sys.stderr)
        raise SystemExit(1)
