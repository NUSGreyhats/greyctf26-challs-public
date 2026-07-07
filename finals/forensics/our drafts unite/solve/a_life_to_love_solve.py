import binascii
import pathlib
import struct
import zlib


EXPECTED_CRC32 = 0xA5F66B45
EXPECTED_SIZE = 787840


def main() -> None:
    here = pathlib.Path(__file__).resolve().parent
    archive = here.parent / "dist" / "draft_1_remains" / "broken_draft.zip"
    blob = archive.read_bytes()

    header = blob.index(b"PK\x03\x04")
    method = struct.unpack_from("<H", blob, header + 8)[0]
    if method != 8:
        raise SystemExit(f"unexpected compression method: {method}")

    name_len = struct.unpack_from("<H", blob, header + 26)[0]
    extra_len = struct.unpack_from("<H", blob, header + 28)[0]
    name_start = header + 30
    name = blob[name_start:name_start + name_len].decode("utf-8")
    data_start = name_start + name_len + extra_len

    inflater = zlib.decompressobj(-15)
    recovered = inflater.decompress(blob[data_start:]) + inflater.flush()

    crc = binascii.crc32(recovered) & 0xFFFFFFFF
    if len(recovered) != EXPECTED_SIZE:
        raise SystemExit(f"wrong size: {len(recovered)}")
    if crc != EXPECTED_CRC32:
        raise SystemExit(f"wrong crc32: {crc:08x}")
    if not recovered.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SystemExit("recovered data is not a PNG")

    output = here / name
    output.write_bytes(recovered)
    print(f"recovered {output}")


if __name__ == "__main__":
    main()
