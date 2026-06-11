#!/usr/bin/env python3
"""
syscity_blender.py  —  Procedural data-city generator for Blender 5.1
======================================================================
CLI (batch render / GLB export):
  "C:\Program Files\Blender Foundation\Blender 5.1\blender.exe" \
    --background --python syscity_blender.py \
    -- --data syscity_data.json --output city.glb --render city_preview.png

  # demo mode (no data file needed):
  blender --background --python syscity_blender.py -- --demo --output city.glb --render preview.png

Interactively (in Blender Script Editor):
  Open this file, set DATA_FILE at the top, press Run Script.

Data contract  (syscity_data.json — same shape as collector.py snapshots):
  {
    "cpu": 42.0,
    "mem":  {"used": 54.3, "total": 128},
    "disk": {"used": 1430, "total": 2000},
    "net":  {"up_kbps": 340, "down_kbps": 1200},
    "building": true,
    "procs": [{"pid":1,"name":"ollama.exe","cpu":22,"mem":21.5}, ...]
  }
"""

import bpy
import mathutils
import json
import math
import random
import sys
import os

# ─── inline data path when running from Script Editor ────────────────────────
DATA_FILE = None   # set to r"C:\...\syscity_data.json" or leave None for demo

# ─── grid constants ───────────────────────────────────────────────────────────
GRID  = 7
PITCH = 22.0
BLOCK = 14.0
HALF  = (GRID * PITCH) / 2.0
ROAD_W = PITCH - BLOCK

# block positions of special structures  (col, row)
POS_SPIRE = (3, 3)
POS_WAREHOUSE = (5, 2)
POS_CRANE = (1, 4)

# ─── colour palette ───────────────────────────────────────────────────────────
C_CONCRETE = [
    (0.72, 0.70, 0.67),
    (0.58, 0.56, 0.53),
    (0.52, 0.56, 0.60),
    (0.64, 0.60, 0.68),
    (0.48, 0.52, 0.56),
]
C_GLASS       = (0.50, 0.72, 0.90)
C_ROAD        = (0.14, 0.16, 0.20)
C_GROUND      = (0.12, 0.14, 0.18)
C_WAREHOUSE   = (0.28, 0.33, 0.40)
C_METAL_DARK  = (0.08, 0.09, 0.11)
C_NEON_CYAN   = (0.05, 0.90, 1.00)
C_NEON_PINK   = (1.00, 0.15, 0.55)
C_NEON_AMBER  = (1.00, 0.62, 0.08)
C_NEON_MEM    = (0.40, 0.22, 1.00)
C_LAMP_WARM   = (1.00, 0.90, 0.72)


# ═══════════════════════════════════════════════════════════════════════════════
# UTILITIES
# ═══════════════════════════════════════════════════════════════════════════════

def rgba(*c):
    """Ensure 4-tuple."""
    if len(c) == 1:
        c = c[0]
    return (*c[:3], 1.0)


def block_center(ix, iz):
    x = -HALF + ix * PITCH + BLOCK / 2.0
    z = -HALF + iz * PITCH + BLOCK / 2.0
    return x, z


def link_obj(obj):
    bpy.context.scene.collection.objects.link(obj)


def purge_scene():
    """Remove every object, mesh, material, light, camera from the scene."""
    for col in list(bpy.data.collections):
        bpy.data.collections.remove(col)
    for obj in list(bpy.data.objects):
        bpy.data.objects.remove(obj, do_unlink=True)
    for blk in list(bpy.data.meshes):
        bpy.data.meshes.remove(blk)
    for blk in list(bpy.data.materials):
        bpy.data.materials.remove(blk)
    for blk in list(bpy.data.lights):
        bpy.data.lights.remove(blk)
    for blk in list(bpy.data.cameras):
        bpy.data.cameras.remove(blk)
    for blk in list(bpy.data.curves):
        bpy.data.curves.remove(blk)


# ─── material factory ─────────────────────────────────────────────────────────

def mat_new(name, base, roughness=0.75, metallic=0.0,
            emission=None, emit_strength=0.0,
            transmission=0.0, ior=1.45, alpha=1.0):
    """Create a Principled BSDF material, Blender 4.x / 5.x compatible."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    ns = m.node_tree.nodes
    lk = m.node_tree.links
    ns.clear()

    out  = ns.new("ShaderNodeOutputMaterial"); out.location  = (500, 0)
    bsdf = ns.new("ShaderNodeBsdfPrincipled"); bsdf.location = (100, 0)
    lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    bsdf.inputs["Base Color"].default_value = rgba(base)
    bsdf.inputs["Roughness"].default_value  = roughness
    bsdf.inputs["Metallic"].default_value   = metallic

    # Transmission — Blender 4 renamed "Transmission" → "Transmission Weight"
    if transmission > 0:
        for key in ("Transmission Weight", "Transmission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = transmission
                break
        m.blend_method = "BLEND"
        m.use_backface_culling = False

    # Emission — Blender 4 split into Color + Strength
    if emission and emit_strength > 0:
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = rgba(emission)
                break
        for key in ("Emission Strength",):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = emit_strength
                break

    if alpha < 1.0:
        bsdf.inputs["Alpha"].default_value = alpha
        m.blend_method = "BLEND"
    if ior != 1.45 and "IOR" in bsdf.inputs:
        bsdf.inputs["IOR"].default_value = ior

    return m


def mat_window_glow(name, base, window_color, emit_strength=1.8, floor_count=8):
    """Concrete body + emissive window grid via procedural bands."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    ns = m.node_tree.nodes
    lk = m.node_tree.links
    ns.clear()

    out  = ns.new("ShaderNodeOutputMaterial"); out.location  = (800, 0)
    mix  = ns.new("ShaderNodeMixShader");      mix.location  = (600, 0)
    lk.new(mix.outputs["Shader"], out.inputs["Surface"])

    body = ns.new("ShaderNodeBsdfPrincipled"); body.location = (200, 150)
    body.inputs["Base Color"].default_value = rgba(base)
    body.inputs["Roughness"].default_value  = 0.82
    lk.new(body.outputs["BSDF"], mix.inputs[1])

    emi  = ns.new("ShaderNodeEmission"); emi.location = (200, -100)
    emi.inputs["Color"].default_value    = rgba(window_color)
    emi.inputs["Strength"].default_value = emit_strength
    lk.new(emi.outputs["Emission"], mix.inputs[2])

    # UV → wave for window rows
    tc   = ns.new("ShaderNodeTexCoord"); tc.location = (-400, -100)
    mp   = ns.new("ShaderNodeMapping");  mp.location = (-200, -100)
    mp.inputs["Scale"].default_value = (2.5, float(floor_count), 1.0)
    lk.new(tc.outputs["Object"], mp.inputs["Vector"])

    wv   = ns.new("ShaderNodeTexWave"); wv.location = (0, -100)
    wv.wave_type = "BANDS"; wv.bands_direction = "Y"
    wv.inputs["Scale"].default_value      = 1.0
    wv.inputs["Distortion"].default_value = 0.0
    wv.inputs["Detail"].default_value     = 0.0
    lk.new(mp.outputs["Vector"], wv.inputs["Vector"])

    thr  = ns.new("ShaderNodeMath"); thr.location = (250, -200)
    thr.operation = "GREATER_THAN"; thr.inputs[1].default_value = 0.52
    lk.new(wv.outputs["Color"], thr.inputs[0])
    lk.new(thr.outputs["Value"], mix.inputs["Fac"])

    return m


def mat_corrugated_metal(name, base, emission=None, emit_str=0.0):
    """Metallic base + procedural corrugation bump."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    ns = m.node_tree.nodes
    lk = m.node_tree.links
    ns.clear()

    out  = ns.new("ShaderNodeOutputMaterial"); out.location  = (700, 0)
    bsdf = ns.new("ShaderNodeBsdfPrincipled"); bsdf.location = (350, 0)
    lk.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    bsdf.inputs["Base Color"].default_value = rgba(base)
    bsdf.inputs["Roughness"].default_value  = 0.50
    bsdf.inputs["Metallic"].default_value   = 0.88

    if emission and emit_str > 0:
        for key in ("Emission Color", "Emission"):
            if key in bsdf.inputs:
                bsdf.inputs[key].default_value = rgba(emission)
                break
        if "Emission Strength" in bsdf.inputs:
            bsdf.inputs["Emission Strength"].default_value = emit_str

    tc   = ns.new("ShaderNodeTexCoord"); tc.location = (-400, -200)
    wv   = ns.new("ShaderNodeTexWave");  wv.location = (-150, -200)
    wv.wave_type = "BANDS"; wv.bands_direction = "X"
    wv.inputs["Scale"].default_value      = 14.0
    wv.inputs["Distortion"].default_value = 0.08
    lk.new(tc.outputs["Object"], wv.inputs["Vector"])

    bump = ns.new("ShaderNodeBump"); bump.location = (100, -200)
    bump.inputs["Strength"].default_value  = 0.55
    bump.inputs["Distance"].default_value  = 0.04
    lk.new(wv.outputs["Color"], bump.inputs["Height"])
    lk.new(bump.outputs["Normal"], bsdf.inputs["Normal"])

    return m


# ═══════════════════════════════════════════════════════════════════════════════
# SCENE SETUP — render, world, lights
# ═══════════════════════════════════════════════════════════════════════════════

def setup_render(w=1920, h=1080):
    sc = bpy.context.scene
    sc.render.engine                        = "BLENDER_EEVEE_NEXT"
    sc.render.resolution_x                  = w
    sc.render.resolution_y                  = h
    sc.render.resolution_percentage         = 100
    sc.render.film_transparent              = False
    sc.render.image_settings.file_format    = "PNG"
    sc.render.image_settings.color_mode     = "RGBA"

    ev = sc.eevee
    # AO + SSR — available in all EEVEE versions
    for attr, val in [("use_gtao", True), ("use_ssr", True),
                      ("shadow_cube_size", "1024"),
                      ("shadow_cascade_size", "2048"),
                      ("volumetric_tile_size", "8"),
                      ("use_volumetric_lights", True)]:
        try:
            setattr(ev, attr, val)
        except AttributeError:
            pass


def setup_compositor_bloom():
    """Bloom via compositor Glare node (EEVEE Next / Blender 4.2+)."""
    sc = bpy.context.scene
    sc.use_nodes = True
    sc.render.use_compositing = True

    tree  = sc.node_tree
    ns    = tree.nodes
    lk    = tree.links
    ns.clear()

    rl    = ns.new("CompositorNodeRLayers"); rl.location = (-300, 0)
    glare = ns.new("CompositorNodeGlare");   glare.location = (0, 0)
    comp  = ns.new("CompositorNodeComposite"); comp.location = (350, 0)

    glare.glare_type = "BLOOM"
    glare.threshold  = 0.75
    glare.size       = 8
    try:
        glare.quality = "HIGH"
    except Exception:
        pass
    glare.mix = 0.85   # blend factor: 1 = full glare output, 0 = original

    lk.new(rl.outputs["Image"],    glare.inputs["Image"])
    lk.new(glare.outputs["Image"], comp.inputs["Image"])


def setup_world():
    w = bpy.data.worlds.new("SysCity_World")
    bpy.context.scene.world = w
    w.use_nodes = True
    ns = w.node_tree.nodes
    lk = w.node_tree.links
    ns.clear()

    out  = ns.new("ShaderNodeOutputWorld"); out.location = (500, 0)
    bg   = ns.new("ShaderNodeBackground");  bg.location  = (200, 0)
    bg.inputs["Color"].default_value    = (0.025, 0.030, 0.080, 1.0)
    bg.inputs["Strength"].default_value = 0.18
    lk.new(bg.outputs["Background"], out.inputs["Surface"])

    # Volumetric atmosphere (city haze)
    scat = ns.new("ShaderNodeVolumeScatter"); scat.location = (200, -200)
    scat.inputs["Color"].default_value   = (0.55, 0.60, 0.78, 1.0)
    scat.inputs["Density"].default_value = 0.010
    out2 = ns.new("ShaderNodeOutputWorld"); out2.location = (500, -200)
    out2.target = "VOLUME"
    lk.new(scat.outputs["Volume"], out2.inputs["Volume"])


def add_lighting():
    # Key: warm low-angle sun (dusk)
    sun_d = bpy.data.lights.new("Sun", "SUN")
    sun_d.energy = 4.0
    sun_d.color  = (1.0, 0.82, 0.62)
    sun_d.angle  = math.radians(2.5)
    sun_d.use_shadow = True
    sun_o = bpy.data.objects.new("Sun", sun_d); link_obj(sun_o)
    sun_o.rotation_euler = (math.radians(36), 0, math.radians(-52))

    # Fill: cool blue area
    fill_d = bpy.data.lights.new("Fill", "AREA")
    fill_d.energy = 100; fill_d.color = (0.32, 0.48, 0.90); fill_d.size = 80.0
    fill_o = bpy.data.objects.new("Fill", fill_d); link_obj(fill_o)
    fill_o.location       = (-55, 55, 85)
    fill_o.rotation_euler = (math.radians(35), 0, math.radians(118))

    # Rim: electric blue backlight
    rim_d = bpy.data.lights.new("Rim", "SPOT")
    rim_d.energy = 900; rim_d.color = (0.35, 0.50, 1.0)
    rim_d.spot_size = math.radians(40); rim_d.spot_blend = 0.45
    rim_o = bpy.data.objects.new("Rim", rim_d); link_obj(rim_o)
    rim_o.location       = (95, -75, 95)
    rim_o.rotation_euler = (math.radians(53), 0, math.radians(38))


# ═══════════════════════════════════════════════════════════════════════════════
# GROUND + ROADS
# ═══════════════════════════════════════════════════════════════════════════════

def build_ground():
    ext = HALF + 45
    verts = [(-ext,-ext,0),(ext,-ext,0),(ext,ext,0),(-ext,ext,0)]
    mesh  = bpy.data.meshes.new("Ground")
    mesh.from_pydata(verts, [], [(0,1,2,3)])
    mesh.update()
    obj = bpy.data.objects.new("Ground", mesh); link_obj(obj)
    obj.data.materials.append(mat_new("m_ground", C_GROUND, roughness=0.94))


def _road_strip(name, x0, x1, z0, z1, y=0.01):
    verts = [(x0,z0,y),(x1,z0,y),(x1,z1,y),(x0,z1,y)]
    mesh  = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], [(0,1,2,3)])
    mesh.update()
    obj = bpy.data.objects.new(name, mesh); link_obj(obj)
    return obj


def build_roads():
    rm  = mat_new("m_road", C_ROAD, roughness=0.90)
    ext = HALF + 35
    for i in range(GRID + 1):
        edge = -HALF + i * PITCH
        # horizontal strip
        h = _road_strip(f"RH{i}", -ext, ext, edge - ROAD_W/2, edge + ROAD_W/2 - BLOCK/2 + ROAD_W/2)
        h.data.materials.append(rm)
        # vertical strip
        v = _road_strip(f"RV{i}", edge - ROAD_W/2, edge + ROAD_W/2 - BLOCK/2 + ROAD_W/2, -ext, ext)
        v.data.materials.append(rm)


def build_sidewalks():
    """Slightly raised concrete between road edge and building footprint."""
    sw_mat = mat_new("m_sidewalk", (0.55, 0.53, 0.50), roughness=0.90)
    h = 0.04
    for ix in range(GRID):
        for iz in range(GRID):
            cx, cz = block_center(ix, iz)
            half_b = BLOCK / 2.0 - 0.5
            verts = [
                (cx-half_b, cz-half_b, h),
                (cx+half_b, cz-half_b, h),
                (cx+half_b, cz+half_b, h),
                (cx-half_b, cz+half_b, h),
            ]
            mesh = bpy.data.meshes.new(f"SW{ix}{iz}")
            mesh.from_pydata(verts, [], [(0,1,2,3)])
            mesh.update()
            obj = bpy.data.objects.new(f"SW{ix}{iz}", mesh); link_obj(obj)
            obj.data.materials.append(sw_mat)


# ═══════════════════════════════════════════════════════════════════════════════
# BUILDINGS
# ═══════════════════════════════════════════════════════════════════════════════

def _add_bevel_mod(obj, width=0.14, segs=2):
    mod = obj.modifiers.new("Bevel", "BEVEL")
    mod.width        = width
    mod.segments     = segs
    mod.limit_method = "ANGLE"
    mod.angle_limit  = math.radians(55)
    return mod


def _box_obj(name, loc, sx, sy, sz, mat=None, bevel=True):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = (sx, sy, sz)
    bpy.ops.object.transform_apply(scale=True)
    if bevel:
        _add_bevel_mod(obj)
    if mat:
        obj.data.materials.clear()
        obj.data.materials.append(mat)
    obj.cast_shadow = True
    return obj


def build_process_towers(procs, mem_total):
    SPECIAL = {POS_SPIRE, POS_WAREHOUSE, POS_CRANE}
    rng  = random.Random(42)
    idx  = 0

    # window colours cycle per-district
    win_colors = [C_NEON_AMBER, C_NEON_CYAN, (0.9, 0.8, 0.5), C_NEON_PINK, C_NEON_AMBER]

    for ix in range(GRID):
        for iz in range(GRID):
            if (ix, iz) in SPECIAL:
                continue
            cx, cz = block_center(ix, iz)
            n = 1 + ((ix * 7 + iz * 3) % 2)

            for k in range(n):
                p    = procs[idx % len(procs)] if procs else None
                mem  = p["mem"] if p else rng.uniform(0.3, 4.0)
                cpu  = p["cpu"] if p else 0.0

                h = max(3.5, min(46.0, 3.5 + (mem / max(mem_total, 1)) * 220))
                w = rng.uniform(4.2, 6.8)
                d = rng.uniform(4.2, 6.8)

                ox = (-2.6 + k * 5.0) + rng.uniform(-0.6, 0.6)
                oz = ( 2.2 - k * 4.6) + rng.uniform(-0.6, 0.6)

                emit = 0.45 + (cpu / 100.0) * 3.8
                base_c  = C_CONCRETE[idx % len(C_CONCRETE)]
                win_c   = win_colors[(ix + iz) % len(win_colors)]

                m = mat_window_glow(f"m_tower_{idx}", base_c, win_c,
                                    emit_strength=emit,
                                    floor_count=max(4, int(h / 3.5)))

                obj = _box_obj(f"Tower_{idx}", (cx + ox, cz + oz, h / 2), w, d, h, mat=m)
                if p:
                    obj["proc_name"] = p["name"]
                    obj["proc_pid"]  = p["pid"]

                # Slim rooftop detail (antenna / AC unit)
                if rng.random() > 0.45:
                    dh = rng.uniform(1.2, 3.5)
                    dm = mat_new(f"m_roof_{idx}", C_METAL_DARK, roughness=0.65, metallic=0.9)
                    _box_obj(f"Roof_{idx}", (cx + ox + rng.uniform(-1,1),
                                             cz + oz + rng.uniform(-1,1),
                                             h + dh/2),
                             rng.uniform(0.6,1.4), rng.uniform(0.6,1.4), dh,
                             mat=dm, bevel=False)

                idx += 1


# ═══════════════════════════════════════════════════════════════════════════════
# SPECIAL STRUCTURES
# ═══════════════════════════════════════════════════════════════════════════════

def build_spire(mem_used, mem_total):
    cx, cz  = block_center(*POS_SPIRE)
    frac    = min(1.0, mem_used / max(mem_total, 1))
    full_h  = 52.0
    fill_h  = max(1.2, frac * full_h)

    # Outer glass tube
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=3.0, depth=full_h,
                                         location=(cx, cz, full_h/2))
    shell = bpy.context.active_object; shell.name = "Spire_Shell"
    shell.data.materials.append(mat_new(
        "m_spire_glass", C_GLASS, roughness=0.04,
        transmission=0.82, ior=1.45, alpha=0.30))

    # Inner glowing fill — height = memory fraction
    bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=2.0, depth=fill_h,
                                         location=(cx, cz, fill_h/2))
    fill = bpy.context.active_object; fill.name = "Spire_Fill"
    fill.data.materials.append(mat_new(
        "m_spire_fill", C_NEON_MEM, roughness=0.12,
        emission=C_NEON_MEM, emit_strength=5.0))

    # Glowing cap
    bpy.ops.mesh.primitive_uv_sphere_add(radius=1.6, location=(cx, cz, full_h+1.2))
    cap = bpy.context.active_object; cap.name = "Spire_Cap"
    cap.data.materials.append(mat_new(
        "m_spire_cap", C_NEON_MEM, roughness=0.04,
        emission=C_NEON_MEM, emit_strength=9.0))

    # Interior point light
    ld = bpy.data.lights.new("SpireGlow", "POINT")
    ld.energy = max(200, 3500 * frac); ld.color = C_NEON_MEM[:3]; ld.shadow_soft_size = 3.0
    lo = bpy.data.objects.new("SpireGlow", ld); link_obj(lo)
    lo.location = (cx, cz, fill_h * 0.55)

    return fill_h, full_h


def build_warehouse(disk_used, disk_total):
    cx, cz  = block_center(*POS_WAREHOUSE)
    frac    = min(1.0, disk_used / max(disk_total, 1))
    emit_s  = frac * 3.2

    # Main body
    body_mat = mat_corrugated_metal("m_wh_body", C_WAREHOUSE,
                                    emission=C_NEON_CYAN, emit_str=emit_s)
    body = _box_obj("Warehouse", (cx, cz, 3.8), 14.0, 10.0, 7.6, mat=body_mat, bevel=False)
    _add_bevel_mod(body, width=0.25, segs=1)

    # Barrel roof (half-cylinder)
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=5.8, depth=14.2,
                                         location=(cx, cz, 9.0))
    roof = bpy.context.active_object; roof.name = "WH_Roof"
    roof.rotation_euler = (math.radians(90), 0, 0)
    roof.scale = (1.0, 0.48, 1.0)
    bpy.ops.object.transform_apply(rotation=True, scale=True)
    roof.data.materials.append(mat_corrugated_metal("m_wh_roof", (0.20, 0.24, 0.30)))

    # Loading dock ramp
    ramp_mat = mat_new("m_dock", (0.30, 0.30, 0.32), roughness=0.80, metallic=0.6)
    _box_obj("WH_Dock", (cx, cz + 5.5, 0.4), 5.0, 2.0, 0.8, mat=ramp_mat, bevel=False)

    # Cyan glow
    ld = bpy.data.lights.new("WHGlow", "POINT")
    ld.energy = 600 * frac; ld.color = C_NEON_CYAN[:3]; ld.shadow_soft_size = 4.0
    lo = bpy.data.objects.new("WHGlow", ld); link_obj(lo)
    lo.location = (cx, cz, 5.0)

    # 3-D billboard label
    pct = frac * 100
    label = f"DISK  {disk_used/1000:.2f} TB / {disk_total/1000:.1f} TB  ({pct:.0f}%)"
    _text_label(label, (cx, cz - 5.8, 4.0), size=0.50,
                color=C_NEON_CYAN, emit_str=3.5 + emit_s * 0.5)


def build_crane(building_active=False):
    cx, cz = block_center(*POS_CRANE)
    col_m  = C_NEON_AMBER if building_active else C_METAL_DARK
    em     = C_NEON_AMBER if building_active else None
    em_s   = 2.5 if building_active else 0.0

    mat_frame = mat_new("m_frame", (0.45, 0.42, 0.36), roughness=0.88)
    mat_crane = mat_new("m_crane", col_m, roughness=0.45, metallic=0.75,
                        emission=em, emit_strength=em_s)
    mat_cable = mat_new("m_cable", C_METAL_DARK, roughness=0.65, metallic=0.85)

    # Scaffolding box (wireframe)
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(cx-1.5, cz+1.5, 4.0))
    frame = bpy.context.active_object; frame.name = "CraneFrame"
    frame.scale = (6.0, 6.0, 8.0)
    bpy.ops.object.transform_apply(scale=True)
    wfm = frame.modifiers.new("Wireframe", "WIREFRAME"); wfm.thickness = 0.14
    frame.data.materials.append(mat_frame)

    # Mast
    _box_obj("CraneMast", (cx+3, cz-3, 10), 0.85, 0.85, 20.0, mat=mat_crane)

    # Jib (arm)
    _box_obj("CraneJib", (cx+3+5.5, cz-3, 20.3), 13.0, 0.55, 0.55,
             mat=mat_crane, bevel=False)

    # Counter-jib
    _box_obj("CraneCounterJib", (cx+3-3.0, cz-3, 20.3), 5.0, 0.45, 0.45,
             mat=mat_crane, bevel=False)

    # Cable
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.07, depth=7.0,
                                         location=(cx+3+9.5, cz-3, 16.7))
    cable = bpy.context.active_object; cable.name = "CraneCable"
    cable.data.materials.append(mat_cable)

    # Hook block
    _box_obj("CraneHook", (cx+3+9.5, cz-3, 13.0), 1.4, 1.4, 1.4,
             mat=mat_crane)

    # Beacon
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.42, location=(cx+3, cz-3, 20.8))
    beacon = bpy.context.active_object; beacon.name = "CraneBeacon"
    beacon.data.materials.append(mat_new(
        "m_beacon", C_NEON_AMBER, roughness=0.1,
        emission=C_NEON_AMBER, emit_strength=6.0 if building_active else 0.2))

    if building_active:
        ld = bpy.data.lights.new("CraneBeacon", "POINT")
        ld.energy = 700; ld.color = C_NEON_AMBER[:3]
        lo = bpy.data.objects.new("CraneBeaconL", ld); link_obj(lo)
        lo.location = (cx+3, cz-3, 20.8)


def build_street_lamps():
    mat_pole = mat_new("m_pole", (0.22, 0.22, 0.25), roughness=0.60, metallic=0.92)
    mat_head = mat_new("m_head", C_LAMP_WARM, roughness=0.15,
                       emission=C_LAMP_WARM, emit_strength=5.5)

    for i in range(1, GRID, 2):
        for j in range(1, GRID, 2):
            gap = ROAD_W / 2.0
            x   = -HALF + i * PITCH - gap
            z   = -HALF + j * PITCH - gap

            bpy.ops.mesh.primitive_cylinder_add(
                vertices=8, radius=0.11, depth=5.8, location=(x, z, 2.9))
            pole = bpy.context.active_object
            pole.name = f"Pole_{i}_{j}"
            pole.data.materials.append(mat_pole)

            bpy.ops.mesh.primitive_uv_sphere_add(radius=0.35, location=(x, z, 5.95))
            head = bpy.context.active_object
            head.name = f"LampHead_{i}_{j}"
            head.data.materials.append(mat_head)

            ld = bpy.data.lights.new(f"LampL_{i}_{j}", "POINT")
            ld.energy = 160; ld.color = (1.0, 0.88, 0.70); ld.shadow_soft_size = 0.25
            lo = bpy.data.objects.new(f"LampL_{i}_{j}", ld); link_obj(lo)
            lo.location = (x, z, 5.95)


# ═══════════════════════════════════════════════════════════════════════════════
# LABELS
# ═══════════════════════════════════════════════════════════════════════════════

def _text_label(text, loc, size=0.6, color=C_NEON_CYAN, emit_str=3.0):
    bpy.ops.object.text_add(location=loc)
    obj = bpy.context.active_object
    obj.data.body      = text
    obj.data.size      = size
    obj.data.align_x   = "CENTER"
    obj.data.extrude   = 0.045
    # face billboard toward -Y so visible from typical camera angle
    obj.rotation_euler = (math.radians(90), 0, 0)
    m = mat_new(f"m_lbl_{text[:6]}", color, roughness=0.25,
                emission=color, emit_strength=emit_str)
    obj.data.materials.append(m)
    return obj


def add_dashboard_labels(data):
    cpu  = data.get("cpu", 0)
    mem  = data.get("mem",  {"used": 0, "total": 128})
    disk = data.get("disk", {"used": 0, "total": 2000})
    net  = data.get("net",  {"up_kbps": 0, "down_kbps": 0})

    offset_y = -HALF - 8.0
    _text_label(f"CPU  {cpu:.0f}%",
                (HALF - 12, offset_y, 3.0), size=0.75, color=C_NEON_AMBER)
    _text_label(f"RAM  {mem['used']:.1f} / {mem['total']} GB",
                (0, offset_y, 3.0), size=0.75, color=C_NEON_MEM)
    _text_label(f"NET  ↓ {net['down_kbps']:.0f}  ↑ {net['up_kbps']:.0f} KB/s",
                (-HALF + 12, offset_y, 3.0), size=0.75, color=C_NEON_CYAN)

    # Top-of-spire label
    sx, sz = block_center(*POS_SPIRE)
    _text_label(f"MEM  {mem['used']:.1f} GB",
                (sx, sz - 4.0, 57.0), size=0.70, color=C_NEON_MEM)


# ═══════════════════════════════════════════════════════════════════════════════
# CAMERA
# ═══════════════════════════════════════════════════════════════════════════════

def setup_camera():
    cd = bpy.data.cameras.new("Camera")
    cd.lens               = 32.0   # wide-ish
    cd.dof.use_dof        = True
    cd.dof.focus_distance = 62.0
    cd.dof.aperture_fstop = 2.0

    co = bpy.data.objects.new("Camera", cd); link_obj(co)
    bpy.context.scene.camera = co

    # Low-angle corner shot looking toward spire + warehouse district
    co.location       = (-HALF - 18, -HALF - 18, 7.5)
    co.rotation_euler = (math.radians(76), 0, math.radians(47))


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORT
# ═══════════════════════════════════════════════════════════════════════════════

def export_glb(path):
    bpy.ops.export_scene.gltf(
        filepath    = path,
        export_format       = "GLB",
        export_apply        = True,
        export_materials    = "EXPORT",
        export_cameras      = True,
        export_lights       = True,
        export_animations   = False,
        export_yup          = True,
    )
    print(f"[syscity] GLB  →  {path}")


def render_preview(path):
    bpy.context.scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print(f"[syscity] PNG  →  {path}")


# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

DEMO_DATA = {
    "cpu": 42.0,
    "mem":  {"used": 54.3, "total": 128},
    "disk": {"used": 1430, "total": 2000},
    "net":  {"up_kbps": 340, "down_kbps": 1200},
    "building": True,
    "procs": [
        {"pid": 4120, "name": "ollama.exe",    "cpu": 22,  "mem": 21.5},
        {"pid":  912, "name": "chrome.exe",    "cpu": 11,  "mem":  4.2},
        {"pid": 7741, "name": "Code.exe",      "cpu":  5,  "mem":  2.8},
        {"pid": 3308, "name": "blender.exe",   "cpu": 14,  "mem":  8.3},
        {"pid": 1188, "name": "python.exe",    "cpu":  9,  "mem":  3.1},
        {"pid": 5520, "name": "postgres.exe",  "cpu":  2,  "mem":  1.4},
        {"pid":  660, "name": "node.exe",      "cpu":  8,  "mem":  1.9},
        {"pid": 8807, "name": "cargo.exe",     "cpu": 18,  "mem":  0.9},
        {"pid": 2230, "name": "dwm.exe",       "cpu":  2,  "mem":  0.5},
        {"pid": 9912, "name": "claude.exe",    "cpu":  4,  "mem":  1.2},
        {"pid": 3471, "name": "explorer.exe",  "cpu":  1,  "mem":  0.7},
        {"pid": 6105, "name": "pytest",        "cpu":  0,  "mem":  0.4},
    ]
}


def build_city(data, glb_out=None, render_out=None):
    purge_scene()
    setup_render()
    setup_world()
    add_lighting()
    setup_compositor_bloom()

    build_ground()
    build_roads()
    build_sidewalks()

    procs     = data.get("procs", [])
    mem       = data.get("mem",  {"used": 64, "total": 128})
    disk      = data.get("disk", {"used": 1000, "total": 2000})
    building  = data.get("building", False)

    build_process_towers(procs, mem["total"])
    build_spire(mem["used"], mem["total"])
    build_warehouse(disk["used"], disk["total"])
    build_crane(building_active=building)
    build_street_lamps()
    add_dashboard_labels(data)
    setup_camera()

    if glb_out:
        export_glb(os.path.abspath(glb_out))
    if render_out:
        render_preview(os.path.abspath(render_out))


if __name__ == "__main__":
    import argparse

    # Blender passes script args after "--"
    argv = sys.argv
    argv = argv[argv.index("--") + 1:] if "--" in argv else []

    ap = argparse.ArgumentParser(description="SysCity Blender generator")
    ap.add_argument("--data",   default=None, help="Path to syscity_data.json")
    ap.add_argument("--output", default="syscity.glb", help="GLB output path")
    ap.add_argument("--render", default=None, help="PNG render output path")
    ap.add_argument("--demo",   action="store_true", help="Use built-in demo data")
    args = ap.parse_args(argv)

    if args.demo or (args.data is None and DATA_FILE is None):
        data = DEMO_DATA
    else:
        path = args.data or DATA_FILE
        with open(path) as f:
            data = json.load(f)

    print(f"[syscity] building city  cpu={data.get('cpu',0):.0f}%  "
          f"mem={data.get('mem',{}).get('used',0):.1f}/{data.get('mem',{}).get('total',128)} GB")

    build_city(data, glb_out=args.output, render_out=args.render)
    print("[syscity] done.")
