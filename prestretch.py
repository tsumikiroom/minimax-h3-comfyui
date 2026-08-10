"""ページファイル事前ストレッチ。

Windows のコミット上限(物理RAM+ページファイル)は、コミット需要が上限に近づくと
反応的に拡張され、**再起動まで維持される**。この機は2度、重い生成の最中に
「上限の壁ぎわで拡張が間に合わず livelock」で落ちた(2026-08-07)。

このスクリプトは起動直後に commit だけを段階的に確保(touch しないので物理RAMも
ディスクI/Oもほぼ消費しない)して上限を先に育て、即座に全解放する。
以後の重い実行は壁から遠いところで走れる。

使い方: 再起動のたびに1回実行。
    python prestretch.py [目標上限GB=66]
"""
import ctypes
import sys
import time

kernel32 = ctypes.windll.kernel32
kernel32.VirtualAlloc.restype = ctypes.c_void_p
kernel32.VirtualAlloc.argtypes = [ctypes.c_void_p, ctypes.c_size_t,
                                  ctypes.c_ulong, ctypes.c_ulong]
kernel32.VirtualFree.argtypes = [ctypes.c_void_p, ctypes.c_size_t, ctypes.c_ulong]

MEM_COMMIT_RESERVE = 0x3000   # MEM_COMMIT | MEM_RESERVE
PAGE_READWRITE = 0x04
MEM_RELEASE = 0x8000


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


GB = 2**30
TARGET_LIMIT_GB = float(sys.argv[1]) if len(sys.argv) > 1 else 66.0
CHUNK = GB  # 1GB ずつ

m0 = mem()
print(f"開始: 上限 {m0.ullTotalPageFile/GB:.1f} GB / コミット余裕 {m0.ullAvailPageFile/GB:.1f} GB")

# 実測(2026-08-07): Windows は「上限に近づく」だけでは拡張しない。上限を突き抜ける
# 割り当て要求が来た瞬間に同期拡張する。よって境界を実際に踏み抜く必要がある。
# touch しない commit は物理RAMを消費しないので、実行時と違い livelock は起きない。
blocks = []
try:
    fails = 0
    while True:
        m = mem()
        if m.ullTotalPageFile / GB >= TARGET_LIMIT_GB:
            print(f"目標到達: 上限 {m.ullTotalPageFile/GB:.1f} GB")
            break
        # 境界付近は小さい歩幅で踏み抜く
        step = CHUNK if m.ullAvailPageFile > 2 * GB else CHUNK // 4
        p = kernel32.VirtualAlloc(None, step, MEM_COMMIT_RESERVE, PAGE_READWRITE)
        if not p:
            fails += 1
            if fails > 5:
                print(f"拡張されない(ポリシーで固定の可能性)。打ち切り: "
                      f"上限 {mem().ullTotalPageFile/GB:.1f} GB")
                break
            time.sleep(1.5)  # 同期拡張の完了待ちして再試行
            continue
        if fails:
            print(f"  拡張確認: 上限 {mem().ullTotalPageFile/GB:.1f} GB")
        fails = 0
        blocks.append(p)
        time.sleep(0.3)
finally:
    for p in blocks:
        kernel32.VirtualFree(p, 0, MEM_RELEASE)

time.sleep(1.0)
m1 = mem()
print(f"完了: 上限 {m0.ullTotalPageFile/GB:.1f} → {m1.ullTotalPageFile/GB:.1f} GB、"
      f"コミット余裕 {m1.ullAvailPageFile/GB:.1f} GB(確保分 {len(blocks)} GB は全解放済み)")
