"""One-off: turn the raw character art in mascot/raw/ into state sprites.

The raw art is a full-body character on a flat grey studio backdrop, letterboxed
with black bars into a 512x512 square. The mascot window wants a transparent PNG
cropped to her outline. This:

  - flood-fills the black letterbox bars away from the corners (they stop at the
    grey backdrop, so her black clothing is never touched)
  - removes the grey backdrop everywhere -- it is a single flat colour nothing on
    the character shares
  - erodes + feathers the cutout edge by a pixel to kill the grey/black halo
  - crops to her bounding box with a little padding
  - writes idle/listening/thinking/speaking.png (and dance.png) into mascot/

Re-run whenever you replace the files in raw/. Needs Pillow + numpy, both already
in requirements.txt.

    python LIA\\mascot\\prepare_raw.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

RAW = Path(__file__).parent / "raw"
OUT = Path(__file__).parent

# raw/<n>.png -> <state>.png, matching the poses provided
MAPPING = {"1": "idle", "2": "listening", "3": "thinking", "4": "speaking"}
# `dance` has no pose of its own -- the sprite bobs in code. Point it at the most
# dynamic still so it doesn't look identical to idle.
DANCE_FROM = "4"

SENT = (255, 0, 255)       # sentinel colour painted where the background is
BLACK_THRESH = 26          # tolerance for the letterbox flood (seed is pure black)
GREY_THRESH = 16           # tolerance for the backdrop flood (seed is ~209 grey)
GREY_SAT_MAX = 14          # a border pixel this neutral and mid-bright is backdrop
GREY_VALUE = (185, 230)
PAD = 10


def _is_sent(arr: np.ndarray, x: int, y: int) -> bool:
    return bool(arr[y, x, 0] == 255 and arr[y, x, 1] == 0 and arr[y, x, 2] == 255)


def _cut(path: Path) -> Image.Image:
    src = Image.open(path).convert("RGB")
    rgb0 = np.array(src).astype(int)
    h, w = rgb0.shape[:2]
    work = src.copy()

    # 1. letterbox bars -- flood from the corners/edges that really are black.
    #    Stops dead at the grey backdrop, so her black clothing is never in reach.
    for sx, sy in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
                   (0, h // 2), (w - 1, h // 2), (w // 2, 0), (w // 2, h - 1)]:
        if max(rgb0[sy, sx]) < 40:
            ImageDraw.floodfill(work, (sx, sy), SENT, thresh=BLACK_THRESH)

    # 2. grey backdrop -- flood inward from every backdrop pixel on the image
    #    border. Region-growing (not a global colour test) is the point: it
    #    clears the studio grey around her and stops at her outline, so a shaded
    #    white blouse or petticoat *inside* the silhouette is left alone.
    for x in range(0, w, 3):
        for y in (0, h - 1):
            px = rgb0[y, x]
            if (max(px) - min(px) < GREY_SAT_MAX
                    and GREY_VALUE[0] <= max(px) <= GREY_VALUE[1]
                    and not _is_sent(np.asarray(work), x, y)):
                ImageDraw.floodfill(work, (x, y), SENT, thresh=GREY_THRESH)
    for y in range(0, h, 3):
        for x in (0, w - 1):
            px = rgb0[y, x]
            if (max(px) - min(px) < GREY_SAT_MAX
                    and GREY_VALUE[0] <= max(px) <= GREY_VALUE[1]
                    and not _is_sent(np.asarray(work), x, y)):
                ImageDraw.floodfill(work, (x, y), SENT, thresh=GREY_THRESH)

    fm = np.array(work)
    bg = (fm[..., 0] == 255) & (fm[..., 1] == 0) & (fm[..., 2] == 255)

    # Hard edge, no feather. The mascot window is a chroma key: a partly
    # transparent edge pixel gets composited against magenta and shows as a pink
    # halo on the desktop. Erode 2px to eat the raw art's own grey anti-aliasing,
    # then a crisp cut -- jaggies scaled down beat a glow.
    alpha = np.where(bg, 0, 255).astype("uint8")
    a = Image.fromarray(alpha, "L").filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MinFilter(3))
    alpha = np.where(np.array(a) >= 200, 255, 0).astype("uint8")

    # Drop the artist's sparkle marks and any flood-missed speckle. An opening
    # severs the thin bridges that attach a sparkle to her hand or hem; the
    # largest surviving blob is her; dilate it back and keep only original
    # pixels inside it, so her outline is unchanged but the sparkles are gone.
    from scipy import ndimage
    solid = alpha > 0
    opened = ndimage.binary_opening(solid, np.ones((3, 3)), iterations=3)
    lab, n = ndimage.label(opened)
    if n >= 1:
        biggest = lab == (1 + int(np.argmax(ndimage.sum(opened, lab, range(1, n + 1)))))
        body = ndimage.binary_dilation(biggest, np.ones((3, 3)), iterations=3)
        alpha = np.where(solid & body, 255, 0).astype("uint8")

    # One sparkle sits right against a boot, so it rides through the opening as
    # part of her. Kill small bright blobs down in the hem/boot band, where the
    # only bright thing that belongs is nothing.
    h = alpha.shape[0]
    bright = (alpha > 0) & (np.array(src).min(-1) > 170)
    bright[: int(h * 0.80)] = False
    blob, m = ndimage.label(bright)
    for i in range(1, m + 1):
        spot = blob == i
        if spot.sum() < 400:
            alpha[spot] = 0

    out = np.dstack([np.array(src), alpha]).astype("uint8")
    out = Image.fromarray(out, "RGBA")
    bbox = out.getbbox()
    if bbox:
        l, t, r, b = bbox
        out = out.crop((max(0, l - PAD), max(0, t - PAD),
                        min(w, r + PAD), min(h, b + PAD)))
    return out


def main() -> None:
    if not RAW.is_dir():
        raise SystemExit(f"no raw art at {RAW}")
    for stem, state in MAPPING.items():
        src = RAW / f"{stem}.png"
        if not src.exists():
            print(f"[skip] {src.name} missing")
            continue
        img = _cut(src)
        img.save(OUT / f"{state}.png")
        print(f"[ok]   {src.name} -> {state}.png  {img.size}")
    if DANCE_FROM and (RAW / f"{DANCE_FROM}.png").exists():
        _cut(RAW / f"{DANCE_FROM}.png").save(OUT / "dance.png")
        print(f"[ok]   {DANCE_FROM}.png -> dance.png")


if __name__ == "__main__":
    main()
