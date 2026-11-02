"""Render card.png: a cream "newspaper clipping" card used as on-screen evidence.

usage: python make_card.py <project_dir>
reads card.txt: paragraphs separated by blank lines. The first paragraph is drawn
faded, like the tail of the paragraph above a screenshot crop.
Skip this when the user supplies a real screenshot as card.png.
"""
import argparse
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SKILL = Path(__file__).resolve().parent.parent
SERIF = SKILL / 'assets' / 'fonts' / 'NotoSerifSC-VF.ttf'

W, PAD, SIZE, LEAD, PARA = 860, 64, 36, 1.75, 30
PAPER, INK, FADED = (243, 241, 234), (40, 38, 36), (178, 174, 166)


def wrap(text, font, width):
    lines, cur = [], ''
    for ch in text:
        if font.getlength(cur + ch) > width and cur:
            if ch in '，。、；：！？”）》':  # keep closing punctuation on the line
                cur += ch
                ch = ''
            lines.append(cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(cur)
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    a = ap.parse_args()
    proj = Path(a.project)
    paras = [p.strip().replace('\n', '') for p in (proj / 'card.txt').read_text(encoding='utf-8').split('\n\n') if p.strip()]
    font = ImageFont.truetype(str(SERIF), SIZE)
    try:
        font.set_variation_by_axes([500])
    except Exception:
        pass
    blocks = [wrap(p, font, W - 2 * PAD) for p in paras]
    lh = round(SIZE * LEAD)
    H = PAD + sum(len(b) * lh for b in blocks) + PARA * (len(blocks) - 1) + PAD - 10
    img = Image.new('RGB', (W, H), PAPER)
    d = ImageDraw.Draw(img)
    rng = random.Random(3)
    for _ in range(W * H // 60):  # faint paper grain
        x, y = rng.randrange(W), rng.randrange(H)
        v = rng.randint(-10, 6)
        d.point((x, y), fill=tuple(max(0, min(255, c + v)) for c in PAPER))
    y = PAD - 6
    for i, block in enumerate(blocks):
        for line in block:
            d.text((PAD, y), line, font=font, fill=FADED if i == 0 and len(blocks) > 1 else INK)
            y += lh
        y += PARA
    img.save(proj / 'card.png')
    print('wrote', proj / 'card.png', img.size)


if __name__ == '__main__':
    main()
