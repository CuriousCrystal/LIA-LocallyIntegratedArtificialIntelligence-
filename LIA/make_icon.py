"""Turn any image you drop into LIA/assets/ into the icon she actually uses.

    python LIA\\make_icon.py          # build assets/lia.ico from whatever is there

Drop an image into LIA/assets/ -- any PNG, JPG, WebP, GIF or BMP; a name
starting with "lia" or "tray_icon" wins if there are several -- and run that
command. She reads assets/lia.ico for the tray, and the avatar window carries
it too, so the taskbar and alt-tab show your image and not a generic one.

The original image file is never modified. What goes into the .ico:

  * the image made square -- padded to a centred square on transparency by
    default, or centre-cropped with --crop;
  * resized to every size Windows asks for (16, 32, 48, 64, 128, 256), which
    is what keeps it sharp on high-DPI screens: the tray renders 16px, the
    taskbar 32, the alt-tab switcher 256, and a single-size icon gets
    resampled by the shell instead.

Uses only Pillow, which the app already needs to draw her tray icon.
"""

import argparse
import sys
from pathlib import Path

# When packaged as an .exe, __file__ points inside a temporary unpack
# directory that's deleted on exit -- same gotcha as config.py's BASE_DIR,
# and the reason a packaged build reported "assets/lia.ico not built yet"
# even though assets/ was copied right next to the real exe.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
ICO_PATH = ASSETS_DIR / "lia.ico"

# Every size Windows renders at. 256 is the one alt-tab and Explorer previews
# use; skipping it is why custom icons look soft on high-DPI screens.
SIZES = [16, 32, 48, 64, 128, 256]

# In preference order: a file that is obviously meant as her icon beats an
# arbitrary image that happens to share the folder.
PREFERRED_PREFIXES = ("lia", "tray_icon")
IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp")


def find_source(assets_dir: Path) -> Path | None:
    """The image in assets_dir she should build from, or None."""
    if not assets_dir.is_dir():
        return None
    files = [p for p in sorted(assets_dir.iterdir())
             if p.is_file() and p.suffix.lower() in IMAGE_EXTS
             and not p.name.startswith(("_", "."))]
    for p in files:
        if p.stem.lower().startswith(PREFERRED_PREFIXES):
            return p
    return files[0] if files else None


def build(source: Path, ico_path: Path, crop: bool = False) -> str:
    """source image -> multi-size .ico. Returns a one-line report."""
    from PIL import Image

    img = Image.open(source)
    # An animated source's first frame, and anything with a mode that cannot
    # hold an alpha channel, both need normalising before squaring.
    img.seek(0)
    if img.mode in ("RGBA", "LA"):
        img = img.convert("RGBA")
    elif img.mode == "P":
        img = img.convert("RGBA")
    else:
        img = img.convert("RGBA") if "A" in img.mode else img.convert("RGB")

    side = max(img.size)
    square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    if crop:
        # Centre-crop: the largest square inside the image, which throws away
        # the edges. Right for photos; wrong for logos with text.
        w, h = img.size
        edge = min(w, h)
        left, top = (w - edge) // 2, (h - edge) // 2
        square.paste(img.crop((left, top, left + edge, top + edge)), (0, 0))
    else:
        # Centre-pad: nothing is lost, and the transparent margin becomes part
        # of the icon -- Windows scales sizes down, and a padded icon renders
        # slightly smaller in the tray, which is usually what you want.
        square.paste(img, ((side - img.width) // 2, (side - img.height) // 2))

    if square.width > 256:
        square = square.resize((256, 256), Image.LANCZOS)

    ico_path.parent.mkdir(parents=True, exist_ok=True)
    # One resample per size, LANCZOS, written into the .ico as its own frame.
    frames = [square.resize((s, s), Image.LANCZOS) for s in SIZES if s != 256]
    square.save(ico_path, format="ICO", append_images=frames,
                sizes=[(s, s) for s in SIZES])
    return (f"{ico_path.relative_to(BASE_DIR)} built from "
            f"{source.name} ({square.width}px source, {len(SIZES)} sizes)")


def ensure_icon(assets_dir: Path = None) -> str:
    """Build the .ico if the images in assets/ have moved on since it was.

    Returns a report line, empty when there is nothing to say -- an empty
    assets folder is the steady state for anyone who has not dropped an image
    in, and she draws her own cat face then, so it is not worth a log line at
    every startup. Safe to call at every boot: one stat call when current.
    """
    assets_dir = Path(assets_dir) if assets_dir else ASSETS_DIR
    ico_path = assets_dir / "lia.ico"
    source = find_source(assets_dir)
    if source is None:
        return ""
    if ico_path.is_file() and ico_path.stat().st_mtime >= source.stat().st_mtime:
        return ""
    return build(source, ico_path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--crop", action="store_true",
                    help="centre-crop a non-square image instead of padding it")
    ap.add_argument("--force", action="store_true",
                    help="rebuild even if the .ico is newer than the image")
    ap.add_argument("--dir", default=str(ASSETS_DIR),
                    help="folder to look in (default: LIA/assets)")
    args = ap.parse_args()

    assets_dir = Path(args.dir)
    source = find_source(assets_dir)
    if source is None:
        print(f"no image found in {assets_dir} -- drop a PNG/JPG/WebP/GIF/BMP "
              "there and run this again")
        return 1
    ico_path = assets_dir / "lia.ico"
    if not args.force and ico_path.is_file() \
            and ico_path.stat().st_mtime >= source.stat().st_mtime:
        print(f"{ico_path} is already newer than {source.name} "
              "(--force to rebuild)")
        return 0
    print(build(source, ico_path, crop=args.crop))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
