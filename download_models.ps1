# MiniMax H3 モデル取得(16GB VRAM / 32GB RAM 向けの最小構成、計 約42.5GB)
# 中断しても再実行で再開できる。

$ErrorActionPreference = "Stop"

$Hf     = "C:\Dev\ComfyUI_app\.venv\Scripts\hf.exe"
$Models = "C:\Dev\ComfyUI_app\models"
$Repo   = "Comfy-Org/MiniMax-H3"

if (-not (Test-Path $Hf))     { throw "hf CLI が見つからない: $Hf" }
if (-not (Test-Path $Models)) { throw "models ディレクトリが見つからない: $Models" }

# 転送高速化(未導入なら無視される)
$env:HF_HUB_ENABLE_HF_TRANSFER = "1"

$files = @(
    @{ src = "diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors"; dst = "diffusion_models" },
    @{ src = "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors";      dst = "text_encoders"    },
    @{ src = "vae/minimax_h3_video_vae_fp16.safetensors";                       dst = "vae"              },
    @{ src = "vae/minimax_h3_audio_vae_fp32.safetensors";                       dst = "vae"              }
)

foreach ($f in $files) {
    $name = Split-Path $f.src -Leaf
    $out  = Join-Path (Join-Path $Models $f.dst) $name
    if (Test-Path $out) {
        Write-Host "skip (既存): $name"
        continue
    }
    Write-Host "downloading: $name"
    # hf はリポジトリ内のサブフォルダ構造を保って落とすので、いったん models 直下に落として引き上げる
    & $Hf download $Repo $f.src --local-dir $Models
    $nested = Join-Path $Models ($f.src -replace "/", "\")
    if (Test-Path $nested) {
        if ($nested -ne $out) { Move-Item $nested $out -Force }
    } else {
        throw "ダウンロード後にファイルが見つからない: $nested"
    }
}

Write-Host ""
Write-Host "完了。配置を確認:"
foreach ($f in $files) {
    $out = Join-Path (Join-Path $Models $f.dst) (Split-Path $f.src -Leaf)
    $ok  = if (Test-Path $out) { "OK  " } else { "MISS" }
    $gb  = if (Test-Path $out) { "{0:N1} GB" -f ((Get-Item $out).Length / 1GB) } else { "-" }
    Write-Host ("  [{0}] {1}  {2}" -f $ok, $out, $gb)
}
