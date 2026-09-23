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
"""

import ctypes
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import webview

from config import VRM_DIR, VRM_SIZE, VRM_POS_FILE

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
  html, body { margin: 0; padding: 0; background: transparent; overflow: hidden; }
  canvas { display: block; }
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

let state = 'idle';
let mouth = 0;                    // latest level from Python, 0..1
let mouthOpen = 0;                // smoothed toward mouth each frame

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(22, innerWidth / innerHeight, 0.1, 20);
camera.position.set(0, 1.35, 1.9);

const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
renderer.setSize(innerWidth, innerHeight);
renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
renderer.setClearColor(0x000000, 0);
document.body.appendChild(renderer.domElement);

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
loader.load('/model.vrm', (gltf) => {
  vrm = gltf.userData.vrm;
  VRMUtils.removeUnnecessaryVertices(gltf.scene);
  VRMUtils.combineSkeletons(gltf.scene);
  vrm.scene.traverse((o) => { o.frustumCulled = false; });
  VRMUtils.rotateVRM0(vrm);        // VRM 0.x models face away otherwise
  scene.add(vrm.scene);
  if (window.pywebview && pywebview.api) pywebview.api.ready();
}, undefined, () => {
  if (window.pywebview && pywebview.api) pywebview.api.ready();
});

window.setLevel = (v) => { mouth = Math.max(0, Math.min(1, v)); };
const _STATES = ['idle', 'listening', 'thinking', 'speaking'];
window.setState = (s) => { if (_STATES.includes(s)) state = s; };
// readback for diagnostics / the self-test (module vars aren't on window)
window.__lia = { get state() { return state; }, get mouth() { return mouthOpen; } };

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
            self._send(200, _PAGE.encode("utf-8"), "text/html; charset=utf-8")
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


class VrmMascot:
    """Same contract mascot.py had: state_fn/on_click/menu_fn in,
    hide/show/stop/mainloop out. Runs the webview on the calling thread."""

    def __init__(self, model_path: Path, state_fn=None, on_click=None, menu_fn=None):
        self.model_path = model_path
        self._state_fn = state_fn or (lambda: "idle")
        self._on_click = on_click or (lambda: None)
        self._menu_fn = menu_fn or (lambda: [])
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
            threading.Thread(target=self._poll_state, daemon=True).start()
            voice.set_audio_level_sink(self._on_level)
            self._level_sink_on = True

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

if __name__ == "__main__":
    import itertools

    model = find_model()
    if model is None:
        print(f"no .vrm found in {VRM_DIR} -- drop one in and try again")
        raise SystemExit(1)

    cycle = itertools.cycle(_STATES)
    current = {"s": next(cycle), "m": 0.0}

    m = VrmMascot(
        model_path=model,
        state_fn=lambda: current["s"],
        on_click=lambda: print("click"),
        menu_fn=lambda: [("Next state", lambda: current.update(s=next(cycle))),
                         ("-", None), ("Quit", lambda: m.stop())],
    )
    print("vrm preview -- right-click to step through states")

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
