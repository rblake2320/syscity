# CLAUDE.md — SysCity Project Instructions

## What This Is

SysCity is a suite of self-contained Three.js HTML files, each a cinematic 3D system monitoring visualization. No build step, no npm, no framework. Each file is open-and-run.

## Testing

Always test in a browser before claiming anything works.

Local server is running at `http://localhost:9191/` — files are served from `C:\Users\techai\Downloads\` during development, then copied to this repo and committed.

**Screenshot to verify** using the Chrome MCP tools before reporting done.

## Commands

```bash
# Copy a new scene from Downloads to repo
cp /c/Users/techai/Downloads/system-X.html /c/Users/techai/syscity/system-X.html

# Commit
git -C /c/Users/techai/syscity add system-X.html
git -C /c/Users/techai/syscity commit -m "feat: ..."
git -C /c/Users/techai/syscity push
```

## Scene Template Pattern

All scenes use the same scaffolding:

```javascript
// 1. Seeded RNG
function rng32(s){...}

// 2. SIM telemetry — drifts randomly, lerped each frame
const SIM={cpu:.X,mem:.X,...};
const TGT={...};
setInterval(()=>{ /* drift TGT */ },2000);

// 3. Renderer — always set these
renderer.physicallyCorrectLights=true;
renderer.outputEncoding=THREE.sRGBEncoding;
renderer.toneMapping=THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure=1.1;

// 4. Post-processing
const bloom=new THREE.UnrealBloomPass(new THREE.Vector2(W,H),.75,.38,.72);
// bloom.strength and bloom.threshold update each frame with SIM.cpu

// 5. Environment map via PMREMGenerator (warm or cool scene)

// 6. Animate loop — composer.render(), NOT renderer.render()
```

## Known Three.js r128 Constraints

- `MeshPhysicalMaterial.transmission` — NOT available in r128, use `opacity` instead
- `.position.set(x,y,z)` — use this, NEVER `Object.assign(mesh.position, {x,y,z})`
- `CylinderGeometry(R,R,H,6)` = hex prism (use rotation.y=Math.PI/6 for pointy-top)
- `SphereGeometry(R, segs, segs, 0, PI*2, 0, PI*0.5)` = dome (top hemisphere only)

## CDN URLs (r128 — do not change)

```html
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/EffectComposer.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/RenderPass.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/LuminosityHighPassShader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/shaders/CopyShader.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/ShaderPass.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/postprocessing/UnrealBloomPass.js"></script>
```

## Visual Quality Standards

Every scene must have:
- `physicallyCorrectLights`, `ACESFilmicToneMapping`, `sRGBEncoding`
- `MeshPhysicalMaterial` (not Lambert/Phong) on all primary surfaces
- `clearcoat` where surfaces should look wet/glossy
- `PMREMGenerator` environment map for reflections
- `UnrealBloomPass` with CPU-responsive strength/threshold
- `FogExp2` for atmospheric depth
- Shadows enabled (`renderer.shadowMap.enabled`, `castShadow`, `receiveShadow`)
- No primitive placeholder geometry — always use bevels, rings, or compound shapes
- InstancedMesh for any repeated object with count > 20

## HUD Pattern

Each scene has:
- Top-left: metrics panel (bar charts, live values)
- Bottom-right: event feed (3-5 auto-generated events)
- Bottom-center: title line
- Floating 3D→2D projected labels on key objects

## Adding a New Scene

1. Copy the closest existing scene as a base
2. Change the `rng32` seeds so positions are different
3. Change the material colors and geometry to fit the new theme
4. Remap SIM metrics to theme-specific names (e.g. "NECTAR MEMORY" not "MEMORY")
5. Test in browser — screenshot it — then copy to repo and commit
