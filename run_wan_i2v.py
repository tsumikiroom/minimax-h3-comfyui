"""Wan 2.2 I2V(A14B 2段MoE) 実行ランナー — MiniMax H3 との同条件比較用。

構成: GGUF Q8 の high/low 2段 + LightX2V 4step LoRA(high/low 各1.0)、
euler / simple / cfg 1.0 / shift 5.0、KSamplerAdvanced の2段リレー(0-2step, 2-4step)。
H3 との対応: 同じ入力画像・同趣旨プロンプト(音声行なし)・640×640・約5秒(81f @16fps)。

使い方:
    python run_wan_i2v.py [length=81] [width=640] [height=640]
"""
import json
import sys
import urllib.request

SERVER = "http://127.0.0.1:8000"
IMAGE = "Cityscape_NY.jpg"

LENGTH = int(sys.argv[1]) if len(sys.argv) > 1 else 81   # 4n+1、81f @16fps = 5.06秒
WIDTH = int(sys.argv[2]) if len(sys.argv) > 2 else 640
HEIGHT = int(sys.argv[3]) if len(sys.argv) > 3 else 640
SEED = 12345
FPS = 16.0
STEPS_TOTAL = 4
SWITCH_AT = 2   # high: 0-2, low: 2-4
SHIFT = 5.0

# サブフォルダ区切りは Windows の ComfyUI ではバックスラッシュ。
# Q8×2(計30.8GB)は物理RAM 31.7GB を超えガーディアンにキルされた(2026-08-10)。Q4_K_M×2 で運用。
HIGH = "WAN\\Wan2.2-I2V-A14B-HighNoise-Q4_K_M.gguf"
LOW = "WAN\\Wan2.2-I2V-A14B-LowNoise-Q4_K_M.gguf"
LORA_HIGH = "wan2.2_i2v_A14b_high_noise_lora_rank64_lightx2v_4step_1022.safetensors"
LORA_LOW = "wan2.2_i2v_A14b_low_noise_lora_rank64_lightx2v_4step_1022.safetensors"

PROMPT = (
    "A cinematic view of the city skyline at dusk. The camera slowly pushes in as "
    "lights flicker on across the buildings and thin clouds drift past."
)
NEGATIVE = "static, blurry, low quality, distorted, watermark"

workflow = {
    # 共通
    "1": {"class_type": "CLIPLoader", "inputs": {
        "clip_name": "umt5_xxl_fp8_e4m3fn_scaled.safetensors", "type": "wan",
        "device": "default"}},
    "2": {"class_type": "VAELoader", "inputs": {"vae_name": "Wan2_1_VAE_bf16.safetensors"}},
    "3": {"class_type": "CLIPTextEncode", "inputs": {"text": PROMPT, "clip": ["1", 0]}},
    "4": {"class_type": "CLIPTextEncode", "inputs": {"text": NEGATIVE, "clip": ["1", 0]}},
    "5": {"class_type": "LoadImage", "inputs": {"image": IMAGE}},
    "6": {"class_type": "ImageScale", "inputs": {
        "image": ["5", 0], "upscale_method": "lanczos",
        "width": WIDTH, "height": HEIGHT, "crop": "center"}},
    "7": {"class_type": "WanImageToVideo", "inputs": {
        "positive": ["3", 0], "negative": ["4", 0], "vae": ["2", 0],
        "width": WIDTH, "height": HEIGHT, "length": LENGTH, "batch_size": 1,
        "start_image": ["6", 0]}},
    # high-noise 段
    "10": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": HIGH}},
    "11": {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["10", 0], "lora_name": LORA_HIGH, "strength_model": 1.0}},
    "12": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["11", 0], "shift": SHIFT}},
    "13": {"class_type": "KSamplerAdvanced", "inputs": {
        "model": ["12", 0], "add_noise": "enable", "noise_seed": SEED,
        "steps": STEPS_TOTAL, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
        "positive": ["7", 0], "negative": ["7", 1], "latent_image": ["7", 2],
        "start_at_step": 0, "end_at_step": SWITCH_AT,
        "return_with_leftover_noise": "enable"}},
    # low-noise 段
    "20": {"class_type": "UnetLoaderGGUF", "inputs": {"unet_name": LOW}},
    "21": {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": ["20", 0], "lora_name": LORA_LOW, "strength_model": 1.0}},
    "22": {"class_type": "ModelSamplingSD3", "inputs": {"model": ["21", 0], "shift": SHIFT}},
    "23": {"class_type": "KSamplerAdvanced", "inputs": {
        "model": ["22", 0], "add_noise": "disable", "noise_seed": SEED,
        "steps": STEPS_TOTAL, "cfg": 1.0, "sampler_name": "euler", "scheduler": "simple",
        "positive": ["7", 0], "negative": ["7", 1], "latent_image": ["13", 0],
        "start_at_step": SWITCH_AT, "end_at_step": STEPS_TOTAL,
        "return_with_leftover_noise": "disable"}},
    # 出力
    "30": {"class_type": "VAEDecode", "inputs": {"samples": ["23", 0], "vae": ["2", 0]}},
    "31": {"class_type": "CreateVideo", "inputs": {"images": ["30", 0], "fps": FPS}},
    "32": {"class_type": "SaveVideo", "inputs": {
        "video": ["31", 0],
        "filename_prefix": f"video/WAN22_i2v_f{LENGTH}_lightx2v_q4km",
        "format": "auto", "codec": "auto"}},
}

# 投入前ゲート(run_i2v.py と同一の値)
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

body = json.dumps({"prompt": workflow, "client_id": "wan-i2v"}).encode()
req = urllib.request.Request(f"{SERVER}/prompt", data=body,
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    print(f"WAN22 i2v {WIDTH}x{HEIGHT} f{LENGTH} lightx2v 4step")
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
