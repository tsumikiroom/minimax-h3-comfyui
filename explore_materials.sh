#!/bin/bash
# 素材×マスク×遵守強度の探索バッチ(知見貯め用、2026-08-14 設計)。
# 全てに V1 で実証した「暗転保証節」を含む。素材ごとの音記述つき。
# 前提: ヘッドレスサーバー + ガーディアン稼働(results.md 冒頭の起動手順)。
# 実行: bash explore_materials.sh   (10本、約40分)
PY="/c/Dev/ComfyUI_app/.venv/Scripts/python.exe"
DIR="C:/Users/kawam/ClaudeLab/01_incubation/minimax-h3-comfyui"
cd "$DIR" || exit 1

free_models() {
  curl -s -m 30 -X POST "http://127.0.0.1:8000/free" -H "Content-Type: application/json" \
    -d '{"unload_models":true,"free_memory":true}' -o /dev/null; sleep 3
}
run_r2v() {
  local label="$1" prompt="$2" video="$3"
  echo "=== [$label] ==="; free_models
  local out; out=$(H3_PROMPT="$prompt" "$PY" run_r2v.py "$video" 8 124 1 2>&1); echo "$out" | tail -2
  local pid; pid=$(echo "$out" | grep -oE "prompt_id: .*" | awk '{print $2}')
  [ -z "$pid" ] && { echo "[$label] 投入失敗"; return 1; }
  local fails=0
  while true; do
    local res; res=$(curl -s -m 5 "http://127.0.0.1:8000/history/$pid" 2>/dev/null)
    if [ -z "$res" ]; then fails=$((fails+1)); else
      if [ -n "$(echo "$res" | tr -d '{} \n')" ]; then echo "[$label] 完了"; return 0; fi; fails=0; fi
    [ "$fails" -ge 8 ] && { echo "[$label] SERVER DOWN"; return 2; }
    sleep 10
  done
}

# 共通の骨格: 暗転保証(V1) + 役割宣言 + 封じ込め。素材と遵守レベルだけ差し替える。
HEAD="The frame begins as complete empty darkness."
TAIL_STRICT="follows the motion path, silhouette, deformation and timing of <Video 1> with strict precision, never deviating from it"
TAIL_NORMAL="follows the motion path, speed and timing of <Video 1>"
TAIL_LOOSE="moves loosely guided by the general motion and rhythm of <Video 1>, free to elaborate on it"
FADE="As the shape in <Video 1> shrinks and disappears, it dissolves completely: the final frames are pure empty darkness with nothing remaining."
DECL="Use <Video 1> strictly as an invisible motion and silhouette guide; its flat graphic look must not influence the visual style. Fixed camera, pure black background."

M_GLASS="A cluster of transparent glass bubbles with orange and blue liquid cores, refracting light"
A_GLASS="Audio: delicate glass chimes and soft pops that fade to silence."
M_SMOKE="A plume of dense colored smoke, orange and indigo interweaving in soft volumetric curls"
A_SMOKE="Audio: a deep airy whoosh that fades to silence."
M_SILK="A sheet of flowing silk fabric, iridescent orange-to-blue gradient, rippling in slow waves"
A_SILK="Audio: soft fabric rustles and airy swishes that fade to silence."
M_METAL="A stream of molten chrome metal with orange heat glow in its creases, mirror-reflective"
A_METAL="Audio: low molten gurgles and metallic shimmers that fade to silence."
M_PETAL="A swarm of small flower petals in coral orange and powder blue, fluttering individually"
A_PETAL="Audio: papery flutters and a gentle breeze that fade to silence."

# 素材×マスク×遵守 の10通り(相性則の検証を兼ねて、意図的にミスマッチも混ぜる)
run_r2v "X01 glass x mo22 strict"  "$HEAD $M_GLASS emerges exactly where the shape in <Video 1> appears, and $TAIL_STRICT. $FADE $DECL $A_GLASS" "mask_movieout22.mp4"
run_r2v "X02 glass x mo20 loose"   "$HEAD $M_GLASS emerges where the shape in <Video 1> appears, and $TAIL_LOOSE. $FADE $DECL $A_GLASS" "mask_movieout_20.mp4"
run_r2v "X03 smoke x mo24 normal"  "$HEAD $M_SMOKE emerges where the shape in <Video 1> appears, and $TAIL_NORMAL. $FADE $DECL $A_SMOKE" "mask_movieout_24.mp4"
run_r2v "X04 smoke x mo22 strict"  "$HEAD $M_SMOKE emerges exactly where the shape in <Video 1> appears, and $TAIL_STRICT. $FADE $DECL $A_SMOKE" "mask_movieout22.mp4"
run_r2v "X05 silk x mo20 normal"   "$HEAD $M_SILK emerges where the shape in <Video 1> appears, and $TAIL_NORMAL. $FADE $DECL $A_SILK" "mask_movieout_20.mp4"
run_r2v "X06 silk x LineMask strict" "$HEAD $M_SILK, described as an elongated horizontal ribbon, emerges exactly where the shape in <Video 1> appears, and $TAIL_STRICT. $FADE $DECL $A_SILK" "mask_LineMask.mp4"
run_r2v "X07 metal x mo24 strict"  "$HEAD $M_METAL emerges exactly where the shape in <Video 1> appears, and $TAIL_STRICT. $FADE $DECL $A_METAL" "mask_movieout_24.mp4"
run_r2v "X08 metal x mo20 loose"   "$HEAD $M_METAL emerges where the shape in <Video 1> appears, and $TAIL_LOOSE. $FADE $DECL $A_METAL" "mask_movieout_20.mp4"
run_r2v "X09 petal x mo24 loose"   "$HEAD $M_PETAL emerges where the shape in <Video 1> appears, and $TAIL_LOOSE. $FADE $DECL $A_PETAL" "mask_movieout_24.mp4"
run_r2v "X10 petal x mo22 normal"  "$HEAD $M_PETAL emerges where the shape in <Video 1> appears, and $TAIL_NORMAL. $FADE $DECL $A_PETAL" "mask_movieout22.mp4"

free_models
echo "=== explore_materials 終了(モデル解放済み) ==="
