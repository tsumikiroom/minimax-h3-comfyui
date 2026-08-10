# minimax-h3-comfyui

MiniMax H3(2026-08-03 オープンウェイト公開)を ComfyUI ローカルで動かし、動作テストする。

## 問い

- 16GB VRAM / 32GB RAM の実機で MiniMax H3 が実用速度で回るか
- 音声つき動画生成(native 32kHz stereo)の品質は、既存の WAN 系ワークフローと比べてどうか
- TD / 既存の映像研究(`ai-spritesheet-particles`, `bokeh-typography`)に流用できる素材が出せるか

## モデル概要(調査済み)

- omni-modal 生成モデル。768p 動画 + ネイティブ音声(32kHz ステレオ)、11言語、2K in-context 再生成
- 2026-08-03 公開、MiniMax H3 Community License Agreement
- 同日 ComfyUI 本体に native 対応がマージ(PR Comfy-Org/ComfyUI#15224)
- 追加ノード4種: `EmptyMiniMaxH3LatentAV` / `MiniMaxH3ImageToVideo` / `MiniMaxH3ReferenceToVideo` / `MiniMaxH3SigmaShift`
- 公式ワークフローテンプレート6種(ローカル t2v / i2v / ref2v + API 版)
- カスタムノード不要(本体対応)。サードパーティの `ComfyUI_RH_MinMaxH3` もあるが今回は使わない

## 実機環境(2026-08-04 実測)

| 項目 | 値 |
|---|---|
| GPU | RTX 4090 Laptop / VRAM 16 GB (16376 MiB) |
| Driver | 596.08 |
| System RAM | 31.7 GB |
| C: 空き | 350 GB |
| ComfyUI | **v0.30.1**、Desktop 2、port **8000** |
| basePath / core | `C:\Dev\ComfyUI_app` / `C:\Users\kawam\ComfyUI-Installs\ComfyUI\ComfyUI` |
| venv torch | 2.10.0+cu130、Python 3.12.12 |
| MiniMax H3 対応 | **有**(ノード4種・ローカルテンプレート3種を API で確認済み) |
| モデル置き場 | **`D:\ComfyUI\models`**(外付け T7 Shield)。移行完了。詳細は [storage.md](storage.md) |

## ステータス

**2026-08-04: 5フレーム・22フレームとも成功。音声つき動画のローカル生成を確認。**
実測値と確定した事実は [results.md](results.md)。

| | 5フレーム | 22フレーム |
|---|---|---|
| 合計時間 | 98.92 秒 | **108.01 秒** |
| 1step | 4.15 秒 | 6.94 秒 |
| 尺 | 0.21 秒 | 0.92 秒 |

いずれも 1344×768 / 6 steps。出力に **32kHz ステレオ音声**が乗っていることを ffprobe で確認。
**フレーム数4.4倍でも合計時間は1.09倍**。ロード(約60秒)が支配的なので、長尺ほど効率が上がる。

## 動くが、余裕はゼロ

ピーク コミットは 5フレームで 49.74/49.7 GB、22フレームで 50.56/51.73 GB。**常に天井に張り付く**。
Windows がページファイルを反応的に拡張して吸収している。

- **生成中に他のアプリを開けない。** 1つ起動しただけで落ちうる
- 管理者権限が無くページファイルを増やせないため、この制約は解消できない
- **連続実行でベースラインが上がる**(再起動直後 22.3GB → 数回後 29.6GB)。`/free` では
  ComfyUI 分しか戻らないので、検証セッション中は定期的な OS 再起動が要る

## 次の一手

**39 → 56 → 73 フレームと上げて破綻点を特定する。** 実用長の73フレーム(約3秒)が通れば実用ライン。
step 時間が 22フレームで単調増加(6.36→7.72秒)しており、次で急激に悪化する可能性がある。

## 参照

- [ComfyUI Wiki: MiniMax H3 Open Weights Land With Native ComfyUI Support](https://comfyui-wiki.com/en/news/2026-08-03-minimax-h3-open-weights-comfyui)
- [ComfyUI Wiki: MiniMax H3 モデルページ](https://comfyui-wiki.com/en/models/minimax)
- [Hugging Face: Comfy-Org/MiniMax-H3](https://huggingface.co/Comfy-Org/MiniMax-H3)
- [note: MiniMax H3 T2V ガイド(平泉まゆ)](https://note.com/mayu_hiraizumi/n/nd66cfebfe5d0) — RAM 64GB+ 推奨(この機の制約の裏付け)、LLM によるプロンプト生成の手法、「得意の発見が利用方法」という評価
