# Lia's 3D avatar

A floating, always-on-top **VRM character** — the format VTuber apps use — that
shows what Lia is doing: idle, listening, thinking, speaking. Rendered locally
with three.js + `@pixiv/three-vrm` (vendored in `vendor/`, MIT, no network
needed) inside a transparent pywebview/WebView2 window.

## Give her a model

Drop **any `.vrm` file into this folder** and restart her. The first one found
is used. VRM 0.x and 1.0 both work; a full-body model reads best. Free,
permissive models: [VRoid Hub](https://hub.vroid.com/) (check each model's
license) or [Booth](https://booth.pm/).

With no `.vrm` here she runs tray-only and prints one hint pointing here.

## What she does

| state | motion |
|---|---|
| idle | breathing, slow gaze wander, random blinks |
| listening | attentive head tilt, occasional glance at you |
| thinking | gaze up-left, tilted head, eyes mostly closed |
| speaking | mouth follows the **actual loudness** of Piper's audio + subtle bob |

- **Drag** anywhere to move her (position is remembered in `vrm_pos.json`).
- **Left-click** toggles listening.
- **Right-click** opens the same menu as the tray icon.

Preview the states without running her:

```
python LIA\vrm.py
```

(right-click to step through the states; the mouth moves on its own when she
is "speaking")

## Config knobs (config.py)

| constant | what it does |
|---|---|
| `VRM_ENABLED` | `False` runs tray-only even with a model present |
| `VRM_DIR` | where the `.vrm` files live (this folder) |
| `VRM_SIZE` | window size in pixels (420 default) |
| `VRM_POS_FILE` | where the dragged position is remembered |

## Notes & limits

- **Click-through**: a transparent WebView2 window still receives clicks on
  its transparent pixels, so the rectangle in front of her is hers. She is
  small; the desktop around her is not.
- **Renderer**: needs a WebGL-capable WebView2 (standard on Windows 10/11).
  On a machine with no GPU, WebView2 falls back to software rendering — if she
  feels heavy, lower `VRM_SIZE` or use a lighter model.
- **vendored libraries** (`vendor/`): three.js r167.1 and `@pixiv/three-vrm`
  3.5.5, both MIT-licensed; their license files sit beside them. Update by
  replacing the files — the page imports exactly those three paths.
- The viewer is served from a loopback-only HTTP server bound to an ephemeral
  port for the lifetime of the app; it is not reachable from other machines.
