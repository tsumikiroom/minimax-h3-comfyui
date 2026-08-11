"""Wan 2.2 TI2V-5B の I2V 実行ランナー — H3 との「この機で成立する土俵」比較用。

背景: A14B は Q4×2 でもロード段階で物理RAM枯渇(2026-08-11、results.md 参照)。
5B は単段・fp16 10GB で、この機の物理RAMに収まる機体相応の WAN。

公式ワークフロー準拠: shift 8.0 / uni_pc / 20 steps / cfg 5.0。
native 24fps なので 121f = 5.04秒(H3 の 124f@24fps=5.17秒とほぼ同尺)。

使い方:
    python run_wan5b_i2v.py [length=121] [width=640] [height=640] [steps=20]
"""
import json
import sys
import urllib.request

SERVER = "http://127.0.0.1:8000"
IMAGE = "Cityscape_NY.jpg"

LENGTH = int(sys.argv[1]) if len(sys.argv) > 1 else 121   # step=4 → 4n+1、121f @24fps = 5.04秒
WIDTH = int(sys.argv[2]) if len(sys.argv) > 2 else 640
HEIGHT = int(sys.argv[3]) if len(sys.argv) > 3 else 640
STEPS = int(sys.argv[4]) if len(sys.argv) > 4 else 20
SEED = 12345
FPS = 24.0
SHIFT = 8.0

PROMPT = (
    "A cinematic view of the city skyline at dusk. The camera slowly pushes in as "
    "lights flicker on across the buildings and thin clouds drift past."
)
NEGATIVE = "static, blurry, low quality, distorted, watermark"

workflow = {
    "1": {"class_type": "UNETLoader", "inputs": {
        "unet_name": "wan2.2_ti2v_5B_fp16.safetensors", "weight_dtype": "default"}},
    "2": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["1", 0], "shift": SHIFT}},
    "3": {"class_type": "CLIPLoader", "inputs": {
        "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan",
        "device": "default"}},
    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["3", 0]}},
    "5": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["3", 0]}},
    "6": {"class_type": "VAELoader", "inputs": {"vae_name": "wan2.2_vae.safetensors"}},
    "7": {"class_type": "LoadImage", "inputs": {"image": IMAGE}},
    "8": {"class_type": "ImageScale", "inputs": {
        "image": ["7", 0], "upscale_method": "lanczos",
        "width": WIDTH, "height": HEIGHT, "crop": "center"}},
    "9": {"class_type": "Wan22ImageToVideoLatent", "inputs": {
        "vae": ["6", 0], "width": WIDTH, "height": HEIGHT, "length": LENGTH,
        "batch_size": 1, "start_image": ["8", 0]}},
    "10": {"class_type": "KSampler", "inputs": {
        "model": ["2", 0], "seed": SEED, "steps": STEPS, "cfg": 5.0,
        "sampler_name": "uni_pc", "scheduler": "simple",
        "positive": ["4", 0], "negative": ["5", 0],
        "latent_image": ["9", 0], "denoise": 1.0}},
    "11": {"class_type": "VAEDecode", "inputs": {"samples": ["10", 0], "vae": ["6", 0]}},
    "12": {"class_type": "CreateVideo", "inputs": {"images": ["11", 0], "fps": FPS}},
    "13": {"class_type": "SaveVideo", "inputs": {
        "video": ["12", 0],
        "filename_prefix": f"video/WAN22_5B_i2v_f{LENGTH}_s{STEPS}",
        "format": "auto", "codec": "auto"}},
}

# 投入前ゲート
MIN_AVAIL_GB = 6.0
MIN_COMMIT_HEADROOM_GB = 24.0
try:
    import ctypes
    import os

    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    ms = MEMORYSTATUSEX()
    ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    avail_gb = ms.ullAvailPhys / 2**30
    headroom_gb = ms.ullAvailPageFile / 2**30
    ballast_gb = 0.0
    try:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                               "airbag.status"), encoding="utf-8") as f:
            ballast_gb = float(f.read().strip())
    except Exception:
        pass
    headroom_gb += ballast_gb
    print(f"pre-flight: avail={avail_gb:.1f} GB, commit headroom={headroom_gb:.1f} GB"
          f" (うちバラスト {ballast_gb:.0f} GB)")
    if avail_gb < MIN_AVAIL_GB or headroom_gb < MIN_COMMIT_HEADROOM_GB:
        print("ABORT: 投入前ゲート不通過。/free するか OS 再起動", file=sys.stderr)
        sys.exit(2)
except Exception as e:
    print(f"pre-flight check failed ({e}) — ゲート無しで続行", file=sys.stderr)

body = json.dumps({"prompt": workflow, "client_id": "wan5b-i2v"}).encode()
req = urllib.request.Request(f"{SERVER}/prompt", data=body,
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    print(f"WAN22 5B i2v {WIDTH}x{HEIGHT} f{LENGTH} s{STEPS}")
    print("prompt_id:", res.get("prompt_id"))
    if res.get("node_errors"):
        print("node_errors:", json.dumps(res["node_errors"], ensure_ascii=False, indent=1))
except urllib.error.HTTPError as e:
    detail = e.read().decode("utf-8", "replace")
    print("HTTP", e.code, file=sys.stderr)
    try:
        print(json.dumps(json.loads(detail), ensure_ascii=False, indent=1), file=sys.stderr)
    except Exception:
        print(detail, file=sys.stderr)
    sys.exit(1)
