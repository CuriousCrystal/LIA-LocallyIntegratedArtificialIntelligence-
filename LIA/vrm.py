"""The desktop avatar: Lia as a 3D VRM character, fixed in your screen's
top-left corner.

Replaces the old 2D sprite mascot with the format VTuber apps use. A tiny
loopback HTTP server serves a single-page three.js viewer (three + three-vrm
are vendored in vrm/vendor/, so this renders with no network); pywebview shows
it in a frameless, transparent window. Not always-on-top: other windows can
cover her, on purpose. The model is the first *.vrm found in VRM_DIR.

It reflects one state -- idle / listening / thinking / speaking -- read every
~150ms from a callback the app hands in, exactly like mascot.py did. Blinking,
breathing, idle sway and gaze wander are all procedural; the mouth is driven
by the real loudness of Piper's audio (see voice.set_audio_level_sink). Drag
to move within a session (her position is not remembered between runs -- she
always starts top-left); left-click toggles listening; right-click opens the
same menu the tray icon has.

Drop any .vrm into LIA/vrm/ and restart. Preview the states without running
her:

    python LIA\\vrm.py          cycles through the states

And check that the window is really transparent rather than trusting the
flags -- the pixels along the inside of her window's edges are compared with
the desktop just outside them, which stays valid even if what is behind her is
moving:

    python LIA\\vrm.py --check                 prints the verdict
    python LIA\\vrm.py --check --shot her.png  also saves the photo
"""

import ctypes
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import webview

from config import (
    VRM_DIR, VRM_SIZE, VRM_POS_FILE, VRM_FRAMING, VRM_FORCE_SOFTWARE_RENDER,
    VRM_TRANSPARENCY, VRM_COLOR_KEY, VRM_MATERIAL_ALPHA_TEST,
    VRM_CLICK_THROUGH, VRM_CLICK_THROUGH_GROW,
    VRM_QUALITY, VRM_FPS_ACTIVE, VRM_FPS_IDLE, VRM_FPS_SPEAKING,
    VRM_PIXEL_RATIO, VRM_ANTIALIAS, VRM_TEXTURE_MAX, VRM_SPRING_HZ,
    VRM_MODEL, VRM_PAUSE_HIDDEN, VRM_MARGIN, VRM_MIN_SIZE, VRM_MAX_SIZE,
)

# Best effort, and only that: WebView2 reads this when it creates the browser
# process, but pywebview passes its own AdditionalBrowserArguments when it
# builds the WebView2 environment and that takes precedence -- so on this
# version the flag can be ignored entirely. It is no longer the way the opaque
# background gets fixed (see apply_window_transparency); the startup line that
# reports the WebGL renderer in use is the only trustworthy answer to whether
# software rendering is actually in force.
if VRM_FORCE_SOFTWARE_RENDER:
    os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = "--disable-gpu"

_STATES = ("idle", "listening", "thinking", "speaking")
_VENDOR = {
    "three.module.min.js": "text/javascript",
    "GLTFLoader.js": "text/javascript",
    # GLTFLoader imports this via a relative path, so the vendor layout mirrors
    # three.js's own examples/jsm tree.
    "utils/BufferGeometryUtils.js": "text/javascript",
    "three-vrm.module.js": "text/javascript",
}
_MIME = {".vrm": "model/gltf-binary", ".html": "text/html", ".js": "text/javascript"}


def find_model() -> Path | None:
    """The first .vrm in VRM_DIR, alphabetically, or None if there isn't one."""
    if not VRM_DIR.is_dir():
        return None
    for p in sorted(VRM_DIR.glob("*.vrm")):
        return p
    return None


# --------------------------------------------------------------------- page ---
# One page, no build step. The importmap maps three's bare imports onto the
# vendored files; everything below the loader is procedural motion, deliberately
# plain: she has to animate on a machine with no graphics card, where the
# software GL renderer is already spending everything she has on the model.

_PAGE = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Lia</title>
<style>
  /* All of this is load-bearing for the transparent window: any background
     color, border, shadow or outline set here paints itself into the middle of
     her rectangle, and a perfectly transparent 3D scene cannot hide it. */
  html, body { margin: 0; padding: 0; background: transparent !important;
               border: none; outline: none; overflow: hidden; }
  canvas { display: block; background: transparent !important;
           border: none; outline: none; box-shadow: none; }
  #menu { position: fixed; display: none; background: rgba(28,26,32,0.95);
          color: #eee; border-radius: 8px; padding: 4px; min-width: 150px;
          font: 13px 'Segoe UI', sans-serif; user-select: none; z-index: 10; }
  #menu div { padding: 6px 12px; border-radius: 5px; cursor: pointer; }
  #menu div:hover { background: rgba(155,111,217,0.55); }
  #menu hr { border: none; border-top: 1px solid rgba(255,255,255,0.15); margin: 3px 0; }
</style>
<script>
// Classic script on purpose: it runs before the module's imports are even
// resolved, so a failed import (the one failure mode that never reaches the
// module's own error handler) still gets reported.
window.__pageError = null;
addEventListener('error', (e) => { window.__pageError = String(e.message || (e.error && e.error.stack) || e); });
addEventListener('unhandledrejection', (e) => { window.__pageError = 'unhandled: ' + e.reason; });
</script>
<script type="importmap">
{ "imports": { "three": "/vendor/three.module.min.js" } }
</script>
</head>
<body>
<div id="menu"></div>
<script type="module">
import * as THREE from 'three';
import { GLTFLoader } from '/vendor/GLTFLoader.js';
import { VRMLoaderPlugin, VRMUtils } from '/vendor/three-vrm.module.js';

const FRAMING = '__FRAMING__';   // injected by the server: portrait | full
// Performance knobs, injected from config.py by _render_page(). FRAMES is the
// state->fps table (low | medium | high), and HIDDEN is 1 when she should stop
// drawing entirely while nobody can see her.
const FRAMES = __VRM_FRAMES__;
const PIXEL_RATIO = __VRM_PIXEL_RATIO__;
const SPRING_HZ = __VRM_SPRING_HZ__;
const HIDDEN = __VRM_PAUSE_HIDDEN__;
let springAcc = 0;

let state = 'idle';
let mouth = 0;                    // latest level from Python, 0..1
let mouthOpen = 0;                // smoothed toward mouth each frame

const scene = new THREE.Scene();
// Never a scene background, and no fog: either one would paint an opaque
// rectangle behind her inside a window that is supposed to show the desktop.
scene.background = null;
const camera = new THREE.PerspectiveCamera(22, innerWidth / innerHeight, 0.1, 20);

// alpha + premultipliedAlpha: the canvas has to carry an alpha channel itself
// and hand it to the compositor in premultiplied form, which is what the
// window is made of. setClearColor(0x000000, 0) is the cleared background.
// antialias and the pixel ratio come from config: at a 240px window the AA
// buffer is a few pixels of her silhouette that the click-through shape clips
// anyway, and 1.0x is one canvas pixel per window pixel.
const renderer = new THREE.WebGLRenderer({
  alpha: true, premultipliedAlpha: true, antialias: __VRM_ANTIALIAS__,
  powerPreference: 'low-power',
});
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(PIXEL_RATIO);
renderer.setClearColor(0x000000, 0);
// Three's default is flat: no tone mapping, and until r152 a color space that
// undersaturated every texture. ACESFilmic is the closest a transparent
// WebGL overlay gets to an "HDR" look on an ordinary SDR display -- richer
// contrast and highlight rolloff instead of clipping -- since a layered,
// color-keyed window can't actually negotiate real HDR output from Windows.
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.1;
renderer.outputColorSpace = THREE.SRGBColorSpace;
document.body.appendChild(renderer.domElement);

// What she is really rendering with, and whether the canvas is really
// transparent -- the two questions a screenshot cannot answer, readable from
// Python over the js bridge. "SwiftShader" here means every frame is being
// drawn on the CPU, whatever the config says it asked for.
const _gl = renderer.getContext();
const _dbg = _gl.getExtension('WEBGL_debug_renderer_info');
const _rendererName = _dbg ? _gl.getParameter(_dbg.UNMASKED_RENDERER_WEBGL)
                           : _gl.getParameter(_gl.RENDERER);
let _probe = null;
function probePixels() {
  const w = _gl.drawingBufferWidth, h = _gl.drawingBufferHeight;
  const buf = new Uint8Array(4);
  const at = (x, y) => {
    _gl.readPixels(x, y, 1, 1, _gl.RGBA, _gl.UNSIGNED_BYTE, buf);
    return [buf[0], buf[1], buf[2], buf[3]];
  };
  return { size: [w, h], corner: at(2, h - 3), centre: at((w / 2) | 0, (h / 2) | 0) };
}

// The mask has to be read inside the frame that drew it, for the same reason
// the pixel probe does: the drawing buffer is only guaranteed to hold that
// frame until the browser composites it. So Python asks for one, the render
// loop captures it on its next pass, and Python reads the result back.
let _mask = null, _maskWanted = false, _maskCols = 256;

// Which cells of the frame she actually occupies, for the window shape Python
// applies. Not by reading the alpha channel: that came back saying 96% of the
// frame was her, because this WebView2 composites the canvas onto its own
// backdrop and the alpha in the drawing buffer does not survive that. Clearing
// to a colour nothing of hers is, in a throwaway frame, answers the same
// question and cannot be wrong -- whatever still shows that colour is
// background. The colour is restored and the frame redrawn before returning,
// so the magenta frame is never the one the browser shows. Rows come back
// bottom-up (WebGL's own order); Python flips them.
function silhouetteMask(cols) {
  const w = _gl.drawingBufferWidth, h = _gl.drawingBufferHeight;
  const key = new THREE.Color(0xff00ff);
  const prev = renderer.getClearColor(new THREE.Color()).clone();
  const prevAlpha = renderer.getClearAlpha();
  renderer.setClearColor(key, 1);
  renderer.render(scene, camera);
  const buf = new Uint8Array(w * h * 4);
  _gl.readPixels(0, 0, w, h, _gl.RGBA, _gl.UNSIGNED_BYTE, buf);
  renderer.setClearColor(prev, prevAlpha);
  renderer.render(scene, camera);
  const rows = Math.max(1, Math.round(cols * h / w));
  let bits = '';
  for (let r = 0; r < rows; r++) {
    const y = Math.min(h - 1, Math.floor((r + 0.5) * h / rows));
    for (let c = 0; c < cols; c++) {
      const x = Math.min(w - 1, Math.floor((c + 0.5) * w / cols));
      const i = (y * w + x) * 4;
      const hers = Math.abs(buf[i] - 255) > 40 || buf[i + 1] > 40 ||
                   Math.abs(buf[i + 2] - 255) > 40;
      bits += hers ? '1' : '0';
    }
  }
  return { cols: cols, rows: rows, bits: bits };
}

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

scene.add(new THREE.HemisphereLight(0xffffff, 0x888899, 1.1));
const sun = new THREE.DirectionalLight(0xffffff, 1.4);
sun.position.set(1, 2, 2).normalize();
scene.add(sun);

const gaze = new THREE.Object3D();   // where she looks; wanders per state
scene.add(gaze);

let vrm = null;
const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));
// Hair and lashes are often alpha-textured cards, and pixels that are almost
// but not quite transparent blend into a pale halo against whatever is behind
// her. alphaTest discards them instead of blending them. 0 leaves the model's
// own material settings alone, which is the default -- see VRM_MATERIAL_ALPHA_TEST.
// Every texture larger than the cap gets redrawn into a smaller canvas and
// replaces the original in place. The loader's originals are disposed as they
// go, not left for the GC to find: an 18MB VRM carries tens of megabytes of
// texture upload, and this is the difference between her sitting at 240MB of
// RAM and 600MB of it. Called once, at load.
function capTextures(root) {
  if (!(__VRM_TEXTURE_MAX__ > 0)) return;
  const seen = new Set();
  root.traverse((o) => {
    if (!o.material) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    for (const m of mats) {
      for (const slot of Object.keys(m)) {
        const tex = m[slot];
        if (tex && tex.isTexture && tex.image && tex.image.width &&
            !seen.has(tex.uuid)) {
          seen.add(tex.uuid);
          const big = Math.max(tex.image.width, tex.image.height);
          if (big <= __VRM_TEXTURE_MAX__) continue;
          const scale = __VRM_TEXTURE_MAX__ / big;
          const c = document.createElement('canvas');
          c.width = Math.max(1, Math.round(tex.image.width * scale));
          c.height = Math.max(1, Math.round(tex.image.height * scale));
          const ctx = c.getContext('2d');
          ctx.drawImage(tex.image, 0, 0, c.width, c.height);
          const small = new THREE.CanvasTexture(c);
          small.flipY = tex.flipY;
          small.colorSpace = tex.colorSpace;
          small.wrapS = tex.wrapS; small.wrapT = tex.wrapT;
          small.flipY = tex.flipY;
          small.colorSpace = tex.colorSpace;
          small.needsUpdate = true;
          m[slot] = small;
          tex.dispose();
        }
      }
    }
  });
}

function applyAlphaTest(root) {
  if (!(__ALPHA_TEST__ > 0)) return;
  root.traverse((o) => {
    if (!o.material) return;
    const mats = Array.isArray(o.material) ? o.material : [o.material];
    for (const m of mats) { m.alphaTest = __ALPHA_TEST__; m.needsUpdate = true; }
  });
}

loader.load('/model.vrm', (gltf) => {
  vrm = gltf.userData.vrm;
  VRMUtils.removeUnnecessaryVertices(gltf.scene);
  VRMUtils.combineSkeletons(gltf.scene);
  vrm.scene.traverse((o) => { o.frustumCulled = false; });
  VRMUtils.rotateVRM0(vrm);        // VRM 0.x models face away otherwise
  applyAlphaTest(vrm.scene);
  capTextures(vrm.scene);
  scene.add(vrm.scene);

  // Frame her. Portrait fills the window with head and shoulders -- the face
  // is what reads from across a desk -- and works for any model height by
  // anchoring on the head bone. Full shows the whole body: a fixed camera
  // position assumed one fixed model height and cut most models off, so this
  // measures her actual bounding box instead and backs off far enough (at the
  // window's own aspect ratio) to fit all of it, however tall she really is.
  if (FRAMING === 'portrait') {
    const head = vrm.humanoid && vrm.humanoid.getNormalizedBoneNode('head');
    const p = new THREE.Vector3(0, 1.4, 0);
    if (head) head.getWorldPosition(p);
    camera.position.set(p.x, p.y + 0.04, p.z + 0.85);
    camera.lookAt(p);
  } else {
    const box = new THREE.Box3().setFromObject(vrm.scene);
    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const aspect = camera.aspect || 1;
    const vFov = camera.fov * Math.PI / 180;
    const hFov = 2 * Math.atan(Math.tan(vFov / 2) * aspect);
    const distV = (size.y / 2) / Math.tan(vFov / 2);
    const distH = (size.x / 2) / Math.tan(hFov / 2);
    const dist = Math.max(distV, distH) * 1.15 + size.z / 2;   // 15% headroom
    camera.position.set(center.x, center.y, center.z + dist);
    camera.lookAt(center);
  }

  if (window.pywebview && pywebview.api) pywebview.api.ready();
}, undefined, () => {
  if (window.pywebview && pywebview.api) pywebview.api.ready();
});

window.setLevel = (v) => { mouth = Math.max(0, Math.min(1, v)); };
const _STATES = ['idle', 'listening', 'thinking', 'speaking'];
window.setState = (s) => { if (_STATES.includes(s)) state = s; };
// readback for diagnostics / the self-test (module vars aren't on window)
window.__lia = {
  get state() { return state; },
  get mouth() { return mouthOpen; },
  get camera() { return camera.position.toArray(); },
  get renderer() { return _rendererName; },
  get probe() { return _probe; },
  get mask() { return _mask; },
  requestMask(cols) { _maskCols = cols; _maskWanted = true; return true; },
  setHidden(v) { hidden = !!v; },
};

// A character nobody can see has no reason to spend a frame. The page's own
// visibility tells the truth about tab-backgrounding; the window's hide from
// her menu arrives as a call from Python.
document.addEventListener('visibilitychange', () => {
  if (!HIDDEN) return;
  hidden = document.hidden;
  if (!hidden) { clock.getDelta(); }        // don't fast-forward on resume
});

// -- procedural life --------------------------------------------------------
let blinkAt = performance.now() + 1500 + Math.random() * 3000;
let blinkPhase = -1;               // -1 idle, else 0..1 progress
let wanderAt = 0;
let nodAt = 0;

function expr(name, v) {
  const em = vrm && vrm.expressionManager;
  if (em && em.getExpression(name)) em.setValue(name, v);
}
function headBone() {
  return vrm && vrm.humanoid ? vrm.humanoid.getNormalizedBoneNode('head') : null;
}

const clock = new THREE.Clock();
let hidden = false;               // true while she cannot be seen
let lastDrawn = 0;                // performance.now() of the last rendered frame

function capFor(s) {
  return (FRAMES && FRAMES[s]) || 12;
}

function tick() {
  requestAnimationFrame(tick);
  if (hidden) return;             // not a frame spent on nobody
  const dt = Math.min(clock.getDelta(), 0.1);
  const stamp = performance.now();   // 'now' is taken by the blink block below
  // Frame-rate cap per state: skip frames until the state's interval has
  // elapsed. Idle's 12fps is where she spends almost all her life, so it is
  // where the saving lives; speaking buys its higher cap back in lipsync.
  if (dt === 0 || stamp - lastDrawn < 1000 / capFor(state)) return;
  lastDrawn = stamp;
  const t = clock.elapsedTime;
  if (!vrm) { renderer.render(scene, camera); return; }

  // mouth: attack fast, release slower -- reads as speech, not flicker
  const target = state === 'speaking' ? mouth : 0;
  mouthOpen += (target - mouthOpen) * (target > mouthOpen ? 0.55 : 0.25);
  expr('aa', mouthOpen * 0.9);

  // blink (skipped while thinking looks away -- reads better)
  const now = performance.now();
  if (blinkPhase < 0 && now >= blinkAt && state !== 'thinking') blinkPhase = 0;
  if (blinkPhase >= 0) {
    blinkPhase += dt / 0.22;
    const v = Math.sin(Math.min(blinkPhase, 1) * Math.PI);
    expr('blink', v);
    if (blinkPhase >= 1) {
      blinkPhase = -1;
      blinkAt = now + 1500 + Math.random() * 3500;
    }
  }

  // breathing + state motion on the head
  const head = headBone();
  if (head) {
    const breath = Math.sin(t * 1.4) * 0.015;
    let rx = breath, ry = 0, rz = Math.sin(t * 0.9) * 0.008;
    if (state === 'listening') { rz += 0.13; rx += 0.04; }
    if (state === 'thinking')  { rz += 0.10; rx -= 0.05; }
    if (state === 'speaking')  { rx += mouthOpen * 0.05; }
    head.rotation.x += (rx - head.rotation.x) * 0.12;
    head.rotation.y += (ry - head.rotation.y) * 0.12;
    head.rotation.z += (rz - head.rotation.z) * 0.12;
  }

  // gaze wander: a new spot every few seconds, per state
  if (t > wanderAt) {
    wanderAt = t + 2 + Math.random() * 3;
    const spread = state === 'thinking' ? 0.5 : 0.25;
    gaze.position.set(
      (Math.random() - 0.5) * spread,
      1.4 + (state === 'thinking' ? 0.25 : (Math.random() - 0.5) * 0.2),
      1,
    );
  }
  if (vrm.lookAt) vrm.lookAt.target = gaze;

  const s = 1 + Math.sin(t * 1.1) * 0.004;   // idle sway
  vrm.scene.scale.setScalar(s);
  // Spring-bone physics on her own cadence (VRM_SPRING_HZ): vrm.update would
  // re-simulate the hair and skirt every frame, which is most of her per-frame
  // CPU cost for motion nobody can see at 12 fps. rAF still fires at the
  // monitor's rate; only the frames inside the cap draw, and only these step
  // the simulation.
  if (SPRING_HZ > 0) {
    if (springAcc === 0) {
      springAcc = stamp;
    } else if (stamp - springAcc >= 1000 / SPRING_HZ) {
      vrm.update(dt);
      springAcc = stamp;
    }
  } else {
    vrm.update(dt);
  }
  renderer.render(scene, camera);
  // Read once, on the first frame that has her in it: the drawing buffer is
  // only guaranteed to hold the frame until the browser composites it.
  if (_probe === null) _probe = probePixels();
  if (_maskWanted) { _mask = silhouetteMask(_maskCols); _maskWanted = false; }
}
tick();

// -- input: click vs drag, right-click menu ---------------------------------
let down = null, moved = 0, last = null;
const menuEl = document.getElementById('menu');
addEventListener('contextmenu', (e) => { e.preventDefault(); openMenu(e.clientX, e.clientY); });
addEventListener('pointerdown', (e) => {
  if (e.button === 0) { down = { x: e.clientX, y: e.clientY }; last = down; moved = 0; }
  hideMenu();
});
addEventListener('pointermove', (e) => {
  if (!down) return;
  const dx = e.clientX - last.x, dy = e.clientY - last.y;
  moved += Math.abs(dx) + Math.abs(dy);
  last = { x: e.clientX, y: e.clientY };
  if (moved > 5 && window.pywebview && pywebview.api) pywebview.api.drag_by(dx, dy);
});
addEventListener('pointerup', () => {
  if (!down) return;
  if (moved <= 5 && window.pywebview && pywebview.api) pywebview.api.clicked();
  else if (window.pywebview && pywebview.api) pywebview.api.drag_done();
  down = null;
});

async function openMenu(x, y) {
  if (!(window.pywebview && pywebview.api)) return;
  const items = JSON.parse(await pywebview.api.menu());
  menuEl.innerHTML = '';
  for (const it of items) {
    if (it.sep) { menuEl.insertAdjacentHTML('beforeend', '<hr>'); continue; }
    const d = document.createElement('div');
    d.textContent = it.label;
    d.onclick = () => { hideMenu(); pywebview.api.menu_pick(it.id); };
    menuEl.appendChild(d);
  }
  menuEl.style.display = 'block';
  menuEl.style.left = Math.min(x, innerWidth - 170) + 'px';
  menuEl.style.top = Math.min(y, innerHeight - menuEl.offsetHeight - 8) + 'px';
}
function hideMenu() { menuEl.style.display = 'none'; }
</script>
</body>
</html>
"""


def _pick_model() -> tuple[Path, str]:
    """Which VRM file to serve, honouring VRM_MODEL.

    "auto" prefers character_lite.vrm -- the optimiser's output -- and falls
    back to whatever model is actually there, with a note, when it has not
    been built. Returns (path, note); the note is empty when nothing is worth
    saying.
    """
    found = find_model()
    if found is None:
        return found, ""
    mode = str(VRM_MODEL).lower()
    if mode in ("original", "orig"):
        return found, ""
    lite = found.with_name("character_lite.vrm")
    if lite.is_file():
        return lite, (f"serving {lite.name} ({lite.stat().st_size // 1024 // 1024}MB) "
                      f"instead of {found.name} ({found.stat().st_size // 1024 // 1024}MB)")
    if mode == "lite":
        return found, (f"VRM_MODEL = 'lite' but {lite.name} does not exist -- "
                       f"serving {found.name} (see vrm/README.md)")
    return found, ""


def _render_page() -> bytes:
    """The page, with the config values the viewer needs baked into it.

    A replacement rather than a template engine: tokens, no dependency. The
    numbers are all single values except FRAMES, which arrives as a JSON
    object so the tick loop can look up the cap for the state it is in.
    """
    import json as _json

    framing = VRM_FRAMING if VRM_FRAMING in ("portrait", "full") else "portrait"
    frames = {"low": 24, "medium": 30, "high": 60}[str(VRM_QUALITY).lower()]
    page = _PAGE
    page = page.replace("__FRAMING__", framing)
    page = page.replace("__ALPHA_TEST__", f"{float(VRM_MATERIAL_ALPHA_TEST):.3f}")
    page = page.replace("__VRM_FRAMES__", _json.dumps({
        "idle": VRM_FPS_IDLE, "listening": VRM_FPS_ACTIVE,
        "thinking": VRM_FPS_ACTIVE, "speaking": VRM_FPS_SPEAKING,
    }))
    page = page.replace("__VRM_PIXEL_RATIO__", f"{float(VRM_PIXEL_RATIO):.2f}")
    page = page.replace("__VRM_ANTIALIAS__", "true" if VRM_ANTIALIAS else "false")
    page = page.replace("__VRM_SPRING_HZ__", str(int(VRM_SPRING_HZ)))
    page = page.replace("__VRM_TEXTURE_MAX__", str(int(VRM_TEXTURE_MAX)))
    page = page.replace("__VRM_PAUSE_HIDDEN__", "true" if VRM_PAUSE_HIDDEN else "false")
    return page.encode("utf-8")


# url path -> (file on disk, mime). Served under BOTH spellings: /vendor/x.js
# for the page's own imports, and /x.js for the relative paths the vendored
# modules use between themselves (GLTFLoader asks for ../utils/..., which the
# browser resolves against /vendor/ to just /utils/...).
def _vendor_urls() -> dict:
    root = Path(__file__).parent / "vrm" / "vendor"
    out = {}
    for rel, mime in _VENDOR.items():
        out[f"/vendor/{rel}"] = (root / rel, mime)
        out[f"/{rel}"] = (root / rel, mime)
    return out

_VENDOR_URLS = _vendor_urls()


class _Handler(BaseHTTPRequestHandler):
    server_version = "LiaVrm/1"

    def log_message(self, *a):        # silence per-request stdout noise
        pass

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # Rendered from loopback only; the viewer never phones home.
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        m: "VrmMascot" = self.server.mascot          # type: ignore[attr-defined]
        path = self.path.split("?", 1)[0]
        if path in ("/", "/index.html"):
            self._send(200, _render_page(), "text/html; charset=utf-8")
        elif path == "/model.vrm":
            if m.serve_path and m.serve_path.exists():
                self._send(200, m.serve_path.read_bytes(), "model/gltf-binary")
            else:
                self._send(404, b"no model", "text/plain")
        elif path in _VENDOR_URLS:
            p, mime = _VENDOR_URLS[path]
            if p.is_file():
                self._send(200, p.read_bytes(), mime)
            else:
                self._send(404, b"not found", "text/plain")
        else:
            self._send(404, b"not found", "text/plain")


class _Api:
    """The JS bridge. Numbers arrive as floats from the web side."""

    def __init__(self, mascot: "VrmMascot"):
        self._m = mascot

    def ready(self):
        self._m._mark_ready()

    def drag_by(self, dx: float, dy: float):
        self._m._drag_by(int(dx), int(dy))

    def clicked(self):
        self._m._on_click()

    def resize_by(self, delta: float):
        self._m.resize(int(delta))

    def drag_done(self):
        self._m._save_pos()

    def menu(self) -> str:
        items = []
        i = 0
        for label, cb in self._m._menu_fn():
            if label == "-" or cb is None:
                items.append({"sep": True})
            else:
                items.append({"label": label, "id": i})
                self._m._menu_cbs[i] = cb
                i += 1
        return json.dumps(items)

    def menu_pick(self, i: int):
        cb = self._m._menu_cbs.get(int(i))
        if cb is not None:
            try:
                cb()
            except Exception:
                pass


# ---------------------------------------------------- window transparency ---
# The page has been transparent all along -- the canvas is cleared to alpha 0,
# there is no scene background, nothing sets a page background -- and pywebview
# is asked for transparent=True. She still appeared inside an opaque rectangle,
# and the reason is that pywebview's entire transparency implementation is two
# lines:
#
#   Form.SupportsTransparentBackColor = True   (a child-control style; a
#                                               top-level form ignores it)
#   WebView2.DefaultBackgroundColor = Transparent   (set before the browser is
#                                               initialized, which WebView2 is
#                                               documented to be fussy about)
#
# Neither makes the window *layered*, so on a machine where the compositor does
# not carry the alpha there is no mechanism left for transparency to survive --
# and the form's own background color (#F0F0F0) shows through the browser in
# any case, which is exactly what a white rectangle around her is.
#
# So she does it herself, on the live window, and then checks the result by
# looking at the screen instead of trusting the flags.


def _window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    """(x, y, w, h) of a window, or None."""
    class RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    rect = RECT()
    if not hwnd or not ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return None
    return (rect.left, rect.top,
            rect.right - rect.left, rect.bottom - rect.top)


def _sample_background(window) -> tuple[int, int, int] | None:
    """The color actually painted behind her, read off the screen.

    Not the color anything *claims* to use: a WebView2 whose background call
    silently failed paints opaque white, a WebView2 that honoured it lets the
    form's own #F0F0F0 show through, and which of the two is true depends on
the runtime version. Sampling the border of the window and taking the most
    common color among the samples answers it directly -- and the mode rather
    than a single pixel means a strand of hair reaching into one corner cannot
    decide the key for us.
    """
    rect = _window_rect(_avatar_hwnd(window))
    if rect is None:
        return None
    x, y, w, h = rect
    if w < 20 or h < 20:
        return None
    pixels = grab_screen(x, y, w, h)
    points = [(6, 6), (w - 7, 6), (6, h - 7), (w - 7, h - 7),
              (w // 2, 6), (6, h // 2), (w - 7, h // 2), (w // 2, h - 7)]
    counts: dict[tuple[int, int, int], int] = {}
    for col, row in points:
        i = (row * w + col) * 4
        rgb = (pixels[i + 2], pixels[i + 1], pixels[i])      # BGRA -> RGB
        counts[rgb] = counts.get(rgb, 0) + 1
    return max(counts, key=lambda c: counts[c])


def _avatar_hwnd(window) -> int:
    """The top-level Win32 handle of her window."""
    try:
        title = getattr(window, "title", None) or "Lia"
        hwnd = ctypes.windll.user32.FindWindowW(None, title)
        if hwnd:
            return int(hwnd)
    except Exception:
        pass
    return 0


def apply_window_transparency(window) -> str:
    """Make the window's background actually transparent. Returns a log line.

    Two routes on purpose, because they fail differently: the managed one
    (pythonnet, already loaded in this process by pywebview's WinForms
    backend) reaches the real WebView2 control and the real Form, and the Win32
    one below it makes the window layered regardless of what WinForms believes
    it is doing. Both are idempotent, so running both costs nothing.
    """
    if str(VRM_TRANSPARENCY).lower() == "off":
        return "transparency: left as pywebview made it (VRM_TRANSPARENCY = 'off')"

    notes: list[str] = []
    form = getattr(window, "native", None)

    # 1. Ask the browser for a transparent background -- now, after the browser
    #    exists, rather than before it is initialized the way pywebview does it.
    #    WebView2 properties are UI-thread only, and this runs on the thread
    #    pywebview started for us, so it has to be marshalled onto the form.
    try:
        from System import Action
        from System.Drawing import Color

        wv = getattr(form, "webview", None) if form is not None else None
        if wv is not None:
            def _clear():
                wv.DefaultBackgroundColor = Color.Transparent

            form.Invoke(Action(_clear))
            time.sleep(0.25)                 # let it repaint before sampling
            notes.append("browser background cleared")
    except Exception as exc:
        notes.append(f"browser background left alone ({type(exc).__name__})")

    # 2. Whatever is painted behind her now, key it out -- sampled from the
    #    screen, so this keys white when the call above failed and the form's
    #    own color when it worked. An explicit VRM_COLOR_KEY overrides.
    key = None
    if VRM_COLOR_KEY and str(VRM_COLOR_KEY).lower() != "auto":
        h = str(VRM_COLOR_KEY).lstrip("#")
        if len(h) == 6:
            try:
                key = (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
            except ValueError:
                key = None
        if key is not None:
            notes.append(f"key #{key[0]:02X}{key[1]:02X}{key[2]:02X} (from config)")
    if key is None:
        key = _sample_background(window)
        if key is not None:
            notes.append(f"key #{key[0]:02X}{key[1]:02X}{key[2]:02X} (sampled)")
    if key is None:
        key = (240, 240, 240)
        notes.append("key #F0F0F0 (could not sample; WinForms default)")

    # 3. the managed route: make the form paint that color, but NOT via
    #    form.TransparencyKey. WinForms' TransparencyKey installs its own
    #    WM_NCHITTEST handling that treats every pixel matching the key as
    #    click-through -- checked against the Form's own backing surface,
    #    which stays the flat key color underneath a child WebView2 control
    #    that paints on top of it. The result: the *entire* form becomes
    #    click-through to Windows' hit-testing, no matter what WebView2 has
    #    actually drawn there or whether the window is topmost -- which is
    #    what made her impossible to click or drag no matter which of our
    #    own click-through settings was in force. BackColor alone still
    #    gives step 4's manual layered colorkey (below) the right color to
    #    key on, without installing WinForms' own hit-test override.
    try:
        from System.Drawing import Color

        if form is not None:
            key_color = Color.FromArgb(255, key[0], key[1], key[2])
            form.BackColor = key_color
            notes.append("form background-key set")
        else:
            notes.append("no native form to key")
    except Exception as exc:
        notes.append(f"form key failed ({type(exc).__name__})")

    # 4. belt and braces: a layered window keyed on the same color, which also
    #    makes those pixels click-through. Idempotent.
    hwnd = _avatar_hwnd(window)
    if hwnd:
        try:
            user32 = ctypes.windll.user32
            GWL_EXSTYLE, WS_EX_LAYERED, LWA_COLORKEY = -20, 0x00080000, 0x1
            # She is a floating character, not an app -- TOOLWINDOW drops her
            # from the taskbar and alt-tab (APPWINDOW, if pywebview set it,
            # would force her back on, so it comes off at the same time).
            WS_EX_TOOLWINDOW, WS_EX_APPWINDOW = 0x00000080, 0x00040000
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            new_style = (style | WS_EX_LAYERED | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW
            if new_style != style:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, new_style)
                notes.append("window made layered, hidden from taskbar")
            colorref = key[0] | (key[1] << 8) | (key[2] << 16)
            user32.SetLayeredWindowAttributes(hwnd, colorref, 0, LWA_COLORKEY)
            notes.append("layered colour key applied")
            # Windows 11 still draws its own chrome on a frameless layered
            # window: a 1px border, rounded corners and a drop shadow, none of
            # which a floating character should have -- they are the "thin
            # white edge" that survives every renderer-side fix, and the
            # shadow darkens the desktop in the ring around her, which is
            # exactly where any measurement of her edges looks.
            dwm = ctypes.windll.dwmapi
            DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND = 33, 1
            DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE = 34, 0xFFFFFFFE
            for attr, value in ((DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_DONOTROUND),
                                (DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE)):
                dwm.DwmSetWindowAttribute(hwnd, attr,
                                          ctypes.byref(ctypes.c_int(value)),
                                          ctypes.sizeof(ctypes.c_int))
            notes.append("window border and rounding removed")
        except Exception as exc:
            notes.append(f"layered route failed ({type(exc).__name__})")
    else:
        notes.append("window handle not found")

    return "transparency: " + "; ".join(notes)


# ------------------------------------------------------------- screen probe ---
# The only way to answer "is there still a rectangle" without a person looking
# at it: photograph the desktop where her window is, take her away for a
# moment, photograph it again, and compare. Transparent means the pixels she is
# not drawn on were the desktop both times.


class _BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", ctypes.c_uint32), ("biWidth", ctypes.c_int32),
        ("biHeight", ctypes.c_int32), ("biPlanes", ctypes.c_uint16),
        ("biBitCount", ctypes.c_uint16), ("biCompression", ctypes.c_uint32),
        ("biSizeImage", ctypes.c_uint32), ("biXPelsPerMeter", ctypes.c_int32),
        ("biYPelsPerMeter", ctypes.c_int32), ("biClrUsed", ctypes.c_uint32),
        ("biClrImportant", ctypes.c_uint32),
    ]


class _BITMAPINFO(ctypes.Structure):
    _fields_ = [("bmiHeader", _BITMAPINFOHEADER),
                ("bmiColors", ctypes.c_uint32 * 3)]


def grab_screen(x: int, y: int, w: int, h: int) -> bytes:
    """BGRA pixels of the desktop at (x, y, w, h), top row first."""
    user32, gdi32 = ctypes.windll.user32, ctypes.windll.gdi32
    src = user32.GetDC(0)
    mem = gdi32.CreateCompatibleDC(src)
    bmp = gdi32.CreateCompatibleBitmap(src, w, h)
    try:
        gdi32.SelectObject(mem, bmp)
        gdi32.BitBlt(mem, 0, 0, w, h, src, x, y, 0x00CC0020)     # SRCCOPY
        info = _BITMAPINFO()
        info.bmiHeader.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        info.bmiHeader.biWidth = w
        info.bmiHeader.biHeight = -h          # negative: rows top-down
        info.bmiHeader.biPlanes = 1
        info.bmiHeader.biBitCount = 32
        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(mem, bmp, 0, h, buf, ctypes.byref(info), 0)
        return buf.raw
    finally:
        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(mem)
        user32.ReleaseDC(0, src)


# ------------------------------------------------------------ window shape ---
# Resolution of the alpha mask the window is shaped from, and the resolution
# the check re-reads it at. 256 across a ~500px window is a 2px cell: fine
# enough that her outline is not visibly stepped, coarse enough that the mask
# is a few thousand characters over the js bridge rather than a megapixel.
_CLICK_THROUGH_COLS = 256

# Transparency makes her *look* like she is standing on the desktop; it does
# not stop her window from swallowing every click in the rectangle around her.
# The gap between those two is why the window gets a region as well: the frame
# she just rendered is read back as a coarse alpha mask, and only the cells she
# actually occupies stay part of the window. Everything else belongs to the
# desktop again -- and the anti-aliased rim at her edges is clipped off with
# it, since those pixels are not part of her shape either.


def build_region_rects(mask: dict, w: int, h: int,
                       grow: int) -> list[tuple[int, int, int, int]]:
    """Alpha mask cells -> (left, top, right, bottom) spans in window pixels.

    The mask is scaled onto the window's own rectangle rather than converted
    through the DPI scale factor: the canvas fills the window, so cell (r, c)
    maps linearly onto it, and nothing here has to know whether the page is
    rendering at 100% or 150%.
    """
    cols, rows = int(mask["cols"]), int(mask["rows"])
    bits = mask["bits"]
    rects: list[tuple[int, int, int, int]] = []
    for r in range(rows):
        row = bits[r * cols:(r + 1) * cols]
        if "1" not in row:
            continue
        image_row = rows - 1 - r                    # mask rows are bottom-up
        top = max(0, round(image_row * h / rows) - grow)
        bottom = min(h, round((image_row + 1) * h / rows) + grow)
        c = 0
        while c < cols:
            if row[c] != "1":
                c += 1
                continue
            start = c
            while c < cols and row[c] == "1":
                c += 1
            left = max(0, round(start * w / cols) - grow)
            right = min(w, round(c * w / cols) + grow)
            if right > left and bottom > top:
                rects.append((left, top, right, bottom))
    return rects


def apply_window_region(hwnd: int, rects: list[tuple[int, int, int, int]],
                        w: int, h: int) -> bool:
    """Shape the window to those spans. The system owns the region afterwards."""
    class RECTC(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class RGNDATAHEADER(ctypes.Structure):
        _fields_ = [("dwSize", ctypes.c_uint32), ("iType", ctypes.c_uint32),
                    ("nCount", ctypes.c_uint32), ("nRgnSize", ctypes.c_uint32),
                    ("rcBound", RECTC)]

    header_size = 32                       # sizeof(RGNDATAHEADER), both bit-nesses
    count = len(rects)
    buf = ctypes.create_string_buffer(header_size + 16 * count)
    header = RGNDATAHEADER.from_buffer(buf)
    header.dwSize = header_size
    header.iType = 1                       # RDH_RECTANGLES
    header.nCount = count
    header.nRgnSize = 16 * count
    header.rcBound = RECTC(0, 0, w, h)
    for i, (left, top, right, bottom) in enumerate(rects):
        ctypes.memmove(ctypes.addressof(buf) + header_size + i * 16,
                       ctypes.byref(RECTC(left, top, right, bottom)), 16)

    gdi32, user32 = ctypes.windll.gdi32, ctypes.windll.user32
    region = gdi32.ExtCreateRegion(None, len(buf), ctypes.byref(buf))
    if not region:
        return False
    if not user32.SetWindowRgn(hwnd, region, True):
        gdi32.DeleteObject(region)
        return False
    return True                    # SetWindowRgn took ownership of the region


def region_contains(hwnd: int, x: int, y: int) -> bool | None:
    """Is (x, y), in window coordinates, inside the window's region?

    None means the window has no region at all -- in which case it owns its
    whole rectangle.
    """
    gdi32, user32 = ctypes.windll.gdi32, ctypes.windll.user32
    probe = gdi32.CreateRectRgn(0, 0, 0, 0)
    try:
        if user32.GetWindowRgn(hwnd, probe) == 0:
            return None
        return bool(gdi32.PtInRegion(probe, x, y))
    finally:
        gdi32.DeleteObject(probe)


def hit_test_report(window, mask: dict | None = None) -> list[str]:
    """Does her window still take the mouse everywhere she is not drawn?

    The other half of "transparent": if the desktop around her cannot be
    clicked, she is still a rectangle to the mouse even when she is nothing to
    the eye. This checks the window's region against the shape it was built
    from, which is the only thing that decides where clicks land.
    """
    hwnd = _avatar_hwnd(window)
    rect = _window_rect(hwnd)
    if rect is None or not hwnd:
        return []
    _, _, w, h = rect

    # The region is the decisive test, and the reason this does not merely ask
    # WindowFromPoint: that returns the same child window for every point of a
    # layered window's rectangle, transparent or not, so it cannot tell
    # click-through from a rectangle. A point outside the window's region does
    # not belong to the window, full stop.
    #
    # The points come from the shape itself rather than from "the corners are
    # obviously background": she is portrait-framed, so her hair reaches the
    # top corners of the window and the background is a set of small patches
    # beside it. Sampling the mask is the only way to test where the background
    # really is.
    # The mask the window was shaped from, when the caller has it. A freshly
    # captured one is a later frame -- she breathes and her head sways -- so
    # testing against it would measure her movement, not the shaping.
    if mask is None:
        try:
            window.evaluate_js(f"window.__lia.requestMask({_CLICK_THROUGH_COLS})")
            time.sleep(0.4)
            fresh = window.evaluate_js("window.__lia.mask")
            mask = fresh if isinstance(fresh, dict) else None
        except Exception:
            mask = None

    lines: list[str] = []
    if mask is None or not mask.get("bits"):
        lines.append("VERDICT: could not read her shape, so nothing to test")
        return lines

    cols, rows, bits = int(mask["cols"]), int(mask["rows"]), str(mask["bits"])
    her_cells = bits.count("1")
    total_cells = cols * rows
    lines.append(f"  her shape covers {her_cells / total_cells * 100:.1f}% of the "
                 f"window; the other {100 - her_cells / total_cells * 100:.1f}% "
                 "is background the desktop should get")

    # Only cells that are unambiguously her or unambiguously background are
    # tested: a cell on the edge of her outline flips between frames on its own
    # (she breathes, her head sways), and the shape was taken from one frame
    # and is being compared against another. Boundary drift is not a fault in
    # the shaping, so it must not be measured as one.
    def unambiguous(r: int, c: int) -> bool:
        want = bits[r * cols + c]
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < cols:
                    if bits[rr * cols + cc] != want:
                        return False
        return True

    checked = wrong = 0
    for r in range(rows):
        image_row = rows - 1 - r
        y = int((image_row + 0.5) * h / rows)
        for c in range(cols):
            if (r * 7 + c * 3) % 23:        # a cheap scatter, not every cell
                continue
            if not unambiguous(r, c):
                continue
            want = bits[r * cols + c] == "1"
            x = int((c + 0.5) * w / cols)
            got = region_contains(hwnd, x, y)
            if got is None:
                lines.append("VERDICT: her window has no region at all, so the "
                             "rectangle around her still takes the mouse")
                return lines
            checked += 1
            if got != want:
                wrong += 1
    lines.append(f"  {checked} unambiguous points tested (cells away from her "
                 f"outline, which moves between frames): {checked - wrong} match "
                 f"her shape, {wrong} do not")
    if checked == 0:
        lines.append("VERDICT: nothing sampled -- check the mask above")
    elif wrong == 0:
        lines.append("VERDICT: click-through works -- every unambiguous "
                     "background point falls outside her window and every "
                     "point of her falls inside")
    elif wrong <= checked * 0.05:
        lines.append("VERDICT: click-through works, with a few cells of slack "
                     f"({wrong}/{checked} disagree)")
    else:
        lines.append(f"VERDICT: her shape does not match her ({wrong}/{checked} "
                     "points disagree)")
    return lines


def _set_window_icon(window) -> str:
    """Your icon on her window's own handle.

    She is TOOLWINDOW (see apply_window_transparency), so this no longer
    reaches a taskbar or alt-tab entry -- only the tray icon (make_icon.py,
    via app.py) is visible day to day. Kept because Windows still asks a
    window for WM_SETICON regardless, and a future non-toolwindow mode (a
    debug window, say) would want it already wired.
    """
    try:
        from make_icon import ICO_PATH
    except Exception:
        return "window icon: make_icon unavailable"
    if not ICO_PATH.is_file():
        return ("window icon: assets/lia.ico not built yet (drop an image "
                "into LIA/assets/ and run make_icon.py)")
    hwnd = _avatar_hwnd(window)
    if not hwnd:
        return "window icon: window handle not found"
    user32 = ctypes.windll.user32
    IMAGE_ICON, LR_LOADFROMFILE, LR_DEFAULTSIZE = 1, 0x00000010, 0x00000040
    big = user32.LoadImageW(None, str(ICO_PATH), IMAGE_ICON, 0, 0,
                            LR_LOADFROMFILE | LR_DEFAULTSIZE)
    small = user32.LoadImageW(None, str(ICO_PATH), IMAGE_ICON, 16, 16,
                              LR_LOADFROMFILE)
    WM_SETICON, ICON_BIG, ICON_SMALL = 0x80, 1, 0
    if big:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_BIG, big)
    if small:
        user32.SendMessageW(hwnd, WM_SETICON, ICON_SMALL, small)
    if big or small:
        return "window icon: your assets/lia.ico set on the window handle"
    return "window icon: could not load assets/lia.ico"


def transparency_report(window, shot: str | None = None,
                        mask: dict | None = None) -> str:
    """Compare the pixels just inside her window's edges with the desktop just
    outside them. Returns the verdict.

    Photographing her with and without the window is the obvious test, and it
    is the wrong one: anything moving behind her -- a terminal scrolling, a
    video, a live wallpaper -- changes every pixel in the region between the
    two photographs, which is indistinguishable from an opaque rectangle. So
    this measures the thing that actually distinguishes the two cases.

    An opaque background is *flat and discontinuous*: one colour repeated
    along the whole band just inside the window edge, with no relationship to
    the desktop one pixel outside it. A transparent one continues the
    desktop's own pixels across the window's boundary. Two numbers per edge:
    share-of-the-band that is a single colour, and how far the inside band sits
    from the outside band next to it.
    """
    hwnd = _avatar_hwnd(window)
    rect = _window_rect(hwnd)
    if rect is None:
        return "could not locate her window"
    wx, wy, w, h = rect

    pad = 8                       # a margin of the desktop around her window
    x, y, rw, rh = wx - pad, wy - pad, w + pad * 2, h + pad * 2
    grab = grab_screen(x, y, rw, rh)

    if shot:
        try:
            from PIL import Image

            # BGRX raw: the DIB is BGRA and its rows are already top-down
            # (biHeight is negative), so no flip and no channel juggling.
            Image.frombytes("RGB", (rw, rh), grab, "raw", "BGRX").save(shot)
        except Exception as exc:
            print(f"  (could not save {shot}: {exc})")

    # Count every colour inside her window, from the raw BGRA bytes.
    counts: dict[tuple[int, int, int], int] = {}
    for row in range(pad, pad + h):
        base = row * rw * 4 + pad * 4
        for i in range(base, base + w * 4, 4):
            c = (grab[i + 2], grab[i + 1], grab[i])
            counts[c] = counts.get(c, 0) + 1
    total = w * h

    # The only colours an opaque avatar window can be: the two backgrounds that
    # were painting around her before this was fixed. If either one covers any
    # meaningful part of her window, something is painting a background; if
    # neither does, the pixels where she is not drawn are the desktop -- and no
    # amount of desktop, textured or flat, can be either of these two colours
    # in bulk by coincidence.
    suspects = (((240, 240, 240), "WinForms background #F0F0F0"),
                ((255, 255, 255), "WebView2 default background #FFFFFF"))
    top = sorted(counts.items(), key=lambda kv: -kv[1])[:4]
    lines = [f"window {w}x{h} at ({wx}, {wy}) -- {total:,} pixels inside her window",
             "most common colours inside:"]
    for col, n in top:
        lines.append(f"    #{col[0]:02X}{col[1]:02X}{col[2]:02X}"
                     f"  {n / total * 100:5.1f}%")

    opaque = [f"{name} covers {counts.get(c, 0) / total * 100:.1f}%"
              for c, name in suspects if counts.get(c, 0) / total * 100 > 5]
    if opaque:
        lines.append("VERDICT: still opaque -- " + "; ".join(opaque))
    else:
        flat_col, flat_n = top[0]
        lines.append(
            f"no window background colour present (largest single colour is "
            f"#{flat_col[0]:02X}{flat_col[1]:02X}{flat_col[2]:02X} at "
            f"{flat_n / total * 100:.1f}%)")
        lines.append("VERDICT: transparent -- what is around her is the desktop")
        if flat_n / total > 0.7:
            lines.append("  (that colour covers most of her window, so it is a flat "
                         "patch of desktop behind her -- confirm with --shot if it "
                         "looks wrong on screen)")
    lines.append("")
    lines.extend(hit_test_report(window, mask))
    return "\n".join(lines)


def _window_height(width: int) -> int:
    """Her window's height for a given width.

    Portrait crops to head-and-shoulders, so a truly square window is right.
    Full-body framing puts a whole standing figure inside that same window,
    which is why she came out tiny at a square size -- a person is roughly
    twice as tall as wide, so full framing asks for a window in that
    proportion instead.
    """
    if str(VRM_FRAMING).lower() == "full":
        return int(width * 1.8)
    return width


def mask_debug(window) -> str:
    """The alpha mask as a picture, for when the shape comes out wrong."""
    try:
        window.evaluate_js("window.__lia.requestMask(64)")
        time.sleep(0.4)
        mask = window.evaluate_js("window.__lia.mask")
    except Exception as exc:
        return f"mask: unavailable ({exc})"
    if not isinstance(mask, dict) or not mask.get("bits"):
        return "mask: nothing captured"
    cols, rows, bits = int(mask["cols"]), int(mask["rows"]), str(mask["bits"])
    out = [f"mask {cols}x{rows}, {bits.count('1') / (cols * rows) * 100:.0f}% hers:"]
    for r in range(rows):                       # bottom-up, in WebGL's order
        out.append("  " + bits[r * cols:(r + 1) * cols].replace("1", "#").replace("0", "."))
    return "\n".join(out)


class VrmMascot:
    """Same contract mascot.py had: state_fn/on_click/menu_fn in,
    hide/show/stop/mainloop out. Runs the webview on the calling thread."""

    def __init__(self, model_path: Path, state_fn=None, on_click=None, menu_fn=None,
                 on_ready=None):
        # model_path is what the app found; serve_path is what /model.vrm
        # actually returns -- the optimised character_lite.vrm when VRM_MODEL
        # allows it and the file exists, the found model otherwise. The note is
        # printed once at startup so the choice is visible in the log.
        self.model_path = model_path
        self.serve_path, self.model_note = _pick_model()
        self._state_fn = state_fn or (lambda: "idle")
        self._on_click = on_click or (lambda: None)
        self._menu_fn = menu_fn or (lambda: [])
        # Called with the mascot once the window is up and the model is in,
        # on its own thread. Used by the transparency check.
        self._on_ready = on_ready
        self._menu_cbs: dict[int, object] = {}
        self._ready = threading.Event()
        self._stopped = threading.Event()
        # Set once the window has been shaped to her silhouette, so anything
        # that measures the window knows the shape was actually attempted, and
        # the mask it was shaped from, so it can be tested against exactly what
        # the window was built from.
        self._shape_ready = threading.Event()
        self._shape_mask: dict | None = None
        self._level_sink_on = False

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        self._server.mascot = self                     # type: ignore[attr-defined]
        self._url = f"http://127.0.0.1:{self._server.server_address[1]}/"
        threading.Thread(target=self._server.serve_forever, daemon=True).start()

        self.window = webview.create_window(
            "Lia",
            url=self._url,
            js_api=_Api(self),
            width=VRM_SIZE,
            height=_window_height(VRM_SIZE),
            # pywebview defaults to a 200x100 floor (WinForms MinimumSize),
            # which silently overrode any VRM_SIZE/VRM_MIN_SIZE below 200 --
            # she was never actually as small as the config said. Tied to our
            # own floor so "Smaller" can still reach it too.
            min_size=(VRM_MIN_SIZE, VRM_MIN_SIZE),
            transparent=True,
            frameless=True,
            on_top=False,                  # she should not cover other windows
            easy_drag=False,               # drag is handled in JS (click vs drag)
            shadow=False,
        )
        # Placement waits for mainloop: window.move() blocks on pywebview's
        # shown event, which cannot fire until webview.start runs -- calling
        # it from the constructor held every app start for its full 15-second
        # event timeout, invisibly, inside LiaApp.__init__.

    # -- placement and size -------------------------------------------------

    def _size(self) -> int:
        """Her window's current width, within the configured limits."""
        try:
            saved = json.loads(Path(VRM_POS_FILE).read_text())
            return max(VRM_MIN_SIZE, min(VRM_MAX_SIZE, int(saved.get("w", VRM_SIZE))))
        except Exception:
            return VRM_SIZE

    def _place(self):
        size = self._size()
        height = _window_height(size)
        # Fixed at the top-left, on purpose: not a default for when nothing
        # is saved, but her one spot every launch. A dragged position is not
        # read or written for x/y any more -- only her width still comes from
        # VRM_POS_FILE (via _size), since "Bigger"/"Smaller" should still
        # stick between runs even though where she sits does not.
        x, y = VRM_MARGIN, VRM_MARGIN
        try:
            self.window.resize(size, height)
            self.window.move(x, y)
        except Exception:
            pass

    def _save_pos(self):
        try:
            Path(VRM_POS_FILE).write_text(json.dumps(
                {"x": self.window.x, "y": self.window.y,
                 "w": self.window.width}))
        except Exception:
            pass

    def resize(self, delta: int):
        """Grow or shrink her window by whole steps, re-shape to the new
        silhouette, and remember it. Clamped to VRM_MIN_SIZE/VRM_MAX_SIZE."""
        size = max(VRM_MIN_SIZE, min(VRM_MAX_SIZE, self._size() + delta))
        if size == self._size():
            return
        try:
            self.window.resize(size, _window_height(size))
            # The silhouette mask is in old-window coordinates; the region
            # must be rebuilt for the new frame or it clips the wrong shape.
            self._shape_ready.clear()
            threading.Thread(target=self.shape_window, daemon=True).start()
            self._save_pos()
        except Exception:
            pass

    # -- called from the web bridge ------------------------------------------

    def _drag_by(self, dx: int, dy: int):
        try:
            self.window.move(self.window.x + dx, self.window.y + dy)
        except Exception as exc:
            print(f"[avatar: drag failed -- {type(exc).__name__}: {exc}]")

    def _mark_ready(self):
        self._ready.set()

    def setHidden(self, hidden: bool):
        """Tell the page to stop or resume drawing. Called when her window is
        hidden from her menu; the page watches visibilitychange itself for the
        browser-side cases."""
        try:
            self.window.evaluate_js(f"window.__lia.setHidden({json.dumps(bool(hidden))})")
        except Exception:
            pass

    def shape_window(self) -> str:
        """Clip the window down to her silhouette. Returns a log line.

        Waits for a frame with her in it first: the mask comes from the drawing
        buffer, and shaping the window from a frame taken before the model
        loaded would clip her away entirely.
        """
        if str(VRM_CLICK_THROUGH).lower() == "off":
            return "click-through: off (her whole rectangle takes the mouse)"

        hwnd = _avatar_hwnd(self.window)
        rect = _window_rect(hwnd)
        if not hwnd or rect is None:
            return "click-through: could not find her window"
        _, _, w, h = rect
        grow = max(0, int(VRM_CLICK_THROUGH_GROW))

        mask = None
        cols = _CLICK_THROUGH_COLS
        for attempt in range(20):              # ~6s for the model to appear
            try:
                self.window.evaluate_js(f"window.__lia.requestMask({cols})")
                time.sleep(0.2)
                candidate = self.window.evaluate_js("window.__lia.mask")
            except Exception:
                candidate = None
            if isinstance(candidate, dict) and "1" in str(candidate.get("bits", "")):
                mask = candidate
                break
            time.sleep(0.15)
        if mask is None:
            return "click-through: nothing of her had rendered yet"

        # Keep the mask the shape was actually built from: her outline moves
        # (she breathes, her head sways), so a mask taken a second later is a
        # different silhouette, and testing the window against that one would
        # report the movement as a fault.
        self._shape_mask = mask
        rects = build_region_rects(mask, w, h, grow)
        if not rects:
            return "click-through: her shape came out empty"
        if not apply_window_region(hwnd, rects, w, h):
            return "click-through: could not shape the window"
        cells = int(mask["cols"]) * int(mask["rows"])
        covered = str(mask["bits"]).count("1")
        return (f"click-through: window shaped to {len(rects)} spans from a "
                f"{mask['cols']}x{mask['rows']} alpha mask, "
                f"{covered / cells * 100:.0f}% of the frame is hers ({grow}px slack)")

    def _log_renderer(self):
        """One line saying what she is really drawing with, and whether the
        canvas really came out transparent.

        Both are unanswerable from outside the window, and both are exactly
        what "the flags say it should be fine" got wrong before: the renderer
        name separates hardware from software rendering ("SwiftShader" means
        every frame is on the CPU), and the corner alpha says whether the web
        layer is contributing any transparency of its own.
        """
        try:
            # __pageError first: the classic script at the top of the page
            # catches anything that kills the module before window.__lia even
            # exists, which is exactly the failure that would otherwise show
            # up here as two silent nulls.
            page_error = self.window.evaluate_js("window.__pageError")
            if page_error:
                print(f"[avatar: the viewer page failed: {page_error}]")
            name = self.window.evaluate_js("window.__lia && window.__lia.renderer")
            probe = self.window.evaluate_js("window.__lia && window.__lia.probe")
        except Exception:
            return
        bits = []
        if name:
            bits.append(f"WebGL via {name}")
        if isinstance(probe, dict):
            centre, corner = probe.get("centre"), probe.get("corner")
            if centre and corner:
                bits.append(f"canvas alpha centre {centre[3]}, corner {corner[3]}"
                            + ("" if corner[3] == 0 else
                               " -- the canvas itself is painting a background"))
        if bits:
            print("[avatar: " + "; ".join(bits) + "]")

    # -- state -> page ---------------------------------------------------

    def _push_state(self, want: str):
        try:
            self.window.evaluate_js(f"window.setState({json.dumps(want)})")
        except Exception:
            pass

    def _on_level(self, level: float):
        if not self._level_sink_on:
            return
        try:
            self.window.evaluate_js(f"window.setLevel({level:.3f})")
        except Exception:
            pass

    def _poll_state(self):
        last = None
        while not self._stopped.is_set():
            try:
                want = self._state_fn()
            except Exception:
                want = "idle"
            if want in _STATES and want != last:
                last = want
                self._push_state(want)
            self._stopped.wait(0.15)

    # -- lifecycle ---------------------------------------------------------

    def mainloop(self):
        import voice

        def _post_start():
            self._ready.wait(10)          # model may take a moment to parse
            self._place()                 # move() only works once started
            if self.model_note:
                print(f"[avatar: {self.model_note}]")
            print(f"[avatar: {apply_window_transparency(self.window)}]")
            print(f"[avatar: {_set_window_icon(self.window)}]")
            self._log_renderer()
            print(f"[avatar: {self.shape_window()}]")
            self._shape_ready.set()
            threading.Thread(target=self._poll_state, daemon=True).start()
            voice.set_audio_level_sink(self._on_level)
            self._level_sink_on = True
            if self._on_ready is not None:
                threading.Thread(target=self._on_ready, args=(self,),
                                 daemon=True).start()

        try:
            webview.start(func=_post_start, gui="edgechromium")
        except Exception as exc:
            print(f"[vrm: the avatar window failed to open ({exc}) -- "
                  "running without it]")
        finally:
            self._level_sink_on = False
            voice.set_audio_level_sink(None)
            self._stopped.set()
            self._save_pos()
            self._server.shutdown()

    def hide(self):
        try:
            self.setHidden(True)          # stop spending frames on nobody
            self.window.hide()
        except Exception:
            pass

    def show(self):
        try:
            self.window.show()
            self.setHidden(False)
        except Exception:
            pass

    def stop(self):
        self._stopped.set()
        try:
            self.window.destroy()
        except Exception:
            pass


# ------------------------------------------------------------------ preview ---

def _check_transparency(m: "VrmMascot") -> None:
    """Print whether the window is really transparent, then close."""
    shot = None
    for i, arg in enumerate(sys.argv):
        if arg == "--shot" and i + 1 < len(sys.argv):
            shot = sys.argv[i + 1]
    m._shape_ready.wait(10)
    time.sleep(0.6)                   # let a few frames land first
    print()
    print(transparency_report(m.window, shot=shot, mask=m._shape_mask))
    if "--mask" in sys.argv:
        print()
        print(mask_debug(m.window))
    m.stop()


if __name__ == "__main__":
    import itertools

    model = find_model()
    if model is None:
        print(f"no .vrm found in {VRM_DIR} -- drop one in and try again")
        raise SystemExit(1)

    check = "--check" in sys.argv
    cycle = itertools.cycle(_STATES)
    current = {"s": next(cycle), "m": 0.0}

    m = VrmMascot(
        model_path=model,
        state_fn=lambda: current["s"],
        on_click=lambda: print("click"),
        menu_fn=lambda: [("Next state", lambda: current.update(s=next(cycle))),
                         ("-", None), ("Quit", lambda: m.stop())],
        on_ready=_check_transparency if check else None,
    )
    print("vrm transparency check (measuring her window's edges)" if check
          else "vrm preview -- right-click to step through states")

    def step():
        while not m._stopped.is_set():
            time.sleep(3)
            if m._stopped.is_set():
                return
            current["s"] = next(cycle)
            print("state:", current["s"])

    import math
    import threading as _th

    def _loop():
        while not m._stopped.is_set():
            # fake mouth movement while she is "speaking"
            level = 0.45 + 0.35 * math.sin(time.time() * 7) \
                if current["s"] == "speaking" else 0.0
            m._on_level(max(0.0, level))
            m._stopped.wait(0.05)

    _th.Thread(target=_loop, daemon=True).start()
    _th.Thread(target=step, daemon=True).start()
    m.mainloop()
