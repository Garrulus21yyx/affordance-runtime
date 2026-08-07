import struct
import zlib
from runpy import run_path


def _png_rgb(width: int, height: int, pixels: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    rows = b"".join(
        b"\x00" + pixels[row * width * 3 : (row + 1) * width * 3]
        for row in range(height)
    )
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def test_live_conflict_pixel_oracle_counts_rendered_red_and_green_without_dom_geometry() -> None:
    functions = run_path("scripts/run_m85_live_conflict.py")
    count = functions["_red_green_pixel_counts"]
    png = _png_rgb(
        4,
        1,
        bytes(
            (
                220,
                30,
                30,
                250,
                10,
                10,
                20,
                190,
                70,
                255,
                255,
                255,
            )
        ),
    )

    assert count(png) == (2, 1)
