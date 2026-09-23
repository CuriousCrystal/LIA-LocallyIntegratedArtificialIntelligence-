# Lia's desktop mascot

The little character that sits on your desktop and shows what she's doing.
Drop image files in this folder; she picks them up on the next start.

**One image is enough.** Any state with no art of its own uses `idle`, so a
single `idle.png` covers everything. With no art at all she draws a plain purple
cat face — the mascot still appears, it just won't be yours.

## The states

| file(s) | shown when |
|---|---|
| `idle.*` | nothing happening — also the fallback for any state below with no art |
| `listening.*` | the mic is on and she's waiting for you |
| `thinking.*` | she's working out a reply |
| `speaking.*` | she's talking |
| `greeting.*` | *optional* — plays **once** at startup, then drops to `idle` |

(The old `dance` state went with the music player.)

## File formats

For any state, the loader looks for, in order:

1. **Numbered frames** — `idle-1.png`, `idle-2.png`, `idle-3.png` … play as a
   loop at `MASCOT_FPS` (8/sec by default). Any count.
2. **A single still** — `idle.png`.
3. **An animated GIF** — `idle.gif` — its frames are unpacked automatically.

`.png`, `.gif` and `.webp` are accepted. PNG with transparency is best.
Whatever the source size, it's scaled to fit just inside `MASCOT_SIZE`
(300 px for the full-body art here), and centred in a square window.

## Raw studio art (`raw/`)

If your art is a full-body character on a flat backdrop (a commissioned
turnaround, an AI portrait), you don't have to cut it out by hand. Drop the
files in `raw/` as `1.png`–`4.png` (idle, listening, thinking, speaking) and run:

```
python LIA\mascot\prepare_raw.py
```

It flood-fills the backdrop and any letterbox bars to transparent, drops the
artist's sparkle marks, hard-edges the cutout so there's no chroma halo, crops
to her outline, and writes `idle/listening/thinking/speaking.png`. Re-run it
whenever you swap the files in `raw/`. Tune the colour thresholds at the top of
the script if your backdrop isn't grey.

## Transparency

The window punches out one exact colour — `MASCOT_CHROMA`, magenta `#ff00ff` by
default — so the desktop shows through wherever your art doesn't cover.

- **PNG alpha works**, but anti-aliased edges get composited against the chroma
  colour and can show a faint pink fringe.
- For crisp edges, flatten your sprite onto a solid `#ff00ff` background in your
  image editor before exporting.
- If magenta appears in your art, change `MASCOT_CHROMA` in
  [`config.py`](../config.py) to a colour it never uses.

## Settings ([`config.py`](../config.py))

| setting | |
|---|---|
| `MASCOT_ENABLED` | `False` turns the mascot off (tray icon stays) |
| `MASCOT_SIZE` | pixels across |
| `MASCOT_FPS` | animation speed for multi-frame states |
| `MASCOT_CHROMA` | the punched-out transparent colour |
| `MASCOT_POS_FILE` | where the dragged position is remembered |

## Using it

- **Drag** it anywhere — the position is remembered between runs.
- **Left-click** toggles listening on/off.
- **Right-click** opens a menu (listening, speaking, end conversation, open log,
  hide, quit) — the same controls as the tray icon, which is still there.

## Previewing your art

```
python LIA\mascot.py
```

Opens just the mascot and cycles through the states every couple of seconds
(right-click → *Next state* to step manually), so you can check the frames
without starting the whole app.
