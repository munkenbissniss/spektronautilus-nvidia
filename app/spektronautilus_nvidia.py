#!/usr/bin/env python3
"""Spektronautilus NVIDIA: the Linux version of Spektronautilus, plus AI video upscaling with ReCaVSR on an NVIDIA graphics card.

It starts ComfyUI (installed next to it by install.sh) in the background, and lets the Loop Hospital send clips to it.
Everything else is the normal Linux version (spektronautilus.py, which sits next to this file).

Settings (environment variables, all optional):
  SPEKTRO_COMFYUI        address of ComfyUI, default http://127.0.0.1:8188
  SPEKTRO_COMFYUI_START  0 = do not start ComfyUI (use one that is already running)
  SPEKTRO_COMFYUI_DIR    where ComfyUI is installed, default ../ComfyUI next to this program's folder
"""
import atexit, base64, json, os, re, socket, subprocess, sys, threading, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import spektronautilus as base   # noqa: E402  (the normal Linux version)

COMFY_DEFAULT = "http://127.0.0.1:8188"
HOME = HERE.parent                                   # ~/.local/share/spektronautilus-nvidia
COMFY_DIR = Path(os.environ.get("SPEKTRO_COMFYUI_DIR") or HOME / "ComfyUI")
VENV_PY = HOME / "venv" / "bin" / "python"
LOG = HOME / "comfyui.log"


def comfy_url():
    u = (os.environ.get("SPEKTRO_COMFYUI") or COMFY_DEFAULT).strip().rstrip("/")
    return u if re.match(r"^https?://[A-Za-z0-9.\-\[\]:]+$", u) else COMFY_DEFAULT


def comfy_req(path, data=None, ctype=None, timeout=15, url=None):
    h = {"Content-Type": ctype} if ctype else {}
    r = urllib.request.Request((url or comfy_url()) + path, data=data, headers=h, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(r, timeout=timeout) as x:
        return x.read()


# ---------------------------------------------------------------- starting and stopping ComfyUI
class Comfy:
    proc = None
    started = 0.0
    state = "off"          # off | starting | ready | failed

    @classmethod
    def start(cls):
        if os.environ.get("SPEKTRO_COMFYUI_START", "1") == "0":
            cls.state = "ready" if info().get("ok") else "off"; return
        if info().get("ok"):
            cls.state = "ready"; return                                     # one is already running: use it, and leave it running
        if not (COMFY_DIR / "main.py").is_file() or not VENV_PY.is_file():
            cls.state = "failed"; print("ComfyUI is not installed next to this program. Run install.sh again.", flush=True); return
        u = urllib.parse.urlparse(comfy_url())
        cls.state, cls.started = "starting", time.time()
        log = open(LOG, "ab")
        cls.proc = subprocess.Popen([str(VENV_PY), "main.py", "--listen", u.hostname or "127.0.0.1", "--port", str(u.port or 8188), "--disable-auto-launch"],
                                    cwd=COMFY_DIR, stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        atexit.register(cls.stop)
        for _ in range(600):                                                # loading the Python packages can take a minute the first time
            if cls.proc.poll() is not None:
                cls.state = "failed"; print(f"ComfyUI stopped while starting. See {LOG}", flush=True); return
            if info().get("ok"):
                cls.state = "ready"; print(f"ComfyUI is ready ({round(time.time() - cls.started)} s).", flush=True); return
            time.sleep(1)
        cls.state = "failed"; print(f"ComfyUI did not get ready. See {LOG}", flush=True)

    @classmethod
    def stop(cls):
        p, cls.proc = cls.proc, None
        if p and p.poll() is None:
            p.terminate()
            try: p.wait(10)
            except Exception: p.kill()


def info():
    out = {"url": comfy_url(), "ok": False, "state": Comfy.state}
    try: up = json.loads(comfy_req("/object_info/ReCaVSRUpscale", timeout=4))
    except Exception:
        out["why"] = "starting" if Comfy.state == "starting" else "not reachable"; return out
    if "ReCaVSRUpscale" not in up:
        out["why"] = "the ReCaVSR nodes are missing in ComfyUI"; return out
    try:
        t = json.loads(comfy_req("/object_info/ReCaVSRLoader", timeout=4))["ReCaVSRLoader"]["input"]["required"]["transformer"]
        files = t[0] if isinstance(t[0], list) else (t[1].get("options") or [])
    except Exception:
        files = []
    out["models"] = [f for f in files if isinstance(f, str)]
    if not out["models"]:
        out["why"] = "no ReCaVSR model file in ComfyUI/models/recavsr"; return out
    out["ok"] = True
    return out


def pick_model(models):
    for want in ("int8", "transformer.safetensors"):     # int8 first: 6.3 GB instead of 10.6, and faster; the one that fits a 16 GB computer
        for m in models:
            if want in m: return m
    return models[0]


def graph(name, model, scale, color_fix, kv_offload, seed=42):
    return {"1": {"class_type": "LoadVideo", "inputs": {"file": name}},
            "3": {"class_type": "ReCaVSRLoader", "inputs": {"transformer": model}},
            "4": {"class_type": "ReCaVSRUpscale", "inputs": {"model": ["3", 0], "video": ["1", 0], "scale": float(scale), "color_fix": color_fix, "seed": int(seed),
                                                            "decoder": "flashdecoder", "kernels": "fast", "kv_offload": bool(kv_offload), "encoder": "auto"}},
            "6": {"class_type": "SaveVideo", "inputs": {"video": ["4", 0], "filename_prefix": "spektronautilus/upscaled", "format": "auto", "codec": "auto"}}}


def result_files(outputs):
    for node in (outputs or {}).values():
        for v in (node or {}).values():
            if isinstance(v, list):
                for f in v:
                    if isinstance(f, dict) and f.get("filename"): yield f


def multipart(fields, fname, path):
    b = "----spk" + os.urandom(8).hex(); out = []
    for k, v in fields.items():
        out.append(f'--{b}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
    out.append(f'--{b}\r\nContent-Disposition: form-data; name="image"; filename="{fname}"\r\nContent-Type: video/mp4\r\n\r\n'.encode() + path.read_bytes() + b"\r\n")
    out.append(f"--{b}--\r\n".encode())
    return b"".join(out), "multipart/form-data; boundary=" + b


class Progress(threading.Thread):
    """Listens to ComfyUI's websocket for the progress of one job (the ReCaVSR node reports each block). Plain sockets, no extra packages."""
    def __init__(self, client_id):
        super().__init__(daemon=True); self.cid, self.p, self.pid, self.sock, self.ok = client_id, None, None, None, False

    def run(self):
        try:
            u = urllib.parse.urlparse(comfy_url()); s = socket.create_connection((u.hostname, u.port or 80), timeout=10); self.sock = s
            key = base64.b64encode(os.urandom(16)).decode()
            s.sendall((f"GET /ws?clientId={self.cid} HTTP/1.1\r\nHost: {u.hostname}:{u.port or 80}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                       f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
            head = b""
            while b"\r\n\r\n" not in head:
                c = s.recv(1); head += c
                if not c: return
            if b" 101 " not in head.split(b"\r\n")[0]: return
            self.ok = True; s.settimeout(None); rest = b""
            def need(n):
                nonlocal rest
                while len(rest) < n:
                    c = s.recv(65536)
                    if not c: raise EOFError
                    rest += c
                d, rest = rest[:n], rest[n:]; return d
            while True:
                h = need(2); op, ln = h[0] & 15, h[1] & 127
                if ln == 126: ln = int.from_bytes(need(2), "big")
                elif ln == 127: ln = int.from_bytes(need(8), "big")
                if h[1] & 128: need(4)                               # a server never masks, but be safe
                data = need(ln)
                if op == 8: return
                if op != 1: continue                                  # binary frames are preview pictures
                try: m = json.loads(data)
                except Exception: continue
                d = m.get("data") or {}
                if m.get("type") == "progress" and str(d.get("node")) == "4" and (self.pid is None or d.get("prompt_id") in (None, self.pid)) and d.get("max"):
                    self.p = max(0.0, min(1.0, d["value"] / d["max"]))
        except Exception:
            return

    def close(self):
        try: self.sock and self.sock.close()
        except Exception: pass


# ---------------------------------------------------------------- the local server: two more addresses
class State(base.State):
    def __init__(self, *a, **k):
        super().__init__(*a, **k); self.comfy_job = None

    def kill(self):
        super().kill()
        with self.lock: job, self.comfy_job = self.comfy_job, None
        if job:   # Stop also stops ComfyUI: take the job out of its queue, or interrupt it if it is the one running
            for path, body in (("/queue", {"delete": [job]}), ("/interrupt", {})):
                try: comfy_req(path, json.dumps(body).encode(), "application/json", timeout=4)
                except Exception: pass


class Handler(base.Handler):
    def do_GET(self):
        if self.path == "/api/comfy" and self._api_ok(): return self._json(info())
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/comfy-exec" and self._api_ok(): return self._comfy_exec()
        return super().do_POST()

    def _comfy_exec(self):
        """Body: {input, output, scale, colorFix, kvOffload}. Answers like /api/exec: {"p": ...} lines while it works, then {code, log}."""
        try:
            o = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
            src, dst = self.st.safe(o["input"]), self.st.safe(o["output"]); scale = float(o.get("scale", 4)); cf = o.get("colorFix", "none")
            assert 0.5 <= scale <= 8 and cf in ("none", "adain", "wavelet") and src.is_file()
        except Exception:
            return self._deny(400, "Bad request")
        self.send_response(200); self.send_header("Content-Type", "application/x-ndjson"); self.end_headers()
        log, pid, prog = [], None, None
        def say(obj): self.wfile.write((json.dumps(obj) + "\n").encode()); self.wfile.flush()
        def fail(msg): log.append(msg); say({"code": 1, "log": log[-50:]})
        try:
            i = info()
            if not i.get("ok"):
                return fail("ComfyUI with ReCaVSR is not ready (" + str(i.get("why")) + "). " + (f"See {LOG}" if Comfy.state == "failed" else "Try again in a minute."))
            name = "spektronautilus_" + os.urandom(6).hex() + ".mp4"
            body, ct = multipart({"type": "input", "overwrite": "true"}, name, src)
            up = json.loads(comfy_req("/upload/image", body, ct, timeout=600)); name = (up.get("subfolder") + "/" if up.get("subfolder") else "") + up.get("name", name)
            cid = "spektronautilus-" + os.urandom(4).hex(); prog = Progress(cid); prog.start(); time.sleep(0.2)
            try:
                r = json.loads(comfy_req("/prompt", json.dumps({"prompt": graph(name, pick_model(i["models"]), scale, cf, o.get("kvOffload")), "client_id": cid}).encode(), "application/json"))
            except urllib.error.HTTPError as e:
                try: d = json.loads(e.read()); msg = (d.get("error") or {}).get("message", "") + " " + json.dumps(d.get("node_errors") or {})[:300]
                except Exception: msg = str(e)
                return fail("ComfyUI did not accept the job: " + msg)
            pid = prog.pid = r["prompt_id"]
            with self.st.lock: self.st.comfy_job = pid
            t0, sent = time.time(), -1.0
            while True:
                time.sleep(0.5)
                with self.st.lock: active = self.st.comfy_job == pid
                if not active: return fail("Stopped.")
                if prog.p is not None and prog.p - sent >= 0.01:
                    sent = prog.p; say({"p": round(min(0.99, prog.p), 3)})
                h = json.loads(comfy_req(f"/history/{pid}")).get(pid)
                if not h: continue
                st = h.get("status") or {}
                if st.get("status_str") == "error":
                    msgs = [m[1].get("exception_message", "") for m in st.get("messages", []) if isinstance(m, list) and len(m) > 1 and isinstance(m[1], dict) and m[0] == "execution_error"]
                    err = "; ".join(x.strip() for x in msgs if x) or "see the ComfyUI log"
                    if re.search(r"out of memory|CUDA out of memory|OutOfMemory", err, re.I): err = "the graphics card ran out of memory. Choose a smaller scale, or crop / resize the clip first. (" + err[:120] + ")"
                    return fail("ReCaVSR stopped: " + err[:400])
                files = list(result_files(h.get("outputs")))
                if files:
                    f = files[0]; q = urllib.parse.urlencode({"filename": f["filename"], "subfolder": f.get("subfolder", ""), "type": f.get("type", "output")})
                    dst.parent.mkdir(parents=True, exist_ok=True); dst.write_bytes(comfy_req("/view?" + q, timeout=600))
                    log.append(f"ReCaVSR done in {round(time.time() - t0)} s"); say({"code": 0, "log": log}); return
                if st.get("completed"): return fail("ComfyUI finished, but gave no video back.")
        except (BrokenPipeError, ConnectionResetError):
            self.st.kill()
        except Exception as e:
            try: fail("ComfyUI: " + str(e)[:300])
            except Exception: pass
        finally:
            if prog: prog.close()
            with self.st.lock:
                if pid and self.st.comfy_job == pid: self.st.comfy_job = None


def main():
    base.State, base.Handler = State, Handler
    threading.Thread(target=Comfy.start, daemon=True).start()
    print("Spektronautilus NVIDIA: AI video upscaling with ReCaVSR (ComfyUI " + comfy_url() + ", starting in the background).", flush=True)
    try: base.main()
    finally: Comfy.stop()


if __name__ == "__main__":
    main()
