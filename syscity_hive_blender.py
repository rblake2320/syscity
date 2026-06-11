"""
syscity_hive_blender.py — Bee Hive System Monitor
Blender 5.1 Python scene generator.

Usage:
  blender.exe --background --python syscity_hive_blender.py -- --demo
  blender.exe --background --python syscity_hive_blender.py -- \
      --data syscity_data.json --output hive.glb --render hive_preview.png

Scene concept:
  THE HIVE = your computer
  Honeycomb cells = processes  (height=RAM, glow=CPU)
  Queen cell = CPU/system core (pulses with overall load)
  Flying bees = network packets (cyan=download, magenta=upload)
  Honey fill = memory usage
  Deep amber chambers = disk partitions
  Underground tunnels = I/O paths
"""

import bpy, bmesh, math, json, sys, os, random, argparse
from mathutils import Vector, Matrix, Euler

# ── CLI args ──────────────────────────────────────────────────────────────────
def get_args():
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    else:
        argv = []
    p = argparse.ArgumentParser()
    p.add_argument("--data",    default="", help="Path to syscity_data.json")
    p.add_argument("--output",  default="hive.glb")
    p.add_argument("--render",  default="hive_preview.png")
    p.add_argument("--demo",    action="store_true")
    return p.parse_args(argv)

ARGS = get_args()

DEMO_DATA = {
    "cpu": {"usage_pct": 38, "count_logical": 24},
    "memory": {"used_gb": 41.2, "total_gb": 128, "pct": 32},
    "disks": [{"mount": "C:\\", "used_gb": 890, "total_gb": 2000, "pct": 44},
              {"mount": "D:\\", "used_gb": 1430, "total_gb": 4000, "pct": 35}],
    "net_mbps": 1.4,
    "gpu": [{"name": "RTX 5090", "util_pct": 12, "mem_used_mb": 4200,
             "mem_total_mb": 32768, "temp_c": 48}],
    "processes": [
        {"name": "ollama.exe", "cpu": 8.2, "mem_mb": 2142},
        {"name": "chrome.exe", "cpu": 11.1, "mem_mb": 984},
        {"name": "Code.exe", "cpu": 5.3, "mem_mb": 652},
        {"name": "blender.exe", "cpu": 14.0, "mem_mb": 1830},
        {"name": "python.exe", "cpu": 9.1, "mem_mb": 520},
        {"name": "postgres.exe", "cpu": 2.1, "mem_mb": 310},
        {"name": "redis-server", "cpu": 0.8, "mem_mb": 88},
        {"name": "cargo.exe", "cpu": 18.3, "mem_mb": 420},
        {"name": "dwm.exe", "cpu": 1.9, "mem_mb": 95},
        {"name": "claude.exe", "cpu": 4.2, "mem_mb": 215},
        {"name": "explorer.exe", "cpu": 1.1, "mem_mb": 140},
        {"name": "svchost.exe", "cpu": 0.4, "mem_mb": 72},
    ]
}

if ARGS.demo or not ARGS.data:
    DATA = DEMO_DATA
else:
    with open(ARGS.data) as f:
        DATA = json.load(f)

# ── Helpers ───────────────────────────────────────────────────────────────────
def purge_scene():
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in list(bpy.data.meshes) + list(bpy.data.materials) + \
                 list(bpy.data.lights) + list(bpy.data.cameras) + \
                 list(bpy.data.curves):
        block.user_clear()
        try: bpy.data.meshes.remove(block)
        except: pass
    bpy.ops.outliner.orphans_purge(do_recursive=True)

def new_mat(name, base=(1,1,1,1), roughness=.5, metallic=0,
            emission=None, emit_strength=0, alpha=1,
            subsurface=0, ssrad=(1,.3,.1)):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nodes = m.node_tree.nodes; links = m.node_tree.links
    for n in list(nodes): nodes.remove(n)

    out = nodes.new('ShaderNodeOutputMaterial')
    pbsdf = nodes.new('ShaderNodeBsdfPrincipled')
    pbsdf.location = (-200, 0)

    # Base Color
    pbsdf.inputs['Base Color'].default_value = base

    # Roughness
    try: pbsdf.inputs['Roughness'].default_value = roughness
    except: pass

    # Metallic
    try: pbsdf.inputs['Metallic'].default_value = metallic
    except: pass

    # Emission
    if emission:
        for k in ('Emission Color', 'Emission'):
            try: pbsdf.inputs[k].default_value = (*emission, 1); break
            except: pass
        for k in ('Emission Strength',):
            try: pbsdf.inputs[k].default_value = emit_strength; break
            except: pass

    # Subsurface (skin/wax effect)
    if subsurface > 0:
        for k in ('Subsurface Weight', 'Subsurface'):
            try: pbsdf.inputs[k].default_value = subsurface; break
            except: pass
        for k in ('Subsurface Radius',):
            try: pbsdf.inputs[k].default_value = ssrad; break
            except: pass

    # Alpha
    if alpha < 1:
        try: pbsdf.inputs['Alpha'].default_value = alpha
        except: pass
        try: m.blend_method = 'BLEND'
        except: pass
        try: m.shadow_method = 'CLIP'  # removed in Blender 5+
        except: pass

    links.new(pbsdf.outputs['BSDF'], out.inputs['Surface'])
    return m


def new_stripe_mat(name, col_a, col_b, scale=8.0, roughness=.4, subsurface=.08):
    """Procedural stripe material via Wave texture — good for bee abdomen."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nodes = m.node_tree.nodes; links = m.node_tree.links
    for n in list(nodes): nodes.remove(n)

    out = nodes.new('ShaderNodeOutputMaterial'); out.location = (400, 0)
    pbsdf = nodes.new('ShaderNodeBsdfPrincipled'); pbsdf.location = (200, 0)
    ramp = nodes.new('ShaderNodeValToRGB'); ramp.location = (-80, 0)
    wave = nodes.new('ShaderNodeTexWave'); wave.location = (-320, 0)
    coord = nodes.new('ShaderNodeTexCoord'); coord.location = (-520, 0)

    wave.wave_type = 'BANDS'
    wave.inputs['Scale'].default_value = scale
    wave.inputs['Distortion'].default_value = 1.2
    wave.inputs['Detail'].default_value = 4
    wave.inputs['Detail Scale'].default_value = 2

    ramp.color_ramp.elements[0].position = 0.0
    ramp.color_ramp.elements[0].color = (*col_a, 1)
    ramp.color_ramp.elements[1].position = 1.0
    ramp.color_ramp.elements[1].color = (*col_b, 1)

    pbsdf.inputs['Roughness'].default_value = roughness
    if subsurface > 0:
        for k in ('Subsurface Weight', 'Subsurface'):
            try: pbsdf.inputs[k].default_value = subsurface; break
            except: pass
        try: pbsdf.inputs['Subsurface Radius'].default_value = (.8, .35, .1)
        except: pass

    links.new(coord.outputs['Object'], wave.inputs['Vector'])
    links.new(wave.outputs['Color'], ramp.inputs['Fac'])
    links.new(ramp.outputs['Color'], pbsdf.inputs['Base Color'])
    links.new(pbsdf.outputs['BSDF'], out.inputs['Surface'])
    return m


def link_mat(obj, mat):
    if obj.data.materials:
        obj.data.materials[0] = mat
    else:
        obj.data.materials.append(mat)


# ── Hexagonal cell builder ────────────────────────────────────────────────────
HEX_R = 1.0      # hex outer radius
HEX_W = math.sqrt(3) * HEX_R   # hex width (flat-to-flat * sqrt3)
HEX_H = 2 * HEX_R               # hex height

def hex_grid_pos(col, row):
    """Return XY center of hex cell at (col, row) in a pointy-top layout."""
    x = col * HEX_W + (row % 2) * (HEX_W / 2)
    y = row * HEX_R * 1.5
    return x, y


def build_hex_cell(cx, cy, depth, honey_frac, cpu_frac, proc_name, mat_wall, mat_honey):
    """Create one honeycomb cell: outer wax wall + inner honey fill."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=HEX_R - 0.06,
                                        depth=depth, location=(cx, cy, depth / 2))
    wall = bpy.context.active_object
    wall.name = f"Cell_{proc_name}"
    link_mat(wall, mat_wall)
    wall.data.materials.append(mat_wall)

    # Bevel the top edges for a carved-wax look
    bpy.ops.object.modifier_add(type='BEVEL')
    bvl = wall.modifiers[-1]   # grab whatever name Blender assigned
    bvl.width = 0.055; bvl.segments = 2
    bpy.ops.object.modifier_apply(modifier=bvl.name)

    # Honey fill (scaled sub-cylinder inside)
    honey_h = max(depth * honey_frac, 0.05)
    bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=HEX_R * 0.78,
                                        depth=honey_h,
                                        location=(cx, cy, honey_h / 2 + 0.04))
    honey = bpy.context.active_object
    honey.name = f"Honey_{proc_name}"
    link_mat(honey, mat_honey)

    # CPU glow intensity stored in custom property so Three.js can read it
    honey['cpu_frac'] = cpu_frac
    honey['proc_name'] = proc_name

    return wall, honey


# ── Bee body builder ──────────────────────────────────────────────────────────
def build_bee(location=(0, 0, 5), scale=1.0, name="Bee"):
    """Stylised bee: abdomen + thorax + head + wings + legs + antennae."""
    bpy.ops.object.empty_add(location=location)
    root = bpy.context.active_object
    root.name = name

    stripe_mat  = new_stripe_mat(f"{name}_Stripe",
                                  col_a=(.04,.02,.01), col_b=(1.0,.65,.05),
                                  scale=9, roughness=.38, subsurface=.06)
    wing_mat    = new_mat(f"{name}_Wing",  base=(.85,.92,1,1), roughness=.02,
                          alpha=.28, subsurface=0)
    leg_mat     = new_mat(f"{name}_Leg",   base=(.08,.05,.02,1), roughness=.55)
    eye_mat     = new_mat(f"{name}_Eye",   base=(.05,.3,.05,1),
                          roughness=.05, emission=(.05,.5,.05),
                          emit_strength=.8)
    stinger_mat = new_mat(f"{name}_Stng",  base=(.12,.09,.04,1), roughness=.35)

    parts = []

    def add_sphere(r, loc, scl=(1,1,1), mat=None, nm=""):
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=18,
                                              radius=r, location=loc)
        o = bpy.context.active_object
        o.name = f"{name}_{nm}"
        o.scale = scl
        bpy.ops.object.transform_apply(scale=True)
        o.parent = root
        if mat: link_mat(o, mat)
        parts.append(o)
        return o

    def add_cyl(r, h, loc, rot=(0,0,0), mat=None, nm=""):
        bpy.ops.mesh.primitive_cylinder_add(vertices=10, radius=r, depth=h,
                                             location=loc, rotation=rot)
        o = bpy.context.active_object
        o.name = f"{name}_{nm}"
        o.parent = root
        if mat: link_mat(o, mat)
        parts.append(o)
        return o

    # Abdomen — striped, oval
    abd = add_sphere(.42, (0, .55, 0), scl=(.82,1.0,.65), mat=stripe_mat, nm="Abdomen")
    # Thorax
    tho = add_sphere(.26, (0, .05, 0), scl=(.9,.85,.82), mat=stripe_mat, nm="Thorax")
    # Head
    hd = add_sphere(.20, (0, -.28, 0), scl=(1,.92,.9),   mat=stripe_mat, nm="Head")
    # Stinger
    add_cyl(.03, .25, (0, .92, -.06), rot=(math.pi/2,0,0), mat=stinger_mat, nm="Stinger")

    # Compound eyes
    for s in (-1, 1):
        add_sphere(.08, (s*.14, -.36, .04), mat=eye_mat, nm=f"Eye{'+' if s>0 else '-'}")

    # Wings — 4 flat planes (front pair larger)
    for i, (wx, wy, wz, sx, sy) in enumerate([
            (-.48, -.05, .1, .9, 1.6),   # front-left
            ( .48, -.05, .1, .9, 1.6),   # front-right
            (-.38,  .15, .08, .7, 1.1),  # hind-left
            ( .38,  .15, .08, .7, 1.1),  # hind-right
    ]):
        bpy.ops.mesh.primitive_plane_add(size=.5, location=(wx, wy, wz))
        w = bpy.context.active_object
        w.name = f"{name}_Wing{i}"
        w.scale = (sx, sy, 1)
        angle = math.radians(25 if wx < 0 else -25)
        w.rotation_euler = (math.radians(-15), angle, 0)
        bpy.ops.object.transform_apply(scale=True, rotation=True)
        w.parent = root
        link_mat(w, wing_mat)
        parts.append(w)

    # Legs — 6 (3 per side), bent cylinders approx
    leg_positions = [
        (-.25, -.05, -.08), ( .25, -.05, -.08),
        (-.27,  .10, -.10), ( .27,  .10, -.10),
        (-.24,  .28, -.10), ( .24,  .28, -.10),
    ]
    for j, (lx, ly, lz) in enumerate(leg_positions):
        side = -1 if lx < 0 else 1
        add_cyl(.025, .38, (lx, ly, lz),
                rot=(math.radians(40), 0, math.radians(side*55)),
                mat=leg_mat, nm=f"Leg{j}")
        # Lower leg segment
        add_cyl(.018, .28, (lx + side*.12, ly + .05, lz - .22),
                rot=(math.radians(80), 0, math.radians(side*30)),
                mat=leg_mat, nm=f"LegB{j}")

    # Antennae
    for s in (-1, 1):
        add_cyl(.018, .32, (s*.08, -.44, .12),
                rot=(math.radians(-45), 0, math.radians(s*20)),
                mat=leg_mat, nm=f"Ant{'+' if s>0 else '-'}")
        add_sphere(.04, (s*.16, -.62, .28), mat=eye_mat, nm=f"AntTip{'+' if s>0 else '-'}")

    # Scale entire bee
    root.scale = (scale, scale, scale)
    bpy.ops.object.select_all(action='DESELECT')

    return root


# ── Queen cell ────────────────────────────────────────────────────────────────
def build_queen_cell(cpu_pct, mem_pct):
    """Large central peanut-shaped queen cell with royal jelly glow."""
    # Outer casing (elongated cylinder, ribbed)
    bpy.ops.mesh.primitive_cylinder_add(vertices=8, radius=2.2, depth=5.5,
                                         location=(0, 0, 0))
    qc = bpy.context.active_object; qc.name = "QueenCell"
    # Ribbed look via subdivision + wave displacement
    bpy.ops.object.modifier_add(type='SUBSURF')
    sub = qc.modifiers[-1]; sub.levels = 3
    bpy.ops.object.modifier_add(type='DISPLACE')
    tex = bpy.data.textures.new("QueenRibs", type='WOOD')  # WAVES removed in 5.x
    tex.noise_scale = 1.8
    disp = qc.modifiers[-1]; disp.texture = tex; disp.strength = 0.18

    glow = (1.0, .55, .0)
    qc_mat = new_mat("QueenCellMat", base=(.65,.38,.08,1), roughness=.28,
                     emission=glow, emit_strength=2.5 * (cpu_pct/100 + .4),
                     subsurface=.15, ssrad=(.9,.4,.05))
    link_mat(qc, qc_mat)

    # Royal jelly fill
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=1.6,
                                         depth=3.5 * mem_pct,
                                         location=(0, 0, -2.75 + 3.5 * mem_pct / 2))
    jelly = bpy.context.active_object; jelly.name = "RoyalJelly"
    glow_j = (.9, .85, .15)
    link_mat(jelly, new_mat("JellyMat", base=(.95,.88,.25,1), roughness=.05,
                             emission=glow_j, emit_strength=3.5,
                             alpha=.72))

    # Point light inside
    bpy.ops.object.light_add(type='POINT', location=(0, 0, 1.5))
    lgt = bpy.context.active_object; lgt.name = "QueenLight"
    lgt.data.energy = 400 * (cpu_pct / 40 + .5)
    lgt.data.color = (1.0, .7, .2)
    lgt.data.shadow_soft_size = 1.5

    return qc, jelly


# ── Honeycomb wall ────────────────────────────────────────────────────────────
def build_honeycomb(procs, mem_total_gb):
    COLS, ROWS = 7, 5
    wax_col   = (.72, .45, .08, 1)
    honey_col = (.95, .65, .08, 1)

    mat_wax   = new_mat("WaxMat", base=wax_col, roughness=.45,
                         emission=(.6,.35,.05), emit_strength=.35,
                         subsurface=.12, ssrad=(.9,.45,.08))
    mat_honey = new_mat("HoneyMat", base=honey_col, roughness=.06,
                         emission=(.98,.62,.08), emit_strength=1.2,
                         subsurface=.25, ssrad=(1,.5,.08), alpha=.82)

    procs_sorted = sorted(procs, key=lambda p: p.get('mem_mb', 0), reverse=True)
    cell_idx = 0

    for row in range(ROWS):
        for col in range(COLS):
            cx, cy = hex_grid_pos(col, row)
            # Center the grid
            cx -= HEX_W * (COLS - 1) / 2
            cy -= HEX_R * 1.5 * (ROWS - 1) / 2

            if cell_idx < len(procs_sorted):
                p = procs_sorted[cell_idx]
                mem_frac = clamp(p.get('mem_mb', 100) / (mem_total_gb * 1024), 0, 1)
                cpu_frac = clamp(p.get('cpu', 0) / 40, 0, 1)
                pname = p.get('name', f'proc{cell_idx}')
            else:
                mem_frac = random.uniform(.1, .5)
                cpu_frac = random.uniform(0, .15)
                pname = f"idle_{cell_idx}"

            depth = 2.2 + cpu_frac * 1.8   # taller cell = more CPU active
            build_hex_cell(cx, cy, depth, mem_frac, cpu_frac, pname, mat_wax, mat_honey)
            cell_idx += 1


# ── Background hive wall ──────────────────────────────────────────────────────
def build_hive_backdrop():
    """Curved honeycomb shell behind the scene."""
    bpy.ops.mesh.primitive_cylinder_add(vertices=64, radius=22, depth=28,
                                         location=(0, 0, 4))
    shell = bpy.context.active_object; shell.name = "HiveShell"
    shell.scale.x = 1.8   # widen into an oval chamber
    bpy.ops.object.transform_apply(scale=True)

    bm = bmesh.new()
    bm.from_mesh(shell.data)
    # Keep only the curved inner wall (delete top/bottom caps)
    to_del = [f for f in bm.faces if abs(f.normal.z) > .85]
    bmesh.ops.delete(bm, geom=to_del, context='FACES')
    bm.to_mesh(shell.data); bm.free()

    mat = new_mat("ShellMat", base=(.45,.25,.04,1), roughness=.65,
                   emission=(.4,.22,.04), emit_strength=.18,
                   subsurface=.08, ssrad=(.7,.35,.05))
    link_mat(shell, mat)
    shell.data.flip_normals()   # face inward


# ── Bees in flight ────────────────────────────────────────────────────────────
def build_scout_bees(net_mbps, building_active):
    """A few bees flying through the hive representing network/build activity."""
    bee_count = max(1, min(6, int(net_mbps * 2 + (3 if building_active else 0))))
    rng = random.Random(42)
    for i in range(bee_count):
        x = rng.uniform(-8, 8)
        y = rng.uniform(-8, 8)
        z = rng.uniform(2, 8)
        angle = rng.uniform(0, math.pi * 2)
        s = rng.uniform(.28, .42)
        bee = build_bee(location=(x, y, z), scale=s, name=f"Scout_{i}")
        bee.rotation_euler = (math.radians(-30), 0, angle)


# ── Ground queen bee ──────────────────────────────────────────────────────────
def build_queen_bee(location=(0, 0, -1.5)):
    """Larger queen bee sitting in the queen cell."""
    q = build_bee(location=location, scale=0.7, name="Queen")
    q.rotation_euler = (math.radians(90), 0, 0)


# ── Lighting ──────────────────────────────────────────────────────────────────
def setup_lighting():
    # Warm overhead area light (amber hive glow)
    bpy.ops.object.light_add(type='AREA', location=(0, -4, 14))
    key = bpy.context.active_object; key.name = "KeyLight"
    key.data.energy = 1200; key.data.size = 8
    key.data.color = (1.0, .72, .30)
    key.rotation_euler = (math.radians(25), 0, 0)

    # Cool blue fill from front
    bpy.ops.object.light_add(type='AREA', location=(0, -18, 6))
    fill = bpy.context.active_object; fill.name = "FillLight"
    fill.data.energy = 300; fill.data.size = 12
    fill.data.color = (.3, .5, 1.0)
    fill.rotation_euler = (math.radians(-20), 0, 0)

    # Rim light behind for edge glow on wax
    bpy.ops.object.light_add(type='SPOT', location=(8, 10, 8))
    rim = bpy.context.active_object; rim.name = "RimLight"
    rim.data.energy = 800; rim.data.spot_size = math.radians(50)
    rim.data.color = (1.0, .85, .5)
    rim.rotation_euler = (math.radians(-45), math.radians(35), 0)


# ── World (volumetric haze) ───────────────────────────────────────────────────
def setup_world():
    world = bpy.context.scene.world
    world.use_nodes = True
    nodes = world.node_tree.nodes; links = world.node_tree.links
    for n in list(nodes): nodes.remove(n)

    bg = nodes.new('ShaderNodeBackground'); bg.location = (0, 100)
    bg.inputs['Color'].default_value = (.06, .03, .01, 1)
    bg.inputs['Strength'].default_value = .4

    vol = nodes.new('ShaderNodeVolumePrincipled'); vol.location = (0, -100)
    vol.inputs['Color'].default_value = (.98, .72, .28, 1)
    vol.inputs['Density'].default_value = .004
    vol.inputs['Emission Color'].default_value = (.9, .55, .1, 1)
    vol.inputs['Emission Strength'].default_value = .08

    out = nodes.new('ShaderNodeOutputWorld'); out.location = (250, 0)
    links.new(bg.outputs['Background'], out.inputs['Surface'])
    links.new(vol.outputs['Volume'], out.inputs['Volume'])


# ── Camera ────────────────────────────────────────────────────────────────────
def setup_camera():
    bpy.ops.object.camera_add(location=(14, -18, 10))
    cam = bpy.context.active_object; cam.name = "Camera"
    cam.rotation_euler = (math.radians(62), 0, math.radians(38))
    cam.data.lens = 28          # wide-ish for drama
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = 22
    cam.data.dof.aperture_fstop = 2.2
    bpy.context.scene.camera = cam


# ── Render setup ─────────────────────────────────────────────────────────────
def setup_render(w=1920, h=1080):
    # In Blender 4.2+ the engine is still 'BLENDER_EEVEE' — EEVEE Next is the default
    bpy.context.scene.render.engine = 'BLENDER_EEVEE'
    bpy.context.scene.render.resolution_x = w
    bpy.context.scene.render.resolution_y = h
    bpy.context.scene.render.film_transparent = False

    eevee = bpy.context.scene.eevee
    for attr, val in [
        ('use_gtao', True), ('gtao_distance', 0.6),
        ('use_ssr', True), ('ssr_quality', 1.0),
        ('use_bloom', True), ('bloom_intensity', 0.08),
        ('volumetric_start', 0.1), ('volumetric_end', 60),
        ('volumetric_samples', 48),
    ]:
        try: setattr(eevee, attr, val)
        except: pass


# ── Compositor bloom ─────────────────────────────────────────────────────────
def setup_compositor():
    scene = bpy.context.scene
    # Blender 5.1: compositor uses compositing_node_group, not scene.node_tree
    try:
        scene.use_nodes = True  # deprecated in 5.x but still triggers creation
    except: pass

    tree = getattr(scene, 'compositing_node_group', None) or getattr(scene, 'node_tree', None)
    if not tree:
        print("[hive] compositor tree unavailable — skipping bloom node")
        return

    nodes = tree.nodes; links = tree.links
    for n in list(nodes): nodes.remove(n)

    rl  = nodes.new('CompositorNodeRLayers'); rl.location  = (-300, 0)
    out = nodes.new('CompositorNodeComposite'); out.location = (400, 0)

    try:
        glare = nodes.new('CompositorNodeGlare'); glare.location = (100, 0)
        glare.glare_type = 'BLOOM'; glare.threshold = 0.55
        glare.size = 7; glare.quality = 'HIGH'
        links.new(rl.outputs['Image'], glare.inputs['Image'])
        links.new(glare.outputs['Image'], out.inputs['Image'])
    except:
        links.new(rl.outputs['Image'], out.inputs['Image'])


# ── Utils ─────────────────────────────────────────────────────────────────────
def clamp(v, lo, hi): return max(lo, min(hi, v))


def export_glb(path):
    bpy.ops.export_scene.gltf(
        filepath=path,
        export_format='GLB',
        export_apply=True,
        export_materials='EXPORT',
        export_lights=True,
        export_cameras=True,
        export_animations=False,
    )
    print(f"[hive] GLB exported → {path}")


def render_preview(path):
    bpy.context.scene.render.filepath = path
    bpy.context.scene.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True)
    print(f"[hive] Render → {path}")


# ── Main ──────────────────────────────────────────────────────────────────────
def build_hive(data, glb_out, render_out):
    purge_scene()

    cpu_pct    = data['cpu']['usage_pct']
    mem_pct    = data['memory']['pct'] / 100
    mem_total  = data['memory']['total_gb']
    net_mbps   = data.get('net_mbps', 0)
    building   = any(p.get('name','').lower() in ('cargo.exe','make','cmake','gcc')
                     for p in data.get('processes', []))
    procs      = data.get('processes', [])

    setup_render()
    setup_world()

    # Scene elements
    build_hive_backdrop()
    build_honeycomb(procs, mem_total)
    build_queen_cell(cpu_pct, mem_pct)
    build_queen_bee(location=(0, 0, 1.2))
    build_scout_bees(net_mbps, building)
    setup_lighting()
    setup_camera()
    setup_compositor()

    print(f"[hive] Scene built — {len(bpy.data.objects)} objects")
    export_glb(glb_out)
    if render_out:
        render_preview(render_out)


build_hive(DATA, ARGS.output, ARGS.render)
