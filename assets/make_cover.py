"""Generate the social preview card (1280x640, GitHub's og:image size).

Design notes
------------
The one idea that has to land while someone scrolls: **the wall looks solid,
then you walk through the door labelled "as documented".**

So the card is a two-panel ledger. Left panel: the 7 restrictions that DO hold,
all green. Right panel: what happens once you add `--imports pandas numpy`,
which is exactly what the README's own CLI example tells you to do. Three red.

The arrow between them is the point: it isn't a bypass, it's the documented path.

Same warm ink-on-paper palette as the other repos. No stock imagery, no
gradient mush, no corporate blue.

Run: python assets/make_cover.py
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

OUT = pathlib.Path(__file__).resolve().parent / "cover.png"

W, H = 1280, 640

INK = (26, 24, 22)
PAPER = (250, 248, 244)
MUTED = (138, 130, 120)
RULE = (223, 217, 208)
AMBER = (196, 132, 42)
WRONG = (176, 68, 52)
RIGHT = (86, 118, 92)

MONO = "C:/Windows/Fonts/consola.ttf"
MONO_B = "C:/Windows/Fonts/consolab.ttf"
SANS_B = "C:/Windows/Fonts/segoeuib.ttf"
SANS = "C:/Windows/Fonts/segoeui.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size)


def main() -> None:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)

    # Paper grain: near-invisible dots beat a flat fill.
    for y in range(0, H, 3):
        for x in range(0, W, 3):
            if (x * 7 + y * 13) % 97 == 0:
                d.point((x, y), fill=(244, 241, 236))

    # --- header ------------------------------------------------------------
    d.text((64, 42), "smolagents-audit", font=font(SANS_B, 48), fill=INK)
    d.text(
        (66, 104),
        "The README says it is not a sandbox. It does not say where the wall ends.",
        font=font(SANS, 22),
        fill=MUTED,
    )
    d.rectangle([64, 156, 132, 161], fill=AMBER)

    # --- two panels --------------------------------------------------------
    top = 200
    row_h = 42
    col_l = 64
    col_r = 700

    # panel headers
    d.text((col_l, top - 32), "NO EXTRA IMPORTS", font=font(SANS_B, 15), fill=MUTED)
    d.text((col_r, top - 32), "--imports pandas numpy", font=font(MONO_B, 15), fill=AMBER)

    left_rows = [
        ("import os", "blocked"),
        ("open()", "blocked"),
        ("__class__", "blocked"),
        ("__subclasses__()", "blocked"),
        ("__builtins__", "blocked"),
        ("while 1e7", "blocked"),
        ("getattr dunder", "blocked"),
    ]
    right_rows = [
        ("df.to_csv(path)", "wrote the file"),
        ("pd.read_csv(path)", "read the file"),
        ("os.system(cmd)", "ran the command"),
    ]

    mono = font(MONO, 19)
    tag = font(MONO_B, 17)

    y = top
    for name, verdict in left_rows:
        d.text((col_l, y), name, font=mono, fill=INK)
        d.text((col_l + 250, y + 1), verdict, font=tag, fill=RIGHT)
        y += row_h
    d.line([col_l, y + 6, col_l + 400, y + 6], fill=RULE, width=1)

    # vertical rule between panels
    d.line([628, top - 10, 628, top + row_h * 7 + 4], fill=RULE, width=1)
    y = top
    for name, verdict in right_rows:
        d.text((col_r, y), name, font=mono, fill=INK)
        d.text((col_r + 268, y + 1), verdict, font=tag, fill=WRONG)
        y += row_h
    d.line([col_r, y + 6, col_r + 430, y + 6], fill=RULE, width=1)

    # Why the right panel is so short: the deny-list is a name list, and library
    # file I/O was never on it. This note fills the gap with the actual reason.
    note = font(SANS, 17)
    d.text((col_r, y + 26), "The deny-list is 9 names:", font=note, fill=MUTED)
    d.text((col_r, y + 52), "builtins.eval  ·  builtins.exec  ·  os.system ...", font=font(MONO, 15), fill=MUTED)
    d.text((col_r, y + 82), "pandas I/O and subprocess were never on it.", font=note, fill=WRONG)

    # --- the punchline -----------------------------------------------------
    d.text(
        (64, 512),
        "7 of 7 restrictions hold.  Then you follow the documented CLI example.",
        font=font(SANS_B, 26),
        fill=INK,
    )
    d.text(
        (64, 550),
        "open() is banned. pandas.to_csv() is not. subprocess is not in the deny-list at all.",
        font=font(SANS, 18),
        fill=MUTED,
    )

    # --- footer ------------------------------------------------------------
    d.line([64, 588, W - 64, 588], fill=RULE, width=1)
    d.text(
        (64, 602),
        "31 cases  ·  side-effect based  ·  no API key  ·  runs in 20s",
        font=font(SANS_B, 17),
        fill=INK,
    )
    d.text(
        (W - 64 - 336, 604),
        "github.com/linmoxi33/smolagents-audit",
        font=font(MONO, 15),
        fill=MUTED,
    )

    img.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes, {W}x{H})")


if __name__ == "__main__":
    main()
