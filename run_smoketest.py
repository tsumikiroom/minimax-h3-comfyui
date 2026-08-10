"""MiniMax H3 i2v の最小構成スモークテスト。

公式テンプレート video_minimax_h3_i2v.json のサブグラフを API 形式に展開したもの。
テンプレートからの変更点:
  - UNETLoader     int8_convrot -> pruned_fp8_scaled (手元にあるのは fp8 のみ)
  - BasicScheduler steps 20 -> 6
  - length         73 -> 5 (ノード仕様の最小値。min=5, step=17)
  - 入力画像       テンプレート同梱アセット -> Cityscape_NY.jpg
解像度 1344x768 は据え置き(H3 の学習解像度。半端な値だと落ちうる)。
"""
import json
import sys
import urllib.request

SERVER = "http://127.0.0.1:8000"
IMAGE = "Cityscape_NY.jpg"
WIDTH, HEIGHT = 1344, 768
LENGTH = int(sys.argv[1]) if len(sys.argv) > 1 else 5  # min=5, step=17 -> 5, 22, 39, 56, 73...
STEPS = int(sys.argv[2]) if len(sys.argv) > 2 else 6
SEED = 12345

PROMPT = (
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
    "5": {"class_type": "LoadImage", "inputs": {"image": IMAGE}},
    # first_frame の解像度を width/height に合わせておく(不一致による失敗を潰す)
    "6": {"class_type": "ImageScale", "inputs": {
        "image": ["5", 0], "upscale_method": "lanczos",
        "width": WIDTH, "height": HEIGHT, "crop": "center"}},
    "7": {"class_type": "MiniMaxH3ImageToVideo", "inputs": {
        "clip": ["2", 0], "vae": ["3", 0], "prompt": PROMPT,
        "width": WIDTH, "height": HEIGHT, "length": LENGTH,
        "first_frame": ["6", 0]}},
    "8": {"class_type": "RandomNoise", "inputs": {"noise_seed": SEED}},
    "9": {"class_type": "BasicGuider", "inputs": {
        "model": ["1", 0], "conditioning": ["7", 0]}},
    "10": {"class_type": "KSamplerSelect", "inputs": {"sampler_name": "res_multistep"}},
    "11": {"class_type": "BasicScheduler", "inputs": {
        "model": ["1", 0], "scheduler": "simple", "steps": STEPS, "denoise": 1.0}},
    "12": {"class_type": "SamplerCustomAdvanced", "inputs": {
        "noise": ["8", 0], "guider": ["9", 0], "sampler": ["10", 0],
        "sigmas": ["11", 0], "latent_image": ["7", 1]}},
    "13": {"class_type": "VAEDecode", "inputs": {"samples": ["12", 0], "vae": ["3", 0]}},
    "14": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["12", 0], "vae": ["4", 0]}},
    "15": {"class_type": "CreateVideo", "inputs": {
        "images": ["13", 0], "audio": ["14", 0], "fps": 24.0}},
    "16": {"class_type": "SaveVideo", "inputs": {
        "video": ["15", 0], "filename_prefix": f"video/MiniMax_H3_f{LENGTH}_s{STEPS}",
        "format": "auto", "codec": "auto"}},
}

print(f"length={LENGTH} steps={STEPS} {WIDTH}x{HEIGHT}")

body = json.dumps({"prompt": workflow, "client_id": "smoketest"}).encode()
req = urllib.request.Request(f"{SERVER}/prompt", data=body,
                             headers={"Content-Type": "application/json"})
try:
    with urllib.request.urlopen(req, timeout=60) as r:
        res = json.load(r)
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
