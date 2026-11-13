// Interactive level-of-detail viewer for the meshkit results.
// Reads data/manifest.json (written by run_experiments.py) and shows each
// simplified OBJ with three.js. No build step: three.js comes from a CDN.

import * as THREE from 'three';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { mergeVertices } from 'three/addons/utils/BufferGeometryUtils.js';

const $ = (id) => document.getElementById(id);

// ---- headline numbers from results/summary.json --------------------------
fetch('data/summary.json')
  .then((r) => r.json())
  .then((summary) => {
    document.querySelectorAll('[data-num]').forEach((el) => {
      const value = summary.headline[el.dataset.num];
      el.textContent = typeof value === 'number' ? value.toLocaleString('en') : value;
    });
  })
  .catch(() => { $('headline').hidden = true; });

// ---- before / after divider ------------------------------------------------
const compareRange = $('compare-range');
function moveDivider() {
  const pct = compareRange.value;
  $('compare-top').style.clipPath = `inset(0 ${100 - pct}% 0 0)`;  // show the left part of the top image
  $('compare-divider').style.left = `${pct}%`;
}
compareRange.addEventListener('input', moveDivider);
moveDivider();

// ---- three.js scene ---------------------------------------------------------
const container = $('viewer');
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
container.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf6f5f2);
const camera = new THREE.PerspectiveCamera(35, 16 / 10, 0.01, 100);
camera.position.set(0, 0.3, 3.2);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.autoRotate = true;
controls.autoRotateSpeed = 1.5;

scene.add(new THREE.HemisphereLight(0xffffff, 0x8a7f72, 1.6));
const sun = new THREE.DirectionalLight(0xffffff, 2.2);
sun.position.set(-2, 3, 4);
camera.add(sun);              // the light moves with the camera, so the lit side is always visible
scene.add(camera);

const clay = new THREE.MeshStandardMaterial({ color: 0xc89f73, roughness: 0.8, metalness: 0.0, flatShading: true });
const wireMaterial = new THREE.LineBasicMaterial({ color: 0x2b2b2b, transparent: true, opacity: 0.35 });
const holder = new THREE.Group();
scene.add(holder);

function resize() {
  const w = container.clientWidth;
  const h = container.clientHeight;
  renderer.setSize(w, h, false);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resize).observe(container);

renderer.setAnimationLoop(() => {
  controls.update();
  renderer.render(scene, camera);
});

// ---- loading OBJ files (cached, so slider moves are instant the 2nd time) ---
const loader = new OBJLoader();
const cache = new Map();                 // file -> Promise<BufferGeometry>
const frames = new Map();                // model name -> {centre, scale}, from the first level loaded

function loadGeometry(file) {
  if (!cache.has(file)) {
    cache.set(file, loader.loadAsync(file).then((group) => {
      let geometry = null;
      group.traverse((child) => { if (child.isMesh && !geometry) geometry = child.geometry; });
      // Drop normals/UVs so vertices shared by several faces can be merged,
      // then compute smooth normals (flat shading ignores them).
      geometry.deleteAttribute('normal');
      geometry.deleteAttribute('uv');
      geometry = mergeVertices(geometry);
      geometry.computeVertexNormals();
      return geometry;
    }));
  }
  return cache.get(file);
}

// ---- UI state -----------------------------------------------------------------
let manifest = null;
let current = null;                       // the model entry from the manifest
let request = 0;                          // ignore results of slider moves that were overtaken

function showStats(level) {
  $('lod-label').textContent = level.label;
  $('s-tris').textContent = level.triangles.toLocaleString('en');
  $('s-kb').textContent = `${level.kb.toLocaleString('en')} KB`;
  $('s-err').textContent = level.kept_pct === 100 ? '0 (original)' : `${level.mean_error_pct}%`;
  $('s-pct').textContent = `${level.kept_pct}% of the triangles`;
}

async function showLevel(index) {
  const level = current.levels[index];
  const mine = ++request;
  showStats(level);
  $('loading').hidden = false;
  const geometry = await loadGeometry(level.file);
  if (mine !== request) return;         // a newer slider position is already loading
  $('loading').hidden = true;

  // Frame every level of a model the same way, so only the detail changes.
  if (!frames.has(current.name)) {
    geometry.computeBoundingBox();
    const box = geometry.boundingBox;
    const centre = box.getCenter(new THREE.Vector3());
    const scale = 2 / box.getSize(new THREE.Vector3()).length();
    frames.set(current.name, { centre, scale });
  }
  const { centre, scale } = frames.get(current.name);

  holder.clear();
  const mesh = new THREE.Mesh(geometry, clay);
  const wire = new THREE.LineSegments(new THREE.WireframeGeometry(geometry), wireMaterial);
  wire.visible = $('wire').checked;
  for (const object of [mesh, wire]) {
    object.position.copy(centre).multiplyScalar(-scale);
    object.scale.setScalar(scale);
    holder.add(object);
  }
}

function selectModel(name) {
  current = manifest.models.find((m) => m.name === name);
  const slider = $('lod');
  slider.max = current.levels.length - 1;
  // Start at the 2% level if there is one: small file, loads quickly.
  const start = current.levels.findIndex((l) => l.kept_pct === 2);
  slider.value = start >= 0 ? start : 0;
  showLevel(Number(slider.value));
}

$('lod').addEventListener('input', (e) => showLevel(Number(e.target.value)));
$('model').addEventListener('change', (e) => selectModel(e.target.value));
$('wire').addEventListener('change', (e) => {
  holder.children.forEach((child) => { if (child.isLineSegments) child.visible = e.target.checked; });
});
$('smooth').addEventListener('change', (e) => {
  clay.flatShading = !e.target.checked;
  clay.needsUpdate = true;              // flatShading changes the shader, so it must be rebuilt
});
$('spin').addEventListener('change', (e) => { controls.autoRotate = e.target.checked; });

fetch('data/manifest.json')
  .then((r) => r.json())
  .then((data) => {
    manifest = data;
    for (const model of manifest.models) {
      const option = document.createElement('option');
      option.value = option.textContent = model.name;
      $('model').appendChild(option);
    }
    selectModel(manifest.models[0].name);
  })
  .catch((err) => { $('loading').textContent = `could not load the model list (${err.message})`; });
