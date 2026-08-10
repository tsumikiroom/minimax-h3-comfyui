"""メモリガーディアン(エアバッグ + キルスイッチ)。

## 背景(2026-08-07、クラッシュ×2 から確立)

この機(RAM 31.7GB / 管理者権限なし)は、生成中にコミット上限の壁ぎわで
ページファイルの反応的拡張が間に合わず livelock → 強制電源断を2度起こした。

- 通常の監視(PowerShell+CIM)や HTTP /interrupt は livelock 時に自身が動けず無力(2敗)
- ページファイルを事前に育てる案(prestretch.py 単発実行)は、確保を解放すると
  Windows が数分で刈り戻す(トリム)ため**永続しない**ことが判明

## 本方式: エアバッグ

1. 起動時に境界踏み抜き割り当てで上限を STRETCH_TARGET まで育て、
   **BALLAST_GB の commit を保持し続ける**(touch しないので物理RAMは消費しない)
2. 余裕 < AIRBAG_DEPLOY で**バラストを即時解放** → 瞬時に +BALLAST_GB の余裕。
   メモリ解放はディスクI/O不要なので livelock 進行中でも成立する
3. それでも余裕 < TRIGGER が続いたら ComfyUI python を TerminateProcess で即殺
4. 平穏が続いたら再ストレッチしてバラストを積み直す(re-arm)

バラスト保持中は見かけの余裕が BALLAST_GB ぶん小さく見えるため、実効余裕は
airbag.status ファイル(保持GBを記録)を足して評価すること(run_i2v.py のゲートは対応済み)。

使い方(ComfyUI venv の python で):
    python killswitch.py
ログ: killswitch.log / 状態: airbag.status
"""
import ctypes
import datetime
import os
import time

import psutil

STRETCH_TARGET_GB = 66.0
# バラストはピーク需要(実測 24〜26GB)と同格に。Windows のトリムは「上限 ≥ コミット済」までしか
# 刈れないため、バラストが占有している分だけは上限が釘付けになる(2026-08-07 実測:
# 12GB では不足 — アーム1分後に 66.9 → 55GB に刈られ、実効余裕 23GB でゲートに弾かれた)
BALLAST_GB = 26
AIRBAG_DEPLOY_HEADROOM_GB = 4.0
AIRBAG_STAGE_GB = 6          # 一度に解放する量(全解放するとトリムとの競争に負ける)
TRIGGER_HEADROOM_GB = 2.5
TRIGGER_AVAIL_GB = 0.4
STRIKES = 2
INTERVAL = 0.25
# 解放した余裕は約1分でトリムに刈り戻される(2026-08-07 実測: ロード段で26GB撃ち尽くし →
# 2分後のVAEデコード段で残弾ゼロ → キル)。よってバラストは使い捨てでなく、
# 平時に1GBずつ買い戻す回転式バッファとして運用する
REFILL_MIN_HEADROOM_GB = 8.0   # 見かけ余裕がこれ以上あるときだけ買い戻す

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "killswitch.log")
STATUS = os.path.join(HERE, "airbag.status")

kernel32 = ctypes.windll.kernel32
kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), 0x80)  # HIGH_PRIORITY_CLASS
kernel32.VirtualAlloc.restype = ctypes.c_void_p
kernel32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.c_ulong, ctypes.c_ulong]
kernel32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]
MEM_COMMIT_RESERVE = 0x3000
PAGE_READWRITE = 0x04
MEM_RELEASE = 0x8000
GB = 2**30


class MEMORYSTATUSEX(ctypes.Structure):
    _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]


def mem():
    ms = MEMORYSTATUSEX()
    ms.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    kernel32.GlobalMemoryStatusEx(ctypes.byref(ms))
    return ms


def log(msg):
    line = f"{datetime.datetime.now():%H:%M:%S} {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def write_status(ballast_gb):
    with open(STATUS, "w", encoding="utf-8") as f:
        f.write(str(ballast_gb))


def find_targets():
    pids = []
    for p in psutil.process_iter(["name", "cmdline"]):
        try:
            if p.info["name"] != "python.exe":
                continue
            cl = " ".join(p.info["cmdline"] or [])
            if "main.py" in cl and "ComfyUI" in cl:
                pids.append(p.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return pids


def stretch_and_arm():
    """上限を育ててからバラストを確保。確保できたバラストGBを返す。"""
    stretch = []
    fails = 0
    while True:
        m = mem()
        if m.ullTotalPageFile / GB >= STRETCH_TARGET_GB:
            break
        step = GB if m.ullAvailPageFile > 2 * GB else GB // 4
        p = kernel32.VirtualAlloc(None, step, MEM_COMMIT_RESERVE, PAGE_READWRITE)
        if not p:
            fails += 1
            if fails > 5:
                log(f"ストレッチ頭打ち: 上限 {mem().ullTotalPageFile/GB:.1f} GB")
                break
            time.sleep(1.5)
            continue
        fails = 0
        stretch.append(p)
        time.sleep(0.2)
    for p in stretch:
        kernel32.VirtualFree(p, 0, MEM_RELEASE)
    ballast = []
    for _ in range(BALLAST_GB):
        p = kernel32.VirtualAlloc(None, GB, MEM_COMMIT_RESERVE, PAGE_READWRITE)
        if not p:
            break
        ballast.append(p)
    m = mem()
    log(f"アーム完了: 上限 {m.ullTotalPageFile/GB:.1f} GB / バラスト {len(ballast)} GB 保持 / "
        f"見かけ余裕 {m.ullAvailPageFile/GB:.1f} GB")
    write_status(len(ballast))
    return ballast


ballast = stretch_and_arm()
targets = find_targets()
log(f"guardian 稼働開始。監視対象: {targets or '(未検出、定期再探索)'}")

strike = 0
i = 0
last_status = 0.0
while True:
    m = mem()
    headroom = m.ullAvailPageFile / GB
    avail = m.ullAvailPhys / GB

    # 第1段: エアバッグ段階展開(瞬時解放、I/O無し)。全解放するとトリムに刈られるので少しずつ
    if ballast and headroom < AIRBAG_DEPLOY_HEADROOM_GB:
        n = min(AIRBAG_STAGE_GB, len(ballast))
        for p in ballast[:n]:
            kernel32.VirtualFree(p, 0, MEM_RELEASE)
        ballast = ballast[n:]
        write_status(len(ballast))
        log(f"*** エアバッグ展開: 余裕 {headroom:.2f} GB → +{n} GB 解放(残バラスト {len(ballast)} GB)")
        time.sleep(0.5)
        continue

    # 第2段: キルスイッチ(バラストを撃ち尽くしてなお枯渇 = 真の危機。
    # 物理メモリの枯渇はバラスト残の有無にかかわらず数える)
    if (headroom < TRIGGER_HEADROOM_GB and not ballast) or avail < TRIGGER_AVAIL_GB:
        strike += 1
    else:
        strike = 0
    if strike >= STRIKES:
        if not targets:
            targets = find_targets()
        log(f"!!! キル発火: 余裕 {headroom:.2f} GB / 物理空き {avail:.2f} GB → {targets}")
        for pid in targets:
            try:
                psutil.Process(pid).kill()
                log(f"  killed pid {pid}")
            except Exception as e:
                log(f"  kill 失敗 pid {pid}: {e}")
        strike = 0
        targets = []
        time.sleep(5)

    # 買い戻し: 余裕のある平時に1GBずつバラストを補充(波の合間の弾込め)。
    # VirtualAlloc が失敗しても無害(次tickで再試行)。
    if len(ballast) < BALLAST_GB and headroom >= REFILL_MIN_HEADROOM_GB:
        p = kernel32.VirtualAlloc(None, GB, MEM_COMMIT_RESERVE, PAGE_READWRITE)
        if p:
            ballast.append(p)
            write_status(len(ballast))
            if len(ballast) in (1, BALLAST_GB) or len(ballast) % 6 == 0:
                log(f"バラスト買い戻し: {len(ballast)}/{BALLAST_GB} GB")

    i += 1
    if i % 80 == 0:
        new = find_targets()
        if set(new) != set(targets):
            targets = new
            log(f"監視対象を更新: {targets}")
    now = time.time()
    if now - last_status > 300:
        last_status = now
        log(f"alive: 見かけ余裕 {headroom:.1f} GB / バラスト {len(ballast)} GB / "
            f"物理空き {avail:.1f} GB / 対象 {targets}")

    time.sleep(INTERVAL)
