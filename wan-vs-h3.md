# WAN vs MiniMax H3 — ローカル動画生成の現状整理(2026-08-07)

情報源: ComfyUI Wiki、note の実測比較記事(RTX 5060 Ti 16GB)、各所のリリース情報、
およびこの機(4090 Laptop 16GB / RAM 31.7GB)での H3 実測。

## まず前提: 「WAN」のどれと比べるかを整理する

WAN は系列が分裂しており、ここを混同した記事が多い。

| 系列 | 公開形態 | 備考 |
|---|---|---|
| Wan 2.2(A14B MoE / 5B) | **オープンウェイト** | ローカル勢の現行本命。VACE Fun 等の control 生態系 |
| Wan 2.5 / 2.6 | APIのみ | 2.5 から音声対応だがウェイト非公開 |
| Wan 2.7 | APIのみ(ComfyUI はパートナーノード経由) | マルチモーダル入力。**オープンウェイト版は存在しない**。"Wan 2.7 download" を謳うサイトはSEO偽装 |

→ **ローカルで比べる相手は Wan 2.2**。「Wan 2.7 が音声対応でオープン」のような情報は誤り。

MiniMax H3 側: 2026-07-31 発表、**08-03 にオープンウェイト公開**(Community License、除外国あり)。
モデル最大能力は 15秒・2K・音声つき(発表/プラットフォーム側の数字)。
**ローカル配布物(H3-Base 系)は 768p クラス**で、長尺・2K はアップスケール/延長で補う運用。

## 本題: Wan 2.2 vs MiniMax H3(ローカル・オープンウェイト対決)

| 軸 | Wan 2.2 | MiniMax H3(open) |
|---|---|---|
| **音声** | **なし**(音声対応は API 版 2.5 以降のみ) | **ネイティブ 32kHz ステレオ**。環境音+11言語の音声(日本語含む)。実機で確認済み |
| タスク | T2V / I2V / FLF2V / **V2V control(VACE)** | T2V / I2V / **FLF2V(fl2va がまさにこれ)** / R2V(reference) |
| **動き指定動画(control video)** | **○ VACE Fun**(depth/線画/グレースケール動画で構造支配) | **× 現状入口なし**。reference は動きではなくスタイル/同一性用 |
| 解像度クラス | 720p(5B)〜 | 768p |
| 品質評価(note 実測) | 「画質はいいけど動きは控えめ」 | 「商用サービスを少し簡略化したくらい」。動きの質は LTX 2.3 より上 |
| 速度(note, 5060Ti) | 832×480 10秒 ≈ **30分** | 864×480 5秒 = 633秒(素) → 最適化で**5〜6分**、Turbo LoRA 追加で **約3分**(3060 実測) |
| 高速化生態系 | Lightning LoRA(4step)が成熟 | Turbo LoRA(4step, 08-06 登場)。音声が弱点との報告 |
| モデルサイズ | 5B なら軽量。A14B は GGUF 量子化前提 | 42.5GB(T2V/I2V)+ ref2va で 63GB 超 |
| 成熟度 | 1年分の LoRA・ワークフロー資産 | 公開から**4日**。生態系は生まれたて |
| ライセンス | Apache 2.0 | Community License(除外国条項あり、商用時は原文確認) |

## 用途分担(どちらかを選ぶ話ではない)

- **動きを厳密に支配したいショット** → Wan 2.2 VACE(TD/C4D のノンテクスチャ動画を構造条件に)
- **キーフレーム間を気持ちよく繋ぐ+音が欲しいショット** → H3 flf2v
- **音声(環境音・セリフ)込みの一発出し** → H3 一択。ローカルでこれができるのは現状 H3 だけ
- VACE 出力に音を付けたい → H3 で作り直すか、音は別工程

## この機の所持状況

- Wan 2.2: VACE Fun A14B GGUF ×4(Q4/Q5/Q8)+ Lightning LoRA ×4 を **D:\ComfyUI\models に所持済み**(過去に稼働実績あり)
- H3: fp8 pruned 一式 + Turbo LoRA(ckpt500 pruned)所持。5f/22f で動作実証済み。124f は計測待ち

## 参照

- [ComfyUI Wiki: MiniMax H3](https://comfyui-wiki.com/en/models/minimax) / [open weights 記事](https://comfyui-wiki.com/en/news/2026-08-03-minimax-h3-open-weights-comfyui) / [Turbo LoRA 記事](https://comfyui-wiki.com/en/news/2026-08-06-minimax-h3-turbo-lora)
- [note: 5060Ti での H3 vs Wan/LTX 実測](https://note.com/ai_0049/n/nb4d548eb991d)
- [Wan 2.7 のオープンソース状況(open は 2.2 まで)](https://localaimaster.com/blog/wan-2-7-open-source) / [ComfyUI 公式: Wan 2.7 はパートナーノード経由](https://blog.comfy.org/p/wan27-is-now-available-in-comfyui)
- [drbaph: H3 Turbo LoRA pruned ComfyUI 版](https://huggingface.co/drbaph/MiniMax-H3-Turbo-Lora-ComfyUI)
- YouTube「Seedance 2.0級の動画生成AI『MiniMax H3』完全ガイド」(y6NHb_z6nVY) — 15秒/2K/日本語ボイスはモデル最大能力の数字
