# ComfyUI サーバーをヘッドレス起動する(Desktop アプリ不要)。
#
# 背景: ガーディアンがサーバー python を殺した後、Desktop はエラー画面で止まり
# 人間のクリックが要る。API 経由のバッチ運用に GUI は不要なので、サーバーを直接起動する。
# コマンドラインは Desktop が起動していた実プロセスから採取したもの(2026-08-11)。
# Desktop と併用しない(ポート8000が衝突する)。UI を使いたいときはこのサーバーを止めて Desktop を起動。
$env:PYTHONIOENCODING = "utf-8"
Set-Location "C:\Users\kawam\ComfyUI-Installs\ComfyUI"
& "C:\Dev\ComfyUI_app\.venv\Scripts\python.exe" -s ComfyUI\main.py `
    --base-directory "C:\Dev\ComfyUI_app" `
    --user-directory "C:\Dev\ComfyUI_app\user" `
    --database-url "sqlite:///C:\Dev\ComfyUI_app\user\comfyui.db" `
    --port 8000 `
    --extra-model-paths-config "C:\Users\kawam\AppData\Roaming\Comfy Desktop\shared_model_paths.yaml" `
    --input-directory "C:\Dev\ComfyUI_app\input" `
    --output-directory "C:\Dev\ComfyUI_app\output"
