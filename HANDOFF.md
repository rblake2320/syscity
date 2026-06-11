# SysCity Build Handoff

## What We're Building
SysCity — premium sci-fi monitoring dashboard. Each "scene" is a Blender Cycles photorealistic render (PNG) used as a hero background in an HTML page with live HUD overlays. Free tier = Three.js real-time. Premium tier = Blender render + animated HUD.

**Scenes status:**
- `system-hive.html` — DONE (syscity_hive_v2.png)
- `system-city.html` — DONE (syscity_city_v4.png)
- `system-underwater.html` — IN PROGRESS
- `system-space.html`, `system-ocean.html`, `system-ants.html` — pending

---

## Blender MCP — Happy Path

**Start Blender MCP server:**
```python
import subprocess, socket, json, time
BLENDER = r"C:\Program Files\Blender Foundation\Blender 5.1\blender.exe"
proc = subprocess.Popen([BLENDER, "--background", "--command", "blender_mcp"],
                        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
# Wait for port 9876
for _ in range(20):
    time.sleep(0.5)
    try: socket.create_connection(("localhost", 9876), 1).close(); break
    except: pass
```

**Send/receive (null-byte JSON protocol):**
```python
def send_recv(sock, code):
    sock.sendall((json.dumps({"type":"execute","code":code,"strict_json":False})+"\0").encode())
    buf=b""
    while True:
        buf+=sock.recv(65536)
        if b"\0" in buf: break
    return json.loads(buf.rstrip(b"\0"))

with socket.create_connection(("localhost", 9876), timeout=600) as s:
    s.settimeout(600)
    resp = send_recv(s, BUILD_CODE)
proc.terminate()
```

**Scene reset (MUST use this — read_factory_settings is blocked):**
```python
bpy.ops.wm.read_homefile(use_empty=True, use_factory_startup=True)
```

**Render settings that work:**
```python
scene.render.engine = 'CYCLES'
scene.cycles.device = 'GPU'
scene.cycles.samples = 320
scene.cycles.use_denoising = True
try: scene.cycles.denoiser = 'OPTIX'
except: scene.cycles.denoiser = 'OPENIMAGEDENOISE'
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.filepath = r'C:\\Users\\techai\\Downloads\\output'
scene.render.image_settings.file_format = 'PNG'
scene.view_settings.view_transform = 'Filmic'
scene.view_settings.look = 'High Contrast'
scene.view_settings.exposure = 0.3
```

**Materials that work (use these patterns):**
```python
# Emissive glow — neon signs, lights, organisms
def glow(name, c=(0,0.5,1), s=12.0):
    m=bpy.data.materials.new(name); m.use_nodes=True
    nt=m.node_tree; nt.nodes.clear()
    o=nt.nodes.new("ShaderNodeOutputMaterial")
    e=nt.nodes.new("ShaderNodeEmission")
    e.inputs["Color"].default_value=(*c,1); e.inputs["Strength"].default_value=s
    nt.links.new(e.outputs["Emission"],o.inputs["Surface"]); return m

# Principled with emission — glass facades, glowing surfaces
def glass_em(name, c=(0.04,0.12,0.28), em=6.5):
    m=bpy.data.materials.new(name); m.use_nodes=True
    nt=m.node_tree; nt.nodes.clear()
    o=nt.nodes.new("ShaderNodeOutputMaterial")
    b=nt.nodes.new("ShaderNodeBsdfPrincipled")
    b.inputs["Base Color"].default_value=(*c,1)
    b.inputs["Roughness"].default_value=0.04
    b.inputs["Emission Color"].default_value=(*c,1)
    b.inputs["Emission Strength"].default_value=em
    nt.links.new(b.outputs["BSDF"],o.inputs["Surface"]); return m
```

**What NOT to do:**
- No `Transmission Weight` + `blend_method="BLEND"` → washes out white
- No `ShaderNodeVolumePrincipled` in world → floods scene with color
- Compositor: always wrap in `try/except` (node_tree can throw AttributeError)
- `bpy.ops.wm.read_factory_settings` is BLOCKED by sandbox

**World (dark dramatic):**
```python
bg.inputs["Color"].default_value = (0.003,0.004,0.015,1)
bg.inputs["Strength"].default_value = 0.2
```

---

## Hostinger Server — Happy Path

**Server:** `2.25.184.107` | Ubuntu 22.04 | nginx/1.18 | 100GB disk

**Browser terminal:** hpanel.hostinger.com → VPS → Terminal button (opens bos2.hostingervps.com)

**SSH (key already added):**
```bash
ssh root@2.25.184.107
```

**Web root:** `/var/www/html/`

**Add a new project:**
```bash
# From browser terminal or SSH:
cd /var/www/html
git clone https://github.com/rblake2320/REPONAME foldername
chmod -R 755 foldername && chown -R www-data:www-data foldername
```
Accessible at: `https://api.selfconnect.ai/foldername/`

**Update existing project:**
```bash
cd /var/www/html/syscity && git pull
```

**nginx configs:** `/etc/nginx/sites-enabled/`
- `api-selfconnect` — handles `api.selfconnect.ai` (has `/syscity/` static block added)
- `direct-ip` — catch-all for direct IP (also has `/syscity/` block)

**Add new subdomain (when ready):**
1. Hostinger DNS Manager → add A record `newname` → `2.25.184.107`
2. On server:
```bash
# Create nginx config
cat > /etc/nginx/sites-enabled/newname-selfconnect << 'EOF'
server {
    listen 80;
    server_name newname.selfconnect.ai;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name newname.selfconnect.ai;
    root /var/www/html/foldername;
    index index.html;
    location / { try_files $uri $uri/ =404; }
}
EOF
certbot --nginx -d newname.selfconnect.ai
systemctl reload nginx
```

**Deploy syscity render + HTML (from Windows):**
```bash
scp C:/Users/techai/syscity/system-SCENE.html root@2.25.184.107:/var/www/html/syscity/
scp C:/Users/techai/syscity/syscity_SCENE.png root@2.25.184.107:/var/www/html/syscity/
# or just git push + git pull on server
```
