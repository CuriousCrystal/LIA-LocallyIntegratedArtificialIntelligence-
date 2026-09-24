"""The desktop avatar: Lia as a 3D VRM character, floating over your windows.

Replaces the old 2D sprite mascot with the format VTuber apps use. A tiny
loopback HTTP server serves a single-page three.js viewer (three + three-vrm
are vendored in vrm/vendor/, so this renders with no network); pywebview shows
it in a frameless, transparent, always-on-top window. The model is the first
*.vrm found in VRM_DIR.

It reflects one state -- idle / listening / thinking / speaking -- read every
~150ms from a callback the app hands in, exactly like mascot.py did. Blinking,
breathing and idle sway are procedural; the mouth is driven by the real
loudness of Piper's audio (see voice.set_audio_level_sink). Drag to move (the
position is remembered); left-click toggles listening; right-click opens the
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
const renderer = new THREE.WebGLRenderer({
  alpha: true, premultipliedAlpha: true, antialias: true,
});
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x000000, 0);
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
  scene.add(vrm.scene);

  // Frame her. Portrait fills the window with head and shoulders -- the face
  // is what reads from across a desk -- and works for any model height by
  // anchoring on the head bone. Full shows the whole body.
  if (FRAMING === 'portrait') {
    const head = vrm.humanoid && vrm.humanoid.getNormalizedBoneNode('head');
    const p = new THREE.Vector3(0, 1.4, 0);
    if (head) head.getWorldPosition(p);
    camera.position.set(p.x, p.y + 0.04, p.z + 0.85);
    camera.lookAt(p);
  } else {
    camera.position.set(0, 1.35, 1.9);
    camera.lookAt(0, 1.0, 0);
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
};

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
function tick() {
  requestAnimationFrame(tick);
  const dt = Math.min(clock.getDelta(), 0.1);
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
  vrm.update(dt);
  renderer.render(scene, camera);
  // Read once, on the first frame that has her in it: the drawing buffer is
  // only guaranteed to hold the frame until the browser composites it.
  if (_probe === null) _probe = probePixels();
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


def _render_page() -> bytes:
    """The page, with the config values the viewer needs baked into it.

    A replacement rather than a template engine: two tokens, no dependency.
    """
    framing = VRM_FRAMING if VRM_FRAMING in ("portrait", "full") else "portrait"
    page = _PAGE.replace("__FRAMING__", framing)
    page = page.replace("__ALPHA_TEST__", f"{float(VRM_MATERIAL_ALPHA_TEST):.3f}")
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
            if m.model_path and m.model_path.exists():
                self._send(200, m.model_path.read_bytes(), "model/gltf-binary")
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

    # 3. the managed route: make the form paint and key the same color.
    try:
        from System.Drawing import Color

        if form is not None:
            key_color = Color.FromArgb(255, key[0], key[1], key[2])
            form.BackColor = key_color
            form.TransparencyKey = key_color
            notes.append("form transparent-key set")
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
            style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            if not style & WS_EX_LAYERED:
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
                notes.append("window made layered")
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


def transparency_report(window, shot: str | None = None) -> str:
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
    return "\n".join(lines)


class VrmMascot:
    """Same contract mascot.py had: state_fn/on_click/menu_fn in,
    hide/show/stop/mainloop out. Runs the webview on the calling thread."""

    def __init__(self, model_path: Path, state_fn=None, on_click=None, menu_fn=None,
                 on_ready=None):
        self.model_path = model_path
        self._state_fn = state_fn or (lambda: "idle")
        self._on_click = on_click or (lambda: None)
        self._menu_fn = menu_fn or (lambda: [])
        # Called with the mascot once the window is up and the model is in,
        # on its own thread. Used by the transparency check.
        self._on_ready = on_ready
        self._menu_cbs: dict[int, object] = {}
        self._ready = threading.Event()
        self._stopped = threading.Event()
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
            height=VRM_SIZE + 30,
            transparent=True,
            frameless=True,
            on_top=True,
            easy_drag=False,               # drag is handled in JS (click vs drag)
            shadow=False,
        )
        self._place()

    # -- placement ----------------------------------------------------------

    def _place(self):
        user32 = ctypes.windll.user32
        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        x, y = sw - VRM_SIZE - 40, sh - VRM_SIZE - 110     # bottom-right default
        try:
            saved = json.loads(Path(VRM_POS_FILE).read_text())
            x, y = int(saved["x"]), int(saved["y"])
        except Exception:
            pass
        x = max(0, min(x, sw - VRM_SIZE))
        y = max(0, min(y, sh - VRM_SIZE))
        try:
            self.window.move(x, y)
        except Exception:
            pass

    def _save_pos(self):
        try:
            Path(VRM_POS_FILE).write_text(json.dumps(
                {"x": self.window.x, "y": self.window.y}))
        except Exception:
            pass

    # -- called from the web bridge ------------------------------------------

    def _drag_by(self, dx: int, dy: int):
        try:
            self.window.move(self.window.x + dx, self.window.y + dy)
        except Exception:
            pass

    def _mark_ready(self):
        self._ready.set()

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
            print(f"[avatar: {apply_window_transparency(self.window)}]")
            self._log_renderer()
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
            self.window.hide()
        except Exception:
            pass

    def show(self):
        try:
            self.window.show()
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
    time.sleep(1.2)                   # let a few frames land first
    print()
    print(transparency_report(m.window, shot=shot))
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
