# SysCity — Live 3D System Intelligence Visualizations

A suite of cinematic, real-time 3D system monitoring scenes built with Three.js. Each scene maps live (simulated) system telemetry — CPU, memory, disk, network, queue — onto a unique biological or environmental metaphor.

## Scenes

| File | Theme | Key Features |
|------|-------|--------------|
| `system-city.html` | Cyberpunk city | Buildings = processes, traffic = network I/O |
| `system-space.html` | Solar system | Kepler orbits, satellites, ISS-style station, alien UFOs |
| `system-ocean.html` | Ocean surface | Gerstner waves, ships, lighthouse, storm system, day/night cycle |
| `system-underwater.html` | Deep ocean | Boid fish schools, jellyfish, sharks, manta rays, coral, god rays |
| `system-hive.html` | Bee hive colony | Hex cells, worker bees, queen tower, amber data flow tubes |
| `system-ants.html` | Ant colony network | Overhead map, 8 typed chambers, pheromone trails, glossy ants |

## Running

Any local HTTP server works. With Python:
```bash
python -m http.server 9191
# open http://localhost:9191/system-hive.html
```

Or open the HTML files directly in Chrome (some scenes need a server for CDN scripts).

## Tech Stack

- **Three.js r128** (CDN) — WebGL renderer
- **ACESFilmicToneMapping** + `sRGBEncoding` — color management on all scenes
- **physicallyCorrectLights = true** — PBR-accurate lighting
- **MeshPhysicalMaterial** — clearcoat, metalness, roughness, env map on all surfaces
- **PMREMGenerator** — procedural environment maps for reflections
- **UnrealBloomPass** — bloom strength/threshold responds to CPU load
- **InstancedMesh** — single draw call for fish schools, bee swarms, ant colonies
- **ShaderMaterial** — custom GLSL for data flow tubes (scrolling pulse effect), ocean waves
- **CatmullRomCurve3 + TubeGeometry** — smooth data path tubes

## Blender

`syscity_hive_blender.py` — Python script for Blender 5.1 that builds a cinematic bee hive scene with:
- PBR materials, volumetric atmosphere, Cycles render
- HDRI lighting + compositor bloom node
- Exports `hive.glb` + `hive_preview.png`

Run:
```
"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" --background --python syscity_hive_blender.py -- --demo --output hive.glb --render hive_preview.png
```

## Architecture Notes

Each HTML scene is self-contained (single file, no build step). They share a common pattern:
- Seeded RNG (`rng32`) for deterministic procedural geometry
- Simulated telemetry (`SIM` object) that drifts randomly with `setInterval`
- Smooth lerp toward target values each frame
- CSS overlay HUD with live bar charts + event feed
- Floating 3D→2D projected labels via `vector.project(camera)`
- Slow cinematic camera orbit that responds to system state
