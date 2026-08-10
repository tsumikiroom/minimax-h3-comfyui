# plan — MiniMax H3 を ComfyUI で動かす

## 変種の選定(16GB VRAM / 31.7GB RAM 前提)

Comfy-Org/MiniMax-H3 の全ファイルと実サイズ:

| ファイル | サイズ | 採否 |
|---|---|---|
| `diffusion_models/minimax_h3_fl2va_bf16` | 66.3 GB | × RAM 不足 |
| `diffusion_models/minimax_h3_fl2va_int8_convrot` | 34.0 GB | × RAM 不足 |
| `diffusion_models/minimax_h3_fl2va_pruned_int8_convrot` | 21.0 GB | △ **公式テンプレートの既定値**。フォールバック |
| **`diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled`** | **21.0 GB** | **○ 採用(初回)** |
| `diffusion_models/minimax_h3_ref2va_*` | 同上 | 後回し(ref2v を試す段で追加) |
| `text_encoders/qwen3vl_32b_minimax_h3_bf16` | 51.5 GB | × |
| `text_encoders/qwen3vl_32b_minimax_h3_int8_convrot` | 27.1 GB | × RAM 不足 |
| **`text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq`** | **15.7 GB** | **○ 採用(唯一現実的)** |
| **`vae/minimax_h3_video_vae_fp16`** | **5.2 GB** | **○** |
| **`vae/minimax_h3_audio_vae_fp32`** | **0.6 GB** | **○** |

初回ダウンロード合計 **約 42.5 GB**。

**公式 i2v テンプレート(`video_minimax_h3_i2v.json`)が指定するモデルは以下**(2026-08-04 実確認):

```
diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors
text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
vae/minimax_h3_video_vae_fp16.safetensors
vae/minimax_h3_audio_vae_fp32.safetensors
```

text encoder と VAE 2種は上の選定と一致した。**diffusion だけ公式は int8_convrot、こちらは fp8_scaled** を選んでいる。
fp8 を選んだ理由は 4090(Ada)が fp8 native なため。ただし v0.30.0 のリリースノートは
「int8 convrot embedding lookup 対応」に言及しており、**convrot 側がチューニング済みの本命経路の可能性が高い**。

初回は既にDL済みの fp8 で走らせ(ローダーのドロップダウンを差し替えるだけ)、エラーや品質劣化が出たら
同サイズの int8_convrot を追加DL(+21GB)して比較する。

## 手順

- [x] **1. ComfyUI をアップデート**(2026-08-04 完了)
      **v0.30.1** になり、H3 ノード4種(`EmptyMiniMaxH3LatentAV` / `MiniMaxH3ImageToVideo` /
      `MiniMaxH3ReferenceToVideo` / `MiniMaxH3SigmaShift`)と、ローカル用テンプレート3種
      (`video_minimax_h3_i2v` / `_t2v` / `_r2v`)＋API版3種を API で確認済み。
      H3 対応は v0.30.0(2026-08-03)から。

- [x] **3. モデルをダウンロード**(2026-08-04 完了、計 42.5GB)
      ```
      models/diffusion_models/minimax_h3_fl2va_pruned_fp8_scaled.safetensors   21.0 GB
      models/text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors        15.7 GB
      models/vae/minimax_h3_video_vae_fp16.safetensors                          5.2 GB
      models/vae/minimax_h3_audio_vae_fp32.safetensors                          0.6 GB
      ```
      ComfyUI の UNETLoader が diffusion を認識済み(API で確認)。`.cache` も掃除済み。

- [ ] **2. ページファイルを拡張** ← **ここがブロッカー。実行前に必須**
      2026-08-04 実測:

      | 項目 | 値 |
      |---|---|
      | 物理RAM | 31.7 GB |
      | 実質空き(standby除く) | **約 0.1 GB** |
      | ページファイル | 19 GB(自動管理) |
      | **コミット済 / 上限** | **43.1 GB / 50.7 GB** |
      | **コミット余裕** | **7.6 GB** |

      diffusion 単体で 21GB のコミットが要るのに余裕が 7.6GB しかない。**このまま実行すると
      commit limit に当たって失敗するか、ページファイル自動拡張の最中に長時間フリーズする**。

      **ページファイル拡張は不可**: このアカウント(`P00360-KAWAMURA\kawam`)に**管理者権限が無い**。
      仮想メモリの設定変更には昇格が必要なため、この経路は使えない。コミット上限 50.7GB は固定と考える。

      実際に効いた/効かなかった対処(2026-08-04 実測):

      | 対処 | 効果 |
      |---|---|
      | TouchDesigner ×2 + DJI Studio を終了 | 余裕 7.9 → **12.5 GB** ○ |
      | `wsl --shutdown` | **効果なし**。vmmem(4.0GB)は WSL ではない別の Hyper-V VM で落ちない |
      | 残るプロセスの整理 | 465プロセスの長い裾。1つずつは 0.5GB 程度で効率が悪い |

      → **OS 再起動が唯一の実効的な手段**。25時間稼働でカーネル/ドライバ分だけで約9GB、
      vmmem 4.0GB も残留している。再起動して **ComfyUI だけ起動した状態**なら余裕 30GB 前後が見込め、
      21GB が収まる。

      なお safetensors は mmap で読まれるため、21GB のファイルがそのまま 21GB のコミットになるとは
      限らない(ファイルバックドのページはコミットに乗らない)。これは**推測で、未実測**。
      実測値が取れたらここに追記する。

- [ ] **4. ワークフローを開く**
      ComfyUI の Templates から MiniMax H3 の **image-to-video(ローカル版)** を開く。
      t2v ではなく i2v から始める理由: 入力画像を固定できるので、失敗時に「モデルが動かない」のか
      「プロンプトが効いていない」のかを切り分けやすい。

      テンプレート実体: `comfyui_workflow_templates_json/templates/video_minimax_h3_i2v.json`。
      中身はサブグラフ **"Image to Video (MiniMax H3)"** に本体が入っている。触るのは以下:

      | ノード | 既定値 | 初回テストでの変更 |
      |---|---|---|
      | `UNETLoader` | `..._pruned_int8_convrot` | **`..._pruned_fp8_scaled` に変更(必須。int8 は未DL)** |
      | `CLIPLoader` | `qwen3vl_32b_..._nvfp4_awq` | そのまま |
      | `VAELoader` ×2 | video_fp16 / audio_fp32 | そのまま |
      | `BasicScheduler` | steps **20** / denoise 1 | **steps 6** |
      | `MiniMaxH3ImageToVideo` | 1344×768 / **73フレーム** | 解像度は据え置き、フレーム数を最小に |
      | `KSamplerSelect` | `res_multistep` | そのまま |
      | `CreateVideo` | fps 24 | そのまま |

      解像度を据え置くのは H3 が 768p で学習されており、半端な値だとモデル側で落ちうるため。
      まず軽くするのは steps とフレーム数から。

- [ ] **5. 最小構成で 1本通す**
      - 解像度は 768p のまま、フレーム数を**最小**、ステップ数も**最小**にして、まず最後まで通す
      - VRAM OOM が出たら ComfyUI 起動オプションに `--lowvram` を追加
      - 生成物に**音声が乗っているか**を必ず確認(H3 の要点はここ)

- [x] **6. 実測を記録**(2026-08-04 完了) → [results.md](results.md) に全文

- [ ] **7. Go / No-Go 判断**
      1本あたりの生成時間が実用範囲なら ref2va(+21GB)を追加して reference-to-video を試す。
      実用外なら、そこまでを記録して打ち切り、API 版に切り替えるか判断する。

## 未検証・確認が必要な点

- ~~NVFP4 AWQ text encoder が Ada(4090)で動くか~~ → **懸念は解消。公式 i2v テンプレートの既定値が
  まさに nvfp4_awq**。Blackwell 専用ではなく標準の選択肢として配布されている。
- 残る最大の不確実性は **RAM 31.7GB**。ComfyUI 起動＋DL中の時点で空き 5.3GB しかなかった。
  21GB の diffusion を載せる段でスワップに落ちる可能性が高い。ページファイル拡張は必須。
- fp8_scaled が H3 ローダーで問題なく読めるか(公式既定は int8_convrot)。
- ライセンスに国別の除外条項があるという記述を見かけた(未確認)。商用利用を検討する段になったら
  MiniMax H3 Community License Agreement の原文を読むこと。今回の動作テストの範囲では問題にならない。
