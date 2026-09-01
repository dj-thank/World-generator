from __future__ import annotations

import html
from pathlib import Path

from ..media import copy_media

_IMPORT_MAP = """{
  "imports": {
    "three": "https://cdn.jsdelivr.net/npm/three@0.180.0/build/three.module.js",
    "three/addons/": "https://cdn.jsdelivr.net/npm/three@0.180.0/examples/jsm/",
    "@sparkjsdev/spark": "https://sparkjs.dev/releases/spark/2.1.0/spark.module.js"
  }
}"""


def _base_css() -> str:
    return """
html, body { width: 100%; height: 100%; margin: 0; overflow: hidden; background: #05070b; color: white; font-family: system-ui, sans-serif; }
canvas { display: block; }
#hud { position: fixed; z-index: 10; top: 14px; left: 14px; max-width: min(440px, calc(100vw - 28px)); padding: 11px 13px; border-radius: 12px; background: rgba(5, 8, 14, .72); backdrop-filter: blur(10px); line-height: 1.45; font-size: 13px; }
#hud strong { display: block; font-size: 15px; margin-bottom: 3px; }
#status { opacity: .78; }
#reticle { position: fixed; left: 50%; top: 50%; width: 5px; height: 5px; margin: -2px; border-radius: 50%; background: rgba(255,255,255,.8); pointer-events: none; }
"""


def export_splat_viewer(splat_path: Path, output_dir: Path, *, title: str) -> Path:
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    copy_media(splat_path, assets / "world.ply")
    safe_title = html.escape(title)
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#05070b">
  <title>{safe_title}</title>
  <style>{_base_css()}</style>
  <script type="importmap">{_IMPORT_MAP}</script>
</head>
<body>
  <div id="hud"><strong>{safe_title}</strong><span id="status">Loading Gaussian Splat…</span><br>Desktop: click, then WASD. VR: use Enter VR and controller thumbsticks.</div>
  <div id="reticle"></div>
  <script type="module">
    import * as THREE from "three";
    import {{ VRButton }} from "three/addons/webxr/VRButton.js";
    import {{ PointerLockControls }} from "three/addons/controls/PointerLockControls.js";
    import {{ SparkRenderer, SplatMesh }} from "@sparkjsdev/spark";

    const status = document.querySelector('#status');
    const scene = new THREE.Scene();
    scene.background = new THREE.Color(0x05070b);

    const rig = new THREE.Group();
    scene.add(rig);
    const camera = new THREE.PerspectiveCamera(65, innerWidth / innerHeight, 0.01, 1000);
    camera.position.set(0, 1.65, 0);
    rig.add(camera);

    const renderer = new THREE.WebGLRenderer({{ antialias: false, powerPreference: 'high-performance' }});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 1.75));
    renderer.setSize(innerWidth, innerHeight);
    renderer.xr.enabled = true;
    document.body.appendChild(renderer.domElement);
    document.body.appendChild(VRButton.createButton(renderer));

    const spark = new SparkRenderer({{ renderer }});
    scene.add(spark);
    const world = new SplatMesh({{ url: './assets/world.ply' }});
    const query = new URLSearchParams(location.search);
    world.rotation.set(
      Number(query.get('rotX') || 0),
      Number(query.get('rotY') || 0),
      Number(query.get('rotZ') || 0)
    );
    const scale = Number(query.get('scale') || 1);
    world.scale.setScalar(scale);
    world.position.set(
      Number(query.get('x') || 0),
      Number(query.get('y') || 0),
      Number(query.get('z') || 0)
    );
    scene.add(world);
    status.textContent = 'Gaussian Splat loaded. Click the view to move.';

    const controls = new PointerLockControls(camera, renderer.domElement);
    renderer.domElement.addEventListener('click', () => {{
      if (!renderer.xr.isPresenting) controls.lock();
    }});
    const keys = new Set();
    addEventListener('keydown', event => keys.add(event.code));
    addEventListener('keyup', event => keys.delete(event.code));
    const clock = new THREE.Clock();
    const forward = new THREE.Vector3();
    const right = new THREE.Vector3();

    function desktopMove(dt) {{
      if (!controls.isLocked || renderer.xr.isPresenting) return;
      camera.getWorldDirection(forward);
      forward.y = 0;
      forward.normalize();
      right.crossVectors(forward, camera.up).normalize();
      const speed = keys.has('ShiftLeft') ? 2.4 : 1.2;
      if (keys.has('KeyW')) rig.position.addScaledVector(forward, speed * dt);
      if (keys.has('KeyS')) rig.position.addScaledVector(forward, -speed * dt);
      if (keys.has('KeyD')) rig.position.addScaledVector(right, speed * dt);
      if (keys.has('KeyA')) rig.position.addScaledVector(right, -speed * dt);
    }}

    function xrMove(dt) {{
      const session = renderer.xr.getSession();
      if (!session) return;
      for (const source of session.inputSources) {{
        const gamepad = source.gamepad;
        if (!gamepad || gamepad.axes.length < 2) continue;
        const x = gamepad.axes.at(-2) || 0;
        const y = gamepad.axes.at(-1) || 0;
        if (Math.abs(x) < .16 && Math.abs(y) < .16) continue;
        camera.getWorldDirection(forward);
        forward.y = 0;
        forward.normalize();
        right.crossVectors(forward, camera.up).normalize();
        rig.position.addScaledVector(forward, -y * dt * 1.2);
        rig.position.addScaledVector(right, x * dt * 1.2);
        break;
      }}
    }}

    renderer.setAnimationLoop(() => {{
      const dt = Math.min(clock.getDelta(), .05);
      desktopMove(dt);
      xrMove(dt);
      renderer.render(scene, camera);
    }});

    addEventListener('resize', () => {{
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
    }});
  </script>
</body>
</html>
"""
    index = output_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    return index


def export_panorama_viewer(panorama_path: Path, output_dir: Path, *, title: str) -> Path:
    assets = output_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    extension = panorama_path.suffix.lower() or ".png"
    asset_name = f"panorama{extension}"
    copy_media(panorama_path, assets / asset_name)
    safe_title = html.escape(title)
    page = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="theme-color" content="#05070b">
  <title>{safe_title} — Panorama fallback</title>
  <style>{_base_css()}</style>
  <script type="importmap">{_IMPORT_MAP}</script>
</head>
<body>
  <div id="hud"><strong>{safe_title}</strong><span id="status">360° panorama fallback</span><br>Drag to look around, or use Enter VR.</div>
  <script type="module">
    import * as THREE from "three";
    import {{ VRButton }} from "three/addons/webxr/VRButton.js";
    import {{ OrbitControls }} from "three/addons/controls/OrbitControls.js";

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(70, innerWidth / innerHeight, 0.01, 1100);
    const renderer = new THREE.WebGLRenderer({{ antialias: true }});
    renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    renderer.setSize(innerWidth, innerHeight);
    renderer.xr.enabled = true;
    document.body.appendChild(renderer.domElement);
    document.body.appendChild(VRButton.createButton(renderer));

    const geometry = new THREE.SphereGeometry(100, 96, 64);
    geometry.scale(-1, 1, 1);
    const texture = await new THREE.TextureLoader().loadAsync('./assets/{asset_name}');
    texture.colorSpace = THREE.SRGBColorSpace;
    const sphere = new THREE.Mesh(geometry, new THREE.MeshBasicMaterial({{ map: texture }}));
    scene.add(sphere);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableZoom = true;
    controls.enablePan = false;
    controls.rotateSpeed = -0.25;
    controls.target.set(0, 0, -1);
    controls.update();

    renderer.setAnimationLoop(() => {{
      controls.enabled = !renderer.xr.isPresenting;
      controls.update();
      renderer.render(scene, camera);
    }});
    addEventListener('resize', () => {{
      camera.aspect = innerWidth / innerHeight;
      camera.updateProjectionMatrix();
      renderer.setSize(innerWidth, innerHeight);
    }});
  </script>
</body>
</html>
"""
    index = output_dir / "index.html"
    index.write_text(page, encoding="utf-8")
    return index
