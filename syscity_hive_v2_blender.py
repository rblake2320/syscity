"""Run premium hive build via Blender MCP TCP socket."""
import subprocess, socket, json, time, sys, os

BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
HOST, PORT = "localhost", 9876

BUILD_CODE = """
import bpy, math, random
random.seed(42)

bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
scene = bpy.context.scene
scene.name = "SysCity_Hive_v2"

# Render settings
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = 256
scene.cycles.use_denoising = True
try:
    scene.cycles.denoiser = 'OPTIX'
except:
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.filepath = r'C:\\\\Users\\\\techai\\\\Downloads\\\\syscity_hive_v2'
scene.render.image_settings.file_format = 'PNG'

# World — near-black, no volume (avoid ambient flood)
world = bpy.data.worlds.new("HiveWorld")
scene.world = world
world.use_nodes = True
wnt = world.node_tree
wnt.nodes.clear()
bg  = wnt.nodes.new("ShaderNodeBackground")
bg.inputs["Color"].default_value    = (0.003, 0.001, 0.0, 1)
bg.inputs["Strength"].default_value = 0.05
out = wnt.nodes.new("ShaderNodeOutputWorld")
wnt.links.new(bg.outputs["Background"], out.inputs["Surface"])

# Color management for drama
scene.view_settings.view_transform = "Filmic"
scene.view_settings.look = "High Contrast"
scene.view_settings.exposure = -0.5

# ---- Material builders ----
def mat_wax(name, c=(0.5, 0.25, 0.05)):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value    = (*c, 1)
    b.inputs["Roughness"].default_value     = 0.58
    b.inputs["Specular IOR Level"].default_value = 0.3
    b.inputs["Subsurface Weight"].default_value  = 0.07
    b.inputs["Subsurface Radius"].default_value  = (0.4, 0.2, 0.05)
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m

def mat_honey(name, em=0.4):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value        = (0.95, 0.42, 0.01, 1)
    b.inputs["Roughness"].default_value         = 0.08
    b.inputs["Metallic"].default_value          = 0.0
    b.inputs["Specular IOR Level"].default_value = 0.8
    b.inputs["Emission Color"].default_value    = (1.0, 0.5, 0.02, 1)
    b.inputs["Emission Strength"].default_value = em
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m

def mat_metal(name, c=(0.9,0.72,0.1), rough=0.08):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    b = nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value = (*c, 1)
    b.inputs["Metallic"].default_value   = 1.0
    b.inputs["Roughness"].default_value  = rough
    nt.links.new(b.outputs["BSDF"], out.inputs["Surface"])
    return m

def mat_glow(name, c=(1,0.5,0), s=5.0):
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    e = nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value    = (*c, 1)
    e.inputs["Strength"].default_value = s
    nt.links.new(e.outputs["Emission"], out.inputs["Surface"])
    return m

M_WAX      = mat_wax("M_Wax",    (0.48, 0.22, 0.04))
M_WAX_DK   = mat_wax("M_WaxDk",  (0.28, 0.12, 0.02))
M_HONEY    = mat_honey("M_Honey", 0.8)
M_HONEY_DM = mat_honey("M_HoneyDm", 0.25)
M_GOLD     = mat_metal("M_Gold",  (0.95, 0.76, 0.1),  0.07)
M_CHROME   = mat_metal("M_Chr",   (0.85, 0.85, 0.88), 0.05)
M_GLOW_O   = mat_glow("M_GO",  (1, 0.55, 0.0),  12.0)
M_GLOW_Y   = mat_glow("M_GY",  (1, 0.88, 0.12), 8.0)
M_GLOW_R   = mat_glow("M_GR",  (1, 0.18, 0.02), 18.0)

PI6 = math.pi / 6
HR  = 1.18

# ---- Floor hex grid ----
for row in range(12):
    for col in range(16):
        x = HR*1.732*(col + 0.5*(row%2)) - HR*1.732*8
        y = HR*1.5*row - HR*1.5*6
        d = math.sqrt(x*x + y*y)
        if d < 4.0: continue
        h = random.uniform(0.2, 0.65)
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=HR*0.96, depth=h, location=(x,y,h/2-0.05))
        obj = bpy.context.object
        obj.rotation_euler.z = PI6
        rnd = random.random()
        if d < 7:
            obj.data.materials.append(M_HONEY if rnd>0.3 else M_GLOW_Y)
        elif d < 11:
            obj.data.materials.append(M_HONEY_DM if rnd>0.4 else M_WAX)
        else:
            obj.data.materials.append(M_WAX if rnd>0.3 else M_WAX_DK)
        # gold rim
        bpy.ops.mesh.primitive_torus_add(major_radius=HR*0.96, minor_radius=0.06,
                                         major_segments=6, minor_segments=8, location=(x,y,h-0.05))
        bpy.context.object.rotation_euler.z = PI6
        bpy.context.object.data.materials.append(M_GOLD)

# ---- Background honeycomb wall ----
WY = HR*1.5*6 + 2.0
for row in range(10):
    for col in range(20):
        x = HR*1.732*(col + 0.5*(row%2)) - HR*1.732*10
        z = HR*1.5*row + 0.5
        h = random.uniform(0.5, 2.0)
        bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=HR*0.94, depth=h, location=(x,WY,z))
        obj = bpy.context.object
        obj.rotation_euler.x = math.pi/2
        obj.rotation_euler.z = PI6
        rnd = random.random()
        obj.data.materials.append(M_HONEY_DM if rnd>0.55 else (M_GLOW_O if rnd>0.3 else M_WAX_DK))

# ---- Queen tower ----
tower = [(0.0,0.6,1.5,10),(0.7,1.6,1.2,10),(1.7,2.9,0.9,9),(3.0,4.2,0.65,8),(4.3,5.8,0.42,7)]
for z0,z1,r,seg in tower:
    h = z1-z0
    bpy.ops.mesh.primitive_cylinder_add(vertices=seg, radius=r, depth=h, location=(0,0,z0+h/2))
    bpy.context.object.data.materials.append(M_GOLD)
# Band rings
for z in [1.4, 2.7, 4.0]:
    bpy.ops.mesh.primitive_torus_add(major_radius=0.85, minor_radius=0.12,
                                     major_segments=12, minor_segments=10, location=(0,0,z))
    bpy.context.object.data.materials.append(M_CHROME)
# Crown spires
for i in range(5):
    a = i*2*math.pi/5
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.1, depth=0.7,
                                        location=(math.cos(a)*0.55, math.sin(a)*0.55, 5.95))
    bpy.context.object.data.materials.append(M_GOLD)
# Queen core
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.42, location=(0,0,5.1), segments=28, ring_count=18)
bpy.context.object.data.materials.append(M_GLOW_R)
# Inner shaft glow
bpy.ops.mesh.primitive_cylinder_add(vertices=16, radius=0.16, depth=5.5, location=(0,0,2.75))
bpy.context.object.data.materials.append(M_GLOW_O)

# ---- CPU cell ring ----
for i in range(6):
    a = i*math.pi/3
    x,y = math.cos(a)*5.8, math.sin(a)*5.8
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=1.45, depth=3.8, location=(x,y,1.9))
    bpy.context.object.rotation_euler.z = PI6
    bpy.context.object.data.materials.append(M_HONEY)
    # inner glow core
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=0.52, depth=3.5, location=(x,y,1.75))
    bpy.context.object.rotation_euler.z = PI6
    bpy.context.object.data.materials.append(M_GLOW_Y)
    # top collar
    bpy.ops.mesh.primitive_torus_add(major_radius=1.45, minor_radius=0.13,
                                     major_segments=6, minor_segments=12, location=(x,y,3.82))
    bpy.context.object.rotation_euler.z = PI6
    bpy.context.object.data.materials.append(M_GOLD)

# ---- Middle ring (storage) ----
for i in range(12):
    a = i*math.pi/6
    x,y = math.cos(a)*10.8, math.sin(a)*10.8
    h = random.uniform(1.6, 3.0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=6, radius=1.1, depth=h, location=(x,y,h/2))
    bpy.context.object.rotation_euler.z = PI6
    bpy.context.object.data.materials.append(M_HONEY_DM if i%3!=0 else M_GLOW_O)
    bpy.ops.mesh.primitive_torus_add(major_radius=1.1, minor_radius=0.09,
                                     major_segments=6, minor_segments=10, location=(x,y,h))
    bpy.context.object.rotation_euler.z = PI6
    bpy.context.object.data.materials.append(M_CHROME)

# ---- Data tubes (queen -> CPU cells) ----
from mathutils import Vector
for i in range(6):
    a = i*math.pi/3
    ex,ey = math.cos(a)*5.8, math.sin(a)*5.8
    crv = bpy.data.curves.new(f"tube{i}", "CURVE")
    crv.dimensions = "3D"
    crv.bevel_depth = 0.055
    crv.bevel_resolution = 5
    sp = crv.splines.new("BEZIER")
    sp.bezier_points.add(2)
    pts = sp.bezier_points
    pts[0].co = Vector((0, 0, 4.8))
    pts[0].handle_right_type = "AUTO"; pts[0].handle_left_type = "AUTO"
    pts[1].co = Vector((math.cos(a)*2.8, math.sin(a)*2.8, 4.0))
    pts[1].handle_right_type = "AUTO"; pts[1].handle_left_type = "AUTO"
    pts[2].co = Vector((ex, ey, 3.2))
    pts[2].handle_right_type = "AUTO"; pts[2].handle_left_type = "AUTO"
    ob = bpy.data.objects.new(f"tube{i}", crv)
    scene.collection.objects.link(ob)
    ob.data.materials.append(M_GLOW_O)

# ---- Lights ----
def pt(loc, e, c=(1,0.65,0.12), r=0.9):
    bpy.ops.object.light_add(type="POINT", location=loc)
    l = bpy.context.object
    l.data.energy = e; l.data.color = c; l.data.shadow_soft_size = r
    return l

pt((0,0,6.2), 5000, (1,0.28,0.04), 0.5)
pt((0,0,3.2), 1800, (1,0.55,0.1),  1.0)
for i in range(6):
    a = i*math.pi/3
    pt((math.cos(a)*5.8, math.sin(a)*5.8, 2.8), 1000, (1,0.8,0.15), 0.7)
for i in range(12):
    a = i*math.pi/6
    pt((math.cos(a)*10.8, math.sin(a)*10.8, 2.0), 300, (1,0.6,0.05), 0.5)

bpy.ops.object.light_add(type="AREA", location=(0,-22,20))
fill = bpy.context.object
fill.rotation_euler = (0.95, 0, 0)
fill.data.energy = 200; fill.data.size = 14; fill.data.color = (0.3,0.12,0.02)

bpy.ops.object.light_add(type="SPOT", location=(16,-12,16))
spot = bpy.context.object
spot.rotation_euler = (0.95, 0, 0.82)
spot.data.energy = 6000; spot.data.spot_size = 0.45; spot.data.color = (1,0.85,0.5)

# ---- Camera ----
bpy.ops.object.camera_add(location=(20,-17,14))
cam = bpy.context.object
cam.rotation_euler = (1.1, 0, 0.9)
scene.camera = cam
cam.data.lens = 35
cam.data.dof.use_dof     = True
cam.data.dof.focus_distance = 24
cam.data.dof.aperture_fstop = 2.2

# ---- Compositor bloom (safe for Blender 5.1) ----
try:
    scene.use_nodes = True
    tree = scene.node_tree
    tree.nodes.clear()
    rl    = tree.nodes.new("CompositorNodeRLayers")
    glare = tree.nodes.new("CompositorNodeGlare")
    glare.glare_type = "FOG_GLOW"; glare.quality = "HIGH"
    glare.threshold  = 0.8; glare.size = 7
    tone  = tree.nodes.new("CompositorNodeTonemap")
    tone.tonemap_type = "RD_PHOTORECEPTOR"; tone.key = 0.18
    comp  = tree.nodes.new("CompositorNodeComposite")
    tree.links.new(rl.outputs["Image"],    glare.inputs["Image"])
    tree.links.new(glare.outputs["Image"], tone.inputs["Image"])
    tree.links.new(tone.outputs["Image"],  comp.inputs["Image"])
    print("Compositor bloom wired")
except Exception as e:
    print(f"Compositor skipped ({e}) — emission glow will handle it")

print("RENDER_START 1920x1080 256spp Cycles+OptiX+Bloom")
bpy.ops.render.render(write_still=True)
print("RENDER_DONE")
"""

def send_recv(sock, code):
    payload = json.dumps({"type": "execute", "code": code, "strict_json": False}) + "\0"
    sock.sendall(payload.encode("utf-8"))
    buf = b""
    while True:
        chunk = sock.recv(65536)
        if not chunk: break
        buf += chunk
        if b"\0" in buf: break
    return json.loads(buf.rstrip(b"\0"))

print("Starting Blender MCP server...")
proc = subprocess.Popen([BLENDER, "--background", "--command", "blender_mcp"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
for attempt in range(20):
    time.sleep(0.5)
    try:
        s = socket.create_connection((HOST, PORT), timeout=1); s.close()
        print(f"Ready ({attempt+1})")
        break
    except: pass

print("Building SysCity Hive v2 via MCP...")
with socket.create_connection((HOST, PORT), timeout=600) as s:
    s.settimeout(600)
    resp = send_recv(s, BUILD_CODE)

proc.terminate()

if resp.get("status") == "error":
    print("ERROR:", resp["message"][:1200])
    sys.exit(1)

png = r"C:\Users\techai\Downloads\syscity_hive_v2.png"
if os.path.exists(png):
    print(f"SUCCESS -> {png}")
else:
    print("Render file not found — checking result:", str(resp)[:300])
