"""Tests of Spektronautilus NVIDIA, built from the package (dist), against a stand-in for ComfyUI.
The stand-in answers like ComfyUI with the ReCaVSR nodes (object_info, upload, prompt, history, view, interrupt, the websocket with
progress), and "upscales" with plain ffmpeg. The real launcher and the real Loop Hospital page run against it.
NOT tested here: real ComfyUI, ReCaVSR itself and an NVIDIA card (there is none in the test machine), and install.sh.
Needs ffmpeg + playwright. Run:  python3 tests/test_nvidia.py   (it builds the package first)"""
import base64, hashlib, http.server, json, os, re, socket, subprocess, sys, tarfile, tempfile, threading, time, urllib.parse, urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright
HERE = Path(__file__).resolve().parent.parent
T = Path(tempfile.mkdtemp(prefix="spknv_")); bad = []
def check(c, m):
    print(("ok   " if c else "FAIL ") + m, flush=True)
    if not c: bad.append(m)
def ff(*a): subprocess.run(["ffmpeg", "-v", "error", "-y", "-nostdin", *a], check=True)
def frames(p): return int(subprocess.check_output(["ffprobe", "-v", "error", "-count_frames", "-select_streams", "v:0", "-show_entries", "stream=nb_read_frames", "-of", "csv=p=0", str(p)]).decode().strip())
def size(p):
    j = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(p)])); return j["streams"][0]["width"], j["streams"][0]["height"]

# ---------------------------------------------------------------- the stand-in for ComfyUI
CI, CO = T / "comfy_in", T / "comfy_out"; CI.mkdir(); CO.mkdir(); (CO / "spektronautilus").mkdir()
JOBS, WS, GRAPHS, EVENTS = {}, {}, [], []
SLOW = {"on": False}
def ws_send(cid, obj):
    s = WS.get(cid)
    if not s: return
    d = json.dumps(obj).encode(); h = bytes([0x81, len(d)]) if len(d) < 126 else bytes([0x81, 126]) + len(d).to_bytes(2, "big")
    try: s.sendall(h + d)
    except Exception: pass
def run_job(pid, g, cid):
    inp = CI / g["1"]["inputs"]["file"]; up = g["4"]["inputs"]; sc = up["scale"]; JOBS[pid] = {"state": "running", "inn": frames(inp)}
    blocks = 6 if not SLOW["on"] else 200
    for i in range(1, blocks + 1):
        if JOBS[pid].get("stop"):
            JOBS[pid] = {"state": "error", "msg": "Processing interrupted"}; EVENTS.append("interrupted"); return
        ws_send(cid, {"type": "progress", "data": {"value": i, "max": blocks, "prompt_id": pid, "node": "4"}}); time.sleep(0.5)
    out = CO / "spektronautilus" / f"upscaled_{pid[:6]}_.mp4"
    ff("-i", str(inp), "-vf", f"scale=iw*{sc}:ih*{sc}:flags=lanczos", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out))
    JOBS[pid] = {"state": "done", "file": out.name}
class C(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a): pass
    def js(self, o, code=200):
        b = json.dumps(o).encode(); self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(u.query)
        if u.path == "/ws":
            key = self.headers["Sec-WebSocket-Key"]; acc = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            self.send_response(101); self.send_header("Upgrade", "websocket"); self.send_header("Connection", "Upgrade"); self.send_header("Sec-WebSocket-Accept", acc); self.end_headers(); self.wfile.flush()
            WS[q["clientId"][0]] = self.connection; ws_send(q["clientId"][0], {"type": "status", "data": {}})
            try:
                while self.connection.recv(1024): pass
            except Exception: pass
            return
        if u.path == "/object_info/ReCaVSRUpscale": return self.js({"ReCaVSRUpscale": {"input": {}}})
        if u.path == "/object_info/ReCaVSRLoader": return self.js({"ReCaVSRLoader": {"input": {"required": {"transformer": [["transformer.safetensors", "transformer_int8_convrot.safetensors"], {}]}}}})
        if u.path.startswith("/history/"):
            pid = u.path.split("/")[-1]; j = JOBS.get(pid)
            if not j or j["state"] == "running": return self.js({})
            if j["state"] == "error": return self.js({pid: {"status": {"status_str": "error", "completed": False, "messages": [["execution_error", {"exception_message": j["msg"]}]]}, "outputs": {}}})
            return self.js({pid: {"status": {"status_str": "success", "completed": True}, "outputs": {"6": {"images": [{"filename": j["file"], "subfolder": "spektronautilus", "type": "output"}], "animated": [True]}}}})
        if u.path == "/view":
            p = CO / q["subfolder"][0] / q["filename"][0]; b = p.read_bytes(); self.send_response(200); self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b); return
        self.js({}, 404)
    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0); body = self.rfile.read(n)
        if self.path == "/upload/image":
            m = re.search(rb'name="image"; filename="([^"]+)"\r\nContent-Type: [^\r]+\r\n\r\n', body); name = m.group(1).decode()
            end = body.rindex(b"\r\n--"); (CI / name).write_bytes(body[m.end():end]); return self.js({"name": name, "subfolder": "", "type": "input"})
        if self.path == "/prompt":
            d = json.loads(body); g = d["prompt"]; GRAPHS.append(g)
            if g["4"]["class_type"] != "ReCaVSRUpscale" or g["3"]["class_type"] != "ReCaVSRLoader" or g["1"]["class_type"] != "LoadVideo": return self.js({"error": {"message": "bad graph"}, "node_errors": {}}, 400)
            pid = os.urandom(8).hex(); threading.Thread(target=run_job, args=(pid, g, d.get("client_id")), daemon=True).start(); return self.js({"prompt_id": pid, "number": 1})
        if self.path == "/interrupt":
            EVENTS.append("interrupt")
            for j in JOBS.values(): j["stop"] = True
            return self.js({})
        if self.path == "/queue": EVENTS.append("queue " + body.decode()); return self.js({})
        self.js({}, 404)
comfy = http.server.ThreadingHTTPServer(("127.0.0.1", 0), C); comfy.daemon_threads = True; threading.Thread(target=comfy.serve_forever, daemon=True).start()
CURL = f"http://127.0.0.1:{comfy.server_port}"

# ---------------------------------------------------------------- the package
r = subprocess.run([sys.executable, str(HERE / "build.py")], capture_output=True, text=True); check(r.returncode == 0, "the package builds: " + (r.stdout + r.stderr).strip()[-120:])
with tarfile.open(HERE / "dist/spektronautilus-nvidia.tar.gz") as t: t.extractall(T / "pkg", filter="data")
P = T / "pkg/spektronautilus-nvidia"
check(all((P / f).exists() for f in ("install.sh", "uninstall.sh", "README.md", "app/spektronautilus_nvidia.py", "app/spektronautilus.py", "app/docs/tools/hospital/index.html")), "the package has the installer, the program and the website")
r = subprocess.run(["bash", "-n", str(P / "install.sh")], capture_output=True, text=True); check(r.returncode == 0, "install.sh has no syntax errors " + r.stderr[:100])
ff("-f", "lavfi", "-i", "color=c=black:s=160x90:r=25:d=2,geq=lum='128+90*sin(2*PI*(X/40+T/2))':cb=128:cr=128", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(T / "loop.mp4"))
N = frames(T / "loop.mp4")

PORT = 8793
env = {**os.environ, "SPEKTRO_COMFYUI": CURL, "SPEKTRO_COMFYUI_START": "0", "XDG_CONFIG_HOME": str(T / "cfg")}
srv = subprocess.Popen([sys.executable, str(P / "app/spektronautilus_nvidia.py"), "--no-browser", "--port", str(PORT)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
try:
    B = f"http://127.0.0.1:{PORT}"
    for _ in range(50):
        try: urllib.request.urlopen(urllib.request.Request(B + "/api/ping", headers={"X-Spk": "1"}), timeout=1); break
        except Exception: time.sleep(0.2)
    get = lambda p, h={"X-Spk": "1"}: json.loads(urllib.request.urlopen(urllib.request.Request(B + p, headers=h), timeout=10).read())
    i = get("/api/comfy"); check(i["ok"] and "transformer_int8_convrot.safetensors" in i["models"], f"ComfyUI with ReCaVSR is found: {i}")
    try: urllib.request.urlopen(urllib.request.Request(B + "/api/comfy", headers={"X-Spk": "0"}), timeout=5); code = 200
    except urllib.error.HTTPError as e: code = e.code
    check(code == 403, "the ComfyUI address is protected like the rest of the local API")
    check(get("/api/native")["ok"], "the normal local engine (ffmpeg) works as in the Linux version")

    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_context(viewport={"width": 1100, "height": 900}).new_page(); errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.goto(B + "/tools/hospital/index.html"); pg.wait_for_selector("#picker", state="attached")
        pg.wait_for_function("HOSP.engine.comfy && HOSP.engine.comfy.ok", timeout=15000)
        pg.set_input_files("#picker", str(T / "loop.mp4")); pg.wait_for_selector("#facts span:not(.muted)", timeout=60000)
        pg.click("[data-tile=up]")
        opt = pg.locator("[data-s=up][data-k=engine][value=recavsr]")
        check(opt.count() == 1 and opt.locator("xpath=..").is_visible(), "Upscale offers 'AI video (ReCaVSR)'")
        pg.check("[data-s=up][data-k=engine][value=recavsr]"); pg.check("[data-s=up][data-k=scale][value='4']")
        seen = []
        pg.click("#go")
        for _ in range(400):
            w = pg.evaluate("document.querySelector('#bar i').style.width"); seen.append(w)
            if pg.locator("#res a").count(): break
            pg.wait_for_timeout(150)
        check(pg.locator("#res a").count() == 1, f"a clip is made: {pg.inner_text('#msg')[:200]!r}")
        note = pg.inner_text("#res"); check("ReCaVSR" in note and "loop seam kept" in note, f"the result says ReCaVSR and the kept seam: {note[:160]!r}")
        g = GRAPHS[-1]["4"]["inputs"]
        check(g["scale"] == 4 and g["decoder"] == "flashdecoder" and g["kernels"] == "fast" and GRAPHS[-1]["3"]["inputs"]["transformer"] == "transformer_int8_convrot.safetensors",
              f"the workflow: 4x, FlashDecoder, fast kernels, the int8 model: {g}")
        ins = sorted(CI.glob("*.mp4"), key=lambda p: p.stat().st_mtime)
        check(frames(ins[-1]) == 2 * N, f"for the seam the clip went to ComfyUI twice in a row ({frames(ins[-1])} frames for a {N}-frame clip)")
        href = pg.evaluate("document.querySelector('#res a').href"); data = pg.evaluate("async h => { const r = await fetch(h); const u = new Uint8Array(await r.arrayBuffer()); let s = ''; for (let i = 0; i < u.length; i += 0x8000) s += String.fromCharCode.apply(null, u.subarray(i, i + 0x8000)); return btoa(s); }", href)
        out = T / "out.mp4"; out.write_bytes(base64.b64decode(data)); w, h = size(out)
        check((w, h) == (640, 360), f"the result is 4x bigger: {w}x{h}")
        check(abs(frames(out) - N) <= 1, f"and as long as the original (second round kept): {frames(out)} frames, the original {N}")
        nums = [float(x.rstrip('%')) for x in seen if x and x.endswith('%')]
        check(len(set(round(x) for x in nums if 0 < x < 100)) >= 3, f"the bar moves while ComfyUI works (progress from its websocket): {sorted(set(round(x) for x in nums))[:12]}")
        # Stop also stops ComfyUI
        SLOW["on"] = True; EVENTS.clear()
        pg.click("#go"); pg.wait_for_timeout(4000); pg.click("#stop"); pg.wait_for_timeout(2500)
        check("interrupt" in EVENTS, f"Stop also stops the job in ComfyUI: {EVENTS}")
        pg.wait_for_function("document.querySelector('#stop').classList.contains('hide')", timeout=15000); check(True, "the page is free again after Stop")
        SLOW["on"] = False
        check(not errs, f"no script errors {errs[:2]}")
        b.close()
finally:
    srv.terminate(); srv.wait(10)

# the normal Linux version does not show the ReCaVSR choice
srv2 = subprocess.Popen([sys.executable, str(P / "app/spektronautilus.py"), "--no-browser", "--port", "8794", "--docs", str(P / "app/docs")], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env={**os.environ, "XDG_CONFIG_HOME": str(T / "cfg2")})
try:
    time.sleep(1.5)
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(); pg.goto("http://127.0.0.1:8794/tools/hospital/index.html"); pg.wait_for_selector("#picker", state="attached"); pg.wait_for_timeout(1500)
        pg.set_input_files("#picker", str(T / "loop.mp4")); pg.wait_for_selector("#facts span:not(.muted)", timeout=60000); pg.click("[data-tile=up]")
        check(pg.locator("[data-s=up][data-k=engine][value=recavsr]").locator("xpath=..").is_hidden(), "the normal Linux version does not show 'AI video (ReCaVSR)'")
        b.close()
finally:
    srv2.terminate(); srv2.wait(10)
print("\nALL OK" if not bad else f"\n{len(bad)} FAILED"); raise SystemExit(1 if bad else 0)
