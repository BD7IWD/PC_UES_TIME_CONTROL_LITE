# -*- coding: utf-8 -*-
"""从 ICO/ 目录的设计图生成 app.ico（去白底 + 裁边 + 多尺寸）。

要点：
  1. 不能简单把白色像素全变透明 —— 笔记本键盘高光、屏幕上的"60"也是白的，
     全部透明会把主体挖空。只用「与图片四边连通的白色」判定为背景。
  2. 用 cv2.floodFill（C 实现）从四角灌水标记外部白，2048×2048 也很快；
     PIL 的 floodfill 在纯 Python 下跑这个尺寸会不完整（实测只填了 4.7%）。
  3. 裁到主体轮廓后补成正方形，只留 2% 边距，避免图标四周出现白框。

作者：野怼怼；https://www.bd7iwd.com
许可：MIT
"""
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / 'ICO' / '儿童电脑使用时长控制关键图标.png'
OUT = ROOT / 'app.ico'
PREVIEW = ROOT / 'previews' / 'preview_icon.png'

SIZES = [16, 24, 32, 48, 64, 128, 256]
PAD_RATIO = 0.02          # 主体四周留白比例（很小，视觉上"满格"）
WHITE_TH = 242            # 白色判定阈值


def imread_unicode(path: Path) -> np.ndarray:
    """cv2.imread 不支持中文路径，走 imdecode。"""
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise RuntimeError(f'读取失败：{path}')
    return img


def main() -> None:
    bgr = imread_unicode(SRC)
    h, w = bgr.shape[:2]
    print('原图:', w, 'x', h)

    # 1. 白色掩码（BGR 三通道都接近白）
    white = np.zeros((h, w), np.uint8)
    for c in range(3):
        white = np.maximum(white, (bgr[:, :, c] >= WHITE_TH).astype(np.uint8) * 255)
    white = ((bgr.min(axis=2) >= WHITE_TH).astype(np.uint8)) * 255
    print('白色像素占比: %.1f%%' % (white.mean() / 255 * 100))

    # 2. 从四边灌水，标记「与边缘连通」的白色（= 背景）
    flood = white.copy()
    seed_mask = np.zeros((h + 2, w + 2), np.uint8)
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1),
             (w // 2, 0), (0, h // 2), (w - 1, h // 2), (w // 2, h - 1)]
    used = 0
    for sx, sy in seeds:
        if flood[sy, sx] == 255:
            cv2.floodFill(flood, seed_mask, (sx, sy), 128, 0, 0, 4)
            used += 1
    outer = seed_mask[1:-1, 1:-1] > 0
    print(f'灌水种子: {used} 个 | 外部背景占比: {outer.mean() * 100:.1f}%')

    # 3. 组装 RGBA
    #    注意：这里不做"半透明羽化"。近白过渡像素半透明后在深色任务栏上会泛白光晕，
    #    反而像留了一圈白边。直接二分 alpha，锯齿交给后面的 LANCZOS 缩放平滑。
    alpha = np.where(outer, 0, 255).astype(np.uint8)

    rgba = np.dstack([cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB), alpha])
    out = Image.fromarray(rgba, 'RGBA')

    bbox = out.getbbox()
    print('主体 bbox:', bbox, '→ 裁剪后尺寸:', (bbox[2] - bbox[0], bbox[3] - bbox[1]))
    out = out.crop(bbox)
    cw, ch = out.size

    side = max(cw, ch)
    pad = int(round(side * PAD_RATIO))
    canvas = Image.new('RGBA', (side + pad * 2, side + pad * 2), (0, 0, 0, 0))
    canvas.paste(out, ((canvas.width - cw) // 2, (canvas.height - ch) // 2), out)
    print('正方形画布:', canvas.size, f'(边距 {pad}px = {PAD_RATIO:.0%})')

    base = canvas.resize((256, 256), Image.LANCZOS)
    base.save(OUT, format='ICO', sizes=[(s, s) for s in SIZES])
    print('已生成', OUT, OUT.stat().st_size, 'bytes')

    PREVIEW.parent.mkdir(exist_ok=True)
    base.save(PREVIEW)

    px = np.array(base)[:, :, 3]
    corners = [int(px[0, 0]), int(px[0, -1]), int(px[-1, 0]), int(px[-1, -1])]
    print('四角 alpha:', corners, '→', '✅ 无白边' if max(corners) < 20 else '❌ 仍有底色')
    print('透明像素占比: %.1f%%' % ((px == 0).sum() / px.size * 100))
    print('预览:', PREVIEW)


if __name__ == '__main__':
    main()
