# AGENTS.md — SysCity AI Agent Instructions

## Purpose

This repo contains cinematic 3D system monitoring visualizations (Three.js HTML files). When working on this project, agents should produce premium, visually impressive results — not demos or placeholders.

## Quality Bar

Before shipping any scene:
- Take a screenshot in the browser and visually confirm it renders
- Confirm no JS errors in the console
- The scene must look premium — not low-poly, not 1980s, not placeholder geometry
- Every object must have PBR materials (MeshPhysicalMaterial), proper lighting, and shadows

## Visual Requirements Per Scene

| Requirement | Minimum |
|-------------|---------|
| Tone mapping | ACESFilmicToneMapping |
| Color space | sRGBEncoding |
| Lights | physicallyCorrectLights = true |
| Surfaces | MeshPhysicalMaterial with roughness/metalness set intentionally |
| Shiny surfaces | clearcoat ≥ 0.5 |
| Environment | PMREMGenerator env map for reflections |
| Bloom | UnrealBloomPass, responds to SIM.cpu |
| Atmosphere | FogExp2 |
| Shadows | PCFSoftShadowMap |
| Repeated objects | InstancedMesh |

## Geometry Standards

- No flat BoxGeometry or PlaneGeometry as hero objects without modification
- Cylinders: use CylinderGeometry with enough sides (≥ 8 for structures, 6 for hex)
- Bevels: add TorusGeometry rings or CylinderGeometry collar pieces to break geometry
- Organic objects: SphereGeometry with appropriate segment counts (≥ 12×10 for heroes)
- Tubes: TubeGeometry along CatmullRomCurve3 (not LineSegments)

## Data Flow Tubes

Use ShaderMaterial with scrolling UV for animated data paths:
```glsl
// fragment
float flow = fract(vU * N - uTime * speed);
float pulse = smoothstep(0.0, 0.3, flow) * smoothstep(0.8, 0.3, flow);
gl_FragColor = vec4(uColor * pulse * 3.5, pulse * 0.9 + 0.08);
```
Always use `blending: THREE.AdditiveBlending` and `depthWrite: false`.

## InstancedMesh Pattern

```javascript
const mesh = new THREE.InstancedMesh(geo, mat, COUNT);
mesh.frustumCulled = false;
const dummy = new THREE.Object3D();
// In animate():
dummy.position.set(x, y, z);
dummy.quaternion.setFromUnitVectors(forward, direction);
dummy.scale.setScalar(s);
dummy.updateMatrix();
mesh.setMatrixAt(i, dummy.matrix);
mesh.instanceMatrix.needsUpdate = true;
```

## Testing Protocol

1. Navigate browser to `http://localhost:9191/<filename>.html`
2. Wait 3-4 seconds for Three.js CDN scripts to load
3. Take screenshot — if black screen, check console for syntax errors
4. If scene renders but looks wrong: fix geometry orientation (PlaneGeometry defaults to XY, rotate X -PI/2 for floor), fix material transparency (depthWrite:false on transparent objects), fix camera angle
5. Only report done after screenshot confirms correct render

## File Organization

- Development: `C:\Users\techai\Downloads\`
- Repo: `C:\Users\techai\syscity\`
- Copy with: `cp /c/Users/techai/Downloads/system-X.html /c/Users/techai/syscity/system-X.html`
- Commit with: `git -C /c/Users/techai/syscity ...`

## Common Bugs

| Bug | Fix |
|-----|-----|
| Black screen | JS syntax error — check console; usually a stray character or undefined variable |
| Floor is vertical | PlaneGeometry lies in XY by default — `geo.rotateX(-Math.PI/2)` |
| Transparent objects Z-fight | Set `depthWrite: false` on all transparent materials |
| Object.assign on position throws | Use `.position.set(x,y,z)` instead |
| Camera sees nothing | `camera.lookAt(target)` must be called every frame if camera moves |
| Bloom too bright/dark | Tune `bloom.threshold` (higher = less bloom) and `bloom.strength` |
