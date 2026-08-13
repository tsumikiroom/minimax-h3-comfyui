"""MiniMax H3 i2v 検証ランナー(低解像度 + Turbo LoRA + EasyCache)。

3060機で実証済みの構成(https://x.com/TlanoAI/status/2084940455809286397)をこの機に移植したもの。
使い方:
    python run_i2v.py <length> <steps> [lora=1] [easycache=1] [sampler=euler]
例:
    python run_i2v.py 124 4              # Turbo LoRA + EasyCache、euler
    python run_i2v.py 124 25 0 1 res_multistep   # LoRA無し25steps(記事構成の再現)
"""
import json
import os
import sys
import urllib.request

SERVER = "http://127.0.0.1:8000"
# H3_IMAGE 環境変数で入力画像を差し替え。"none" で first_frame 無し = T2V
# (公式 t2v テンプレートも同じノードで first_frame を繋がないだけ)
IMAGE = os.environ.get("H3_IMAGE", "Cityscape_NY.jpg")
WIDTH, HEIGHT = 640, 640          # 記事の I2V 解像度
FPS = 24.0
# 既定 LoRA: 2026-08-10 の同シード比較で音・動き・ディテールすべて最良だった Kijai LightX2V 蒸留。
# 推奨 strength 0.75 / sampler er_sde(比較の敗者: drbaph v1 ckpt500, v4_step600)
LORA = "minimax_h3_fl2v_lightx2v_turbo_4step_v0.1_comfy.safetensors"
SEED = 12345

LENGTH = int(sys.argv[1]) if len(sys.argv) > 1 else 124
# steps は2段構え: ドラフト4 / キープ級は同シードで8(暗部×激しい動きの格子ノイズが8で消える。
# 2026-08-14 A/B/C比較: steps8=消滅, sa_solver=大幅軽減, strength0.6=効果なし)
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 4
USE_LORA = bool(int(sys.argv[3])) if len(sys.argv) > 3 else True
USE_EASYCACHE = bool(int(sys.argv[4])) if len(sys.argv) > 4 else False  # 4steps では予測置換リスク>節約
SAMPLER = sys.argv[5] if len(sys.argv) > 5 else "sa_solver"  # er_sde より格子ノイズ耐性が高い
LAST_IMAGE = sys.argv[6] if len(sys.argv) > 6 else None   # 指定すると flf2v になる("-" でスキップ)
if LAST_IMAGE == "-":
    LAST_IMAGE = None
LORA = sys.argv[7] if len(sys.argv) > 7 else LORA          # LoRA ファイル差し替え
LORA_STRENGTH = float(sys.argv[8]) if len(sys.argv) > 8 else 0.75

PROMPT = os.environ.get("H3_PROMPT") or (
    "A cinematic view of the city skyline at dusk. The camera slowly pushes in as "
    "lights flicker on across the buildings and thin clouds drift past. "
    "Audio: distant city ambience, low traffic hum, a faint breeze."
)

workflow = {
    "1": {"class_type": "UNETLoader", "inputs": {
        "unet_name": "minimax_h3_fl2va_pruned_fp8_scaled.safetensors",
        "weight_dtype": "default"}},
    "2": {"class_type": "CLIPLoader", "inputs": {
        "clip_name": "qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors",
        "type": "minimax", "device": "default"}},
    "3": {"class_type": "VAELoader", "inputs": {
        "vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
    "4": {"class_type": "VAELoader", "inputs": {
        "vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
    "7": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
        "clip": ["2", 0], "vae": ["3", 0], "prompt": PROMPT,
        "width": WIDTH, "height": HEIGHT, "length": LENGTH}},
}

if IMAGE.lower() != "none":  # i2v: first_frame を接続。"none" なら T2V
    workflow["5"] = {"class_type": "LoadImage", "inputs": {"image": IMAGE}}
    workflow["6"] = {"class_type": "ImageScale", "inputs": {
        "image": ["5", 0], "upscale_method": "lanczos",
        "width": WIDTH, "height": HEIGHT, "crop": "center"}}
    workflow["7"]["inputs"]["first_frame"] = ["6", 0]

if LAST_IMAGE:
    workflow["30"] = {"class_type": "LoadImage", "inputs": {"image": LAST_IMAGE}}
    workflow["31"] = {"class_type": "ImageScale", "inputs": {
        "image": ["30", 0], "upscale_method": "lanczos",
        "width": WIDTH, "height": HEIGHT, "crop": "center"}}
    workflow["7"]["inputs"]["last_frame"] = ["31", 0]

workflow.update({
    "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": SEED}},
    "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": SAMPLER}},
    "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
    "14": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
    "15": {"class_type": "CreateVideo", "inputs": {
        "images": ["13", 0], "audio": ["14", 0], "fps": FPS}},
})

# モデルチェーン: UNETLoader -> (LoRA) -> (EasyCache) -> Guider/Scheduler
model_ref = ["1", 0]
if USE_LORA:
    workflow["20"] = {"class_type": "LoraLoaderModelOnly", "inputs": {
        "model": model_ref, "lora_name": LORA, "strength_model": LORA_STRENGTH}}
    model_ref = ["20", 0]
if USE_EASYCACHE:
    workflow["21"] = {"class_type": "EasyCache", "inputs": {
        "model": model_ref, "reuse_threshold": 0.3,
        "start_percent": 0.2, "end_percent": 0.9, "verbose": True}}
    model_ref = ["21", 0]

workflow["9"] = {"class_type": "BasicGuider", "inputs": {
    "model": model_ref, "conditioning": ["7", 0]}}
workflow["11"] = {"class_type": "BasicScheduler", "inputs": {
    "model": model_ref, "scheduler": "simple", "steps": STEPS, "denoise": 1.0}}
workflow["12"] = {"class_type": "SamplerCustomAdvanced", "inputs": {
    "noise": ["8", 0], "guider": ["9", 0], "sampler": ["10", 0],
    "sigmas": ["11", 0], "latent_image": ["7", 1]}}

tag = f"f{LENGTH}_s{STEPS}_{'lora' if USE_LORA else 'nolora'}_{'ec' if USE_EASYCACHE else 'noec'}_{SAMPLER}"
if USE_LORA:
    lid = LORA.replace("minimax_h3_", "").replace("_pruned_comfyui", "").replace(".safetensors", "")
    tag += f"_{lid[:28]}_st{LORA_STRENGTH:g}"
if LAST_IMAGE:
    tag += "_flf2v"
img_id = "t2v" if IMAGE.lower() == "none" else os.path.splitext(os.path.basename(IMAGE))[0][:16]
tag += f"_{img_id}"
workflow["16"] = {"class_type": "SaveVideo", "inputs": {
    "video": ["15", 0], "filename_prefix": f"video/MiniMax_H3_{tag}",
    "format": "auto", "codec": "auto"}}

# 投入前ゲート: 2026-08-07 のシステムクラッシュ(ページングロック→強制電源断)を受けて追加。
# 事後型ウォッチドッグはロック時に無力なので、投入前に物理メモリの余裕を確認する。
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
    # ガーディアン(killswitch.py)が保持するバラストは危機時に即時解放されるので
    # 実効余裕として数える(airbag.status に保持GBが書かれている)
    import os
    ballast_gb = 0.0
    status_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "airbag.status")
    try:
        with open(status_path, encoding="utf-8") as f:
            ballast_gb = float(f.read().strip())
    except Exception:
        pass
    headroom_gb += ballast_gb
    print(f"pre-flight: avail={avail_gb:.1f} GB, commit headroom={headroom_gb:.1f} GB"
          f" (うちバラスト {ballast_gb:.0f} GB)")
    if avail_gb < MIN_AVAIL_GB or headroom_gb < MIN_COMMIT_HEADROOM_GB:
        print(f"ABORT: 投入前ゲート不通過 (要 avail>={MIN_AVAIL_GB}, headroom>={MIN_COMMIT_HEADROOM_GB})",
              file=sys.stderr)
        print("対処: curl -X POST http://127.0.0.1:8000/free -H 'Content-Type: application/json'"
              " -d '{\"unload_models\":true,\"free_memory\":true}' を実行してから再試行。"
              "それでも不足なら OS 再起動。", file=sys.stderr)
        sys.exit(2)
except Exception as e:  # ゲート自体の失敗で投入を止めない(ただし警告は出す)
    print(f"pre-flight check failed ({e}) — ゲート無しで続行", file=sys.stderr)

body = json.dumps({"prompt": workflow, "client_id": "i2v-test"}).encode()
req = urllib.request.Request(f"{SERVER}/prompt", data=body,
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
    print(f"{tag} {WIDTH}x{HEIGHT}")
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
