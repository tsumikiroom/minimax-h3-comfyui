"""MiniMax H3 R2V(reference-to-video) ランナー — モーション参照実験。

ref2va モデルは参照動画(最大3本)から「モーション/カメラムーブ」を抽出できる
(公式: https://docs.comfy.org/tutorials/video/minimax/minimax-h3)。
TD 製マスク動画を <Video 1> として渡し、動きだけを転写させる。

使い方:
    python run_r2v.py [ref_video=mask_movieout22.mp4] [steps=8] [length=124] [lora=1]
注意: fl2v 用 turbo LoRA の ref2va への転用は未検証。壊れたら lora=0 + steps 20 で。
"""
import json
import os
import sys
import urllib.request

SERVER = "http://127.0.0.1:8000"

REF_VIDEO = sys.argv[1] if len(sys.argv) > 1 else "mask_movieout22.mp4"
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 8
LENGTH = int(sys.argv[3]) if len(sys.argv) > 3 else 124
USE_LORA = bool(int(sys.argv[4])) if len(sys.argv) > 4 else True
SEED = 12345
WIDTH, HEIGHT = 640, 640
LORA = "minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors"

PROMPT = os.environ.get("H3_PROMPT") or (
    "A single compact blob of glossy orange and blue marbled paint moves through pure "
    "black empty space, following exactly the motion path, speed and timing of <Video 1>. "
    "Use <Video 1> strictly as a motion reference only: its flat white-on-black graphic "
    "look must not influence the visual style. The blob stays a rich glossy 3D liquid "
    "with vivid colors, fully contained in the frame. Fixed camera, pure black background. "
    "Audio: soft fluid whooshes following the movement."
)

workflow = {
    "1": {"class_type": "UNETLoader", "inputs": {
        "unet_name": "minimax_h3_ref2va_pruned_fp8_scaled.safetensors",
        "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {
        "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "type": "minimax", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {
        "vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
    "4": {"class_type": "VAELoader", "inputs": {
        "vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
    "40": {"class_type": "LoadVideo", "inputs": {"file": REF_VIDEO}},
    "41": {"class_type": "GetVideoComponents", "inputs": {"video": ["40", 0]}},
    "7": {"class_type": "MiniMaxH3ReferenceToVideo", "inputs": {
        "clip": ["2", 0], "vae": ["3", 0], "audio_vae": ["4", 0],
        "prompt": PROMPT, "width": WIDTH, "height": HEIGHT, "length": LENGTH,
        "ref_image_size": "match",
        "ref_videos.ref_video_0": ["41", 0]}},
}

# H3_REF_IMAGE 環境変数でルック供給用の参照画像を追加(<Picture 1> としてタグ参照)
REF_IMAGE = os.environ.get("H3_REF_IMAGE")
if REF_IMAGE:
    workflow["42"] = {"class_type": "LoadImage", "inputs": {"image": REF_IMAGE}}
    workflow["7"]["inputs"]["ref_images.ref_image_0"] = ["42", 0]

workflow.update({
    "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": SEED}},
    "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "sa_solver"}},
    "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
    "14": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
    "15": {"class_type": "CreateVideo", "inputs": {
        "images": ["13", 0], "audio": ["14", 0], "fps": 24.0}},
})

model_ref = ["1", 0]
if USE_LORA:
    workflow["20"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": model_ref, "lora_name": LORA, "strength_model": 0.75}}
    model_ref = ["20", 0]

workflow["9"] = {"class_type": "BasicGuider", "inputs": {
    "model": model_ref, "conditioning": ["7", 0]}}
workflow["11"] = {"class_type": "BasicScheduler", "inputs": {
    "model": model_ref, "scheduler": "simple", "steps": STEPS, "denoise": 1.0}}
workflow["12"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
    "noise": ["8", 0], "guider": ["9", 0], "sampler": ["10", 0],
    "sigmas": ["11", 0], "latent_image": ["7", 1]}}

tag = f"r2v_f{LENGTH}_s{STEPS}_{'lora' if USE_LORA else 'nolora'}_{os.path.splitext(REF_VIDEO)[0][:20]}"
workflow["16"] = {"class_type": "SaveVideo", "inputs": {
    "video": ["15", 0], "filename_prefix": f"video/MiniMax_H3_{tag}",
    "format": "auto", "codec": "auto"}}

# 投入前ゲート
MIN_AVAIL_GB = 6.0
MIN_COMMIT_HEADROOM_GB = 24.0
try:
    import ctypes

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
    print(f"pre-flight: avail={avail_gb:.1f} GB, headroom={headroom_gb:.1f} GB (バラスト {ballast_gb:.0f})")
    if avail_gb < MIN_AVAIL_GB or headroom_gb < MIN_COMMIT_HEADROOM_GB:
        print("ABORT: ゲート不通過。/free か再起動を", file=sys.stderr)
        sys.exit(2)
except Exception as e:
    print(f"pre-flight failed ({e}) — 続行", file=sys.stderr)

body = json.dumps({"prompt": workflow, "client_id": "r2v-test"}).encode()
req = urllib.request.Request(f"{SERVER}/prompt", data=body,
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    print(tag)
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
