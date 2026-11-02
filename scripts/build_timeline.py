"""Lay out every group in world space, plan the camera, snap to the music.

usage: python build_timeline.py <project_dir>
reads  script.txt, config.json (optional), build/words.json (voice mode),
       build/beats.json (if bgm), card.png (optional)
writes build/timeline.json for the Remotion engine.

Core logic (layout "chain"): every script line is a group written at +-90° to the
previous one. The camera turns 90° to read each new group upright in the middle of
the frame, so the previous group is left lying sideways next to it.
Layout "scatter": no camera; each sentence is a page of short pieces at random spots
and sizes, popping up with the voice.
"""
import argparse
import json
import math
import random
from pathlib import Path

from PIL import ImageFont

from script_format import parse

SKILL = Path(__file__).resolve().parent.parent
FONT_DIRS = [SKILL / 'assets' / 'fonts', Path('C:/Windows/Fonts'),
             Path.home() / 'AppData/Local/Microsoft/Windows/Fonts']
# preset name -> (file, weight). Any .ttf/.otf path or file name in FONT_DIRS also works.
FONTS = {
    '特黑体': ('NotoSansSC-VF.ttf', 900),
    '粗黑体': ('NotoSansSC-VF.ttf', 700),
    '细体': ('NotoSansSC-VF.ttf', 300),
    '圆体': ('SIMYOU.TTF', 400),  # Windows 幼圆
    '黑体': ('simhei.ttf', 400),
    '等线': ('Dengb.ttf', 400),
    '得意黑': ('SmileySans-Oblique.ttf', 400),  # free (OFL); drop the file into assets/fonts
    '泼墨': ('MaShanZheng-Regular.ttf', 400),  # 马善政毛笔楷书, brush strokes (OFL)
    '毛笔': ('MaShanZheng-Regular.ttf', 400),
}

DEFAULTS = {
    'fps': 24,
    'width': 720,
    'height': 1280,
    'seed': 7,
    'base_size': 64,  # world units; camera zoom decides the final pixel size
    # every line draws a size class [scale, weight]: small / medium / big, never the same twice in a row
    'size_classes': [[0.65, 0.3], [1.0, 0.35], [1.5, 0.35]],
    'size_jitter': 0.08,  # +-8% on top of the class
    'emphasis_scale': 1.6,
    'max_line_width': 600,
    'max_zoom': 1.7,
    'max_zoom_emphasis': 2.4,
    'fit_width': 0.84,  # current block fills at most this share of frame width
    'fit_width_emphasis': 0.92,
    'group_zoom_jitter': 0.2,  # non-emphasis groups land at 80-100% of the fitted size
    'emphasis_row_chars': 4.5,  # long emphasis lines are split into rows of about this many chars
    'rot_frames': 7,
    'para_turn_frames': 10,  # paragraph break: same 90° turn, slower in-out
    'turn_mode': 'random',  # random | alternate | left | right; every turn is exactly 90°
    'chain_gap': 24,  # world units between the previous (upright) sentence and the new one
    'prev_peek': 0.35,  # spoken sentences leave the screen: at most 35% of the previous block shows
    'prev_peek_px': 80,  # ...and never more than 80px of it on screen
    'line_cam_frames': 5,
    'keep_prev_groups': 1,  # only the previous sentence stays, mostly pushed off screen
    'colors': {
        'bg': '#000000',
        'grid': '#262626',
        'white': '#FFFFFF',
        'dim': '#6B6B6B',
        'red': '#D0141C',
        'deep_red': '#A00D14',
        'cover': '#FFD43B',
    },
    'grid_size': 40,
    'voice_volume': 1.0,
    'bgm_volume': None,  # default 0.28 with voice, 0.9 music-only
    'bgm_offset': 0,
    'beat_snap_frames': 1,  # chars within this many frames of a beat jump onto it
    'emphasis_snap_frames': 3,  # emphasis lines may move this far to land on a beat
    'pulse_beat': 0.018,
    'pulse_downbeat': 0.04,
    'pulse_emphasis': 0.07,
    'cover': None,  # e.g. "华为制药\n不做药？" shown for the first frames
    'cover_frames': 2,
    'card_width': 430,
    'card_top': 0.6,  # share of height
    'tail_seconds': 1.2,
    'music_only': False,  # no voice: lines land on beats, groups turn on downbeats
    'font': '特黑体',  # preset from FONTS, or a font file
    'font_weight': None,  # override the preset weight (variable fonts only)
    # how each char of a line comes in: slide | waterfall (drops in from above) |
    # flip (turns over from mirrored) | tumble (spins in tilted, lands with a bounce) |
    # pop (bounces up from small) | rise (slides up out of a mask) | glitch (RGB split jitter) |
    # none (fade only) | mix (each line picks one of reveal_mix)
    'reveal': 'mix',
    'reveal_mix': ['waterfall', 'flip', 'slide'],
    'reveal_frames': 4,
    'text_shadow': 0,  # black shadow opacity 0-1 (template "阴影 黑色 不透明度90" = 0.9)
    'text_stroke': 0,  # black outline width in px of world size (template "描边 黑色" ~ 2-4)
    # grid (flat) | room (3D grid room: ceiling + floor fading into the dark) | a video/image file:
    # name or path, looked up in the project, then assets/backgrounds (e.g. "street" -> street.mp4).
    # A bg.mp4 / bg.jpg dropped into the project is used when background isn't set.
    'background': 'grid',
    'bg_dim': 0.15,  # black veil over a video/image background, 0-1
    # chain: each sentence at 90° to the last, the camera turns to read it |
    # scatter: no camera; short pieces pop up at random spots and sizes, one page per sentence
    'layout': 'chain',
    'scatter_chunk': 4,  # max chars per piece; red keywords and Latin words stay whole
    'scatter_size': [1.1, 2.0],  # piece size range, times base_size
    'scatter_margin': 36,  # px from the screen edge
    'scatter_gap': 14,  # min px between pieces
    'scatter_spread': 1.8,  # a short page is stretched vertically up to this much to fill the screen
}

BG_DIR = SKILL / 'assets' / 'backgrounds'
MEDIA_EXT = {'.mp4': 'video', '.mov': 'video', '.webm': 'video', '.jpg': 'image', '.jpeg': 'image',
             '.png': 'image', '.webp': 'image'}


def resolve_font(name, weight=None):
    file, w = FONTS.get(name, (name, 400))
    path = Path(file)
    if not path.is_absolute():
        path = next((d / file for d in FONT_DIRS if (d / file).exists()), path)
    if not path.exists():
        raise SystemExit(f'font {name!r} not found ({file}); put it in {FONT_DIRS[0]} or use one of {list(FONTS)}')
    return path, weight or w


class Measurer:
    def __init__(self, path, weight):
        self.font = ImageFont.truetype(str(path), 200)
        try:
            self.font.set_variation_by_axes([weight])  # variable fonts only
        except Exception:
            pass

    def width(self, text, size):
        return self.font.getlength(text) * size / 200


def rot(v, deg):
    r = math.radians(deg)
    c, s = math.cos(r), math.sin(r)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c)


def split_emphasis(line, per_row):
    """Break a long emphasis line into short rows so each row can be huge."""
    chars = line['chars']
    n = len(chars)
    rows = round(n / per_row)  # 5-6 chars still fit on one big row; ceil would cut 它做/不了的
    if rows <= 1:
        return [line]
    latin = lambda ch: ch.isascii() and ch.isalnum()
    cuts = []
    for r in range(1, rows):
        ideal = round(n * r / rows)
        # prefer a cut that does not split a red keyword, a Latin word (A/I) or land on a space
        options = sorted(range(max(1, ideal - 2), min(n, ideal + 3)), key=lambda i: abs(i - ideal))
        good = [i for i in options if not (chars[i - 1]['red'] and chars[i]['red']) and chars[i]['c'] != ' '
                and not (latin(chars[i - 1]['c']) and latin(chars[i]['c']))]
        cuts.append((good or options)[0])
    out, start = [], 0
    for c in sorted(set(cuts)) + [n]:
        if c > start:
            out.append({'emphasis': True, 'chars': chars[start:c]})
        start = c
    return out


def layout_group(g, rng, cfg, m, align):
    base = cfg['base_size']
    rows = []
    for line in g['lines']:
        rows += split_emphasis(line, cfg['emphasis_row_chars']) if line['emphasis'] else [line]
    sized = []
    classes = cfg['size_classes']
    last_cls = None
    for line in rows:
        text = ''.join(c['c'] for c in line['chars'])
        weights = [w for _, w in classes]
        if any(c['red'] for c in line['chars']):
            weights[-1] *= 2  # lines carrying a red keyword lean big
        if last_cls is not None and len(classes) > 1:
            weights[last_cls] = 0  # neighbours always differ in size
        cls = rng.choices(range(len(classes)), weights=weights)[0]
        last_cls = cls
        size = base * classes[cls][0] * rng.uniform(1 - cfg['size_jitter'], 1 + cfg['size_jitter'])
        if line['emphasis']:
            size = base * cfg['emphasis_scale'] * rng.uniform(0.95, 1.1)
        w = m.width(text, size)
        limit = cfg['max_line_width'] * (1.08 if line['emphasis'] else 1)
        if w > limit:
            size *= limit / w
            w = limit
        sized.append((line, size, w))
    W = max(w for _, _, w in sized)
    H = sum(s * 1.18 for _, s, _ in sized)
    y = -H / 2
    lines = []
    for line, size, w in sized:
        x = -W / 2 if align == 'left' else (W / 2 - w if align == 'right' else -w / 2)
        lines.append({'x': x, 'y': y, 'w': w, 'size': size, 'emphasis': line['emphasis'], 'src': line})
        y += size * 1.18
    has_emphasis = any(l['emphasis'] for l in rows)
    # each group lands at a slightly random size; emphasis groups land big
    zoom_mul = 1.0 if has_emphasis else rng.uniform(1 - cfg['group_zoom_jitter'], 1.0)
    return {'W': W, 'H': H, 'lines': lines, 'emphasis': has_emphasis, 'zoom_mul': zoom_mul}


def pick_turns(n, rng, mode):
    """+90 = camera turns right, -90 = left. Never more than 90° per sentence."""
    turns = [0]
    for i in range(1, n):
        if mode == 'right':
            turns.append(90)
        elif mode == 'left':
            turns.append(-90)
        elif mode == 'alternate':
            turns.append(90 if i % 2 else -90)
        else:
            turns.append(rng.choice([90, -90]))
    return turns


def place_groups(groups, rng, cfg, m):
    """Chain the sentences: after a turn the previous sentence stands upright
    (vertical) right beside the new one, its last line facing the new sentence,
    and the new first line starts level with the first char of that last line.

    Turning +90 rotates the old block 90° counter-clockwise on screen (it reads
    bottom-to-top, sits on the left, first char at the bottom); -90 mirrors that
    (reads top-to-bottom, sits on the right, first char at the top).
    """
    turns = pick_turns(len(groups), rng, cfg['turn_mode'])
    laid = []
    for i, g in enumerate(groups):
        side = -1 if turns[i] > 0 else 1  # where the previous sentence ends up
        # the new sentence hugs the previous one; the first one is free
        align = rng.choice(['left', 'right']) if i == 0 else ('left' if side < 0 else 'right')
        laid.append(layout_group(g, rng, cfg, m, align) | {'turn': turns[i], 'side': side})
    pos, theta = (0.0, 0.0), 0.0
    for i, L in enumerate(laid):
        if i:
            theta += L['turn']
            prev = laid[i - 1]
            # previous block's centre in the new block's frame
            last = prev['lines'][-1]
            first_char_x = last['x'] + last['size'] / 2  # old-local x of its last line's first char
            new_first_y = L['lines'][0]['y'] + L['lines'][0]['size'] * 0.59
            # rotate(-90) maps old (x, y) -> (y, -x); rotate(+90) maps it -> (-y, x)
            off_y = new_first_y + first_char_x if L['turn'] > 0 else new_first_y - first_char_x
            offset = (L['side'] * (L['W'] / 2 + cfg['chain_gap'] + prev['H'] / 2), off_y)
            L['prev_x'] = (offset[0] - prev['H'] / 2, offset[0] + prev['H'] / 2)
            r = rot(offset, theta)
            pos = (pos[0] - r[0], pos[1] - r[1])
        L.update({'x': pos[0], 'y': pos[1], 'rot': theta, 'cam_rot': theta})
    return laid


def frames_from_words(groups, words, fps):
    it = iter(words)
    for g in groups:
        for line in g['lines']:
            for c in line['chars']:
                w = next(it)
                c['f'] = round(w['t'] * fps)


def frames_from_beats(groups, beats, fps):
    """Music-only mode: one line per beat, each group starts on a downbeat."""
    bf = [round(t * fps) for t in beats['beats']] or [round(i * fps * 0.5) for i in range(400)]
    down = set(round(t * fps) for t in beats['downbeats'])
    k = 0
    for gi, g in enumerate(groups):
        if gi:
            k += 1
            while k < len(bf) - 1 and bf[k] not in down:
                k += 1
        for line in g['lines']:
            k = min(k, len(bf) - 1)
            start = bf[k]
            gap = (bf[k + 1] - bf[k]) if k + 1 < len(bf) else fps // 2
            n = len(line['chars'])
            span = min(gap * 0.6, n * 2)
            for i, c in enumerate(line['chars']):
                c['f'] = start + (round(span * i / max(1, n - 1)) if not line['emphasis'] else 0)
            k += 1


def nearest(frames, f, tol):
    best = min(frames, key=lambda b: abs(b - f), default=None)
    return best if best is not None and abs(best - f) <= tol else None


def snap_to_beats(groups, beat_frames, down_frames, cfg):
    for g in groups:
        for line in g['lines']:
            chars = line['chars']
            if not chars:
                continue
            if line['emphasis']:
                hit = nearest(down_frames, chars[0]['f'], cfg['emphasis_snap_frames']) or nearest(
                    beat_frames, chars[0]['f'], cfg['emphasis_snap_frames']
                )
                if hit is not None:
                    d = hit - chars[0]['f']
                    for c in chars:
                        c['f'] += d
                continue
            for c in chars:
                b = nearest(beat_frames, c['f'], cfg['beat_snap_frames'])
                if b is not None:
                    c['f'] = b
            for a, b in zip(chars, chars[1:]):
                b['f'] = max(b['f'], a['f'])


def fit(L, upto, cfg, anchor_box):
    lines = L['lines'][: upto + 1]
    x0 = min(l['x'] for l in lines)
    x1 = max(l['x'] + l['w'] for l in lines)
    y0 = lines[0]['y']
    y1 = lines[-1]['y'] + lines[-1]['size'] * 1.18
    fill = cfg['fit_width_emphasis'] if L['emphasis'] else cfg['fit_width']
    max_zoom = cfg['max_zoom_emphasis'] if L['emphasis'] else cfg['max_zoom']
    zoom = min(anchor_box[0] * fill / (x1 - x0), anchor_box[1] / (y1 - y0), max_zoom) * L['zoom_mul']
    # frame only the sentence being spoken; the previous one hangs off the screen edge
    cx = (x0 + x1) / 2
    if 'prev_x' in L:
        half = anchor_box[0] / zoom / 2
        px0, px1 = L['prev_x']
        keep = min((px1 - px0) * cfg['prev_peek'], cfg['prev_peek_px'] / zoom)  # most it may show
        if L['side'] < 0 and px1 - (cx - half) > keep:  # previous on the left: slide the view right
            cx = px1 - keep + half
        elif L['side'] > 0 and (cx + half) - px0 > keep:
            cx = px0 + keep - half
    c = rot((cx, (y0 + y1) / 2), L['rot'])
    return L['x'] + c[0], L['y'] + c[1], zoom


def chunk_line(line, cfg):
    """Scatter layout: cut a script line into short pieces at red/plain borders and the
    longest pauses, never inside a Latin word."""
    latin = lambda ch: ch.isascii() and ch.isalnum()
    runs = []
    for c in line['chars']:
        if runs and c['red'] == runs[-1][-1]['red']:
            runs[-1].append(c)
        else:
            runs.append([c])
    out = []

    def cut(run):
        if len(run) <= cfg['scatter_chunk']:
            out.append(run)
            return
        n, mx = len(run), cfg['scatter_chunk']
        # two pieces when that is enough (7 chars -> 3+4, not 2+2+3), each at least 2 chars
        lo, hi = (max(2, n - mx), min(mx, n - 2)) if n <= 2 * mx else (2, n - 2)
        opts = [i for i in range(lo, hi + 1) if not (latin(run[i - 1]['c']) and latin(run[i]['c']))]
        i = max(opts or range(1, len(run)), key=lambda i: (run[i]['f'] - run[i - 1]['f'], -abs(i - len(run) / 2)))
        cut(run[:i])
        cut(run[i:])

    for r in runs:
        cut(r)
    trimmed = []
    for piece in out:
        while piece and piece[0]['c'] == ' ':
            piece = piece[1:]
        while piece and piece[-1]['c'] == ' ':
            piece = piece[:-1]
        if piece:
            trimmed.append(piece)
    return trimmed


def find_spot(page, w, h, rng, cfg, W, top, bottom):
    """Topmost free spot (loosely), at a random x, never above the previous piece's middle."""
    margin, pad = cfg['scatter_margin'], cfg['scatter_gap']
    floor = max(top, page[-1]['y'] - page[-1]['h'] * 0.5) if page else top
    if bottom - h <= floor:
        return None
    best = None
    for _ in range(400):
        x = rng.uniform(margin, max(margin, W - margin - w))
        y = rng.uniform(floor, bottom - h)
        if page and y < page[-1]['y'] + page[-1]['h'] and x < page[-1]['x'] + page[-1]['w'] + pad:
            continue  # same row as the previous piece: only to its right, so it still reads in order
        if any(x < q['x'] + q['w'] + pad and q['x'] < x + w + pad and y < q['y'] + q['h'] + pad
               and q['y'] < y + h + pad for q in page):
            continue
        score = y + rng.uniform(0, 120)
        if best is None or score < best[0]:
            best = (score, x, y)
    return best and best[1:]


def scatter_pages(groups, rng, cfg, m, W, region):
    """One page per sentence (more if it doesn't fit); pieces sit in screen px."""
    top, bottom = region
    base = cfg['base_size']
    pages = []
    for g in groups:
        page = []
        for line in g['lines']:
            for piece in chunk_line(line, cfg):
                size = base * rng.uniform(*cfg['scatter_size'])
                if line['emphasis'] or any(c['red'] for c in piece):
                    size *= rng.uniform(1.3, 1.6)
                if len(piece) == 1 and rng.random() < 0.5:
                    size *= rng.uniform(1.4, 2.2)  # a lone char now and then goes huge
                size = min(size, (bottom - top) * 0.4)
                w = m.width(''.join(c['c'] for c in piece), size)
                if w > W - 2 * cfg['scatter_margin']:
                    size *= (W - 2 * cfg['scatter_margin']) / w
                    w = W - 2 * cfg['scatter_margin']
                h = size * 1.18
                spot = find_spot(page, w, h, rng, cfg, W, top, bottom)
                if spot is None and page:
                    pages.append(page)
                    page = []
                    spot = find_spot(page, w, h, rng, cfg, W, top, bottom)
                x, y = spot or (cfg['scatter_margin'], top)
                page.append({'chars': piece, 'x': x, 'y': y, 'w': w, 'h': h, 'size': size,
                             'emphasis': line['emphasis']})
        pages.append(page)
    for page in pages:
        if not page:
            continue
        # pieces pile up near the top; stretch the gaps (never the pieces) and centre the page
        y0 = min(q['y'] for q in page)
        extent = lambda k: max((q['y'] - y0) * k + q['h'] for q in page)
        k = cfg['scatter_spread']
        while k > 1 and extent(k) > bottom - top:
            k = max(1, k - 0.05)
        off = top + max(0, (bottom - top - extent(k)) / 2)
        for q in page:
            q['y'] = off + (q['y'] - y0) * k
    return [p for p in pages if p]


def resolve_background(cfg, user, proj, fps):
    """-> (kind, media): kind is grid/room/video/image, media is {src, path, frames} for files."""
    value = cfg['background']
    if 'background' not in user:
        auto = next((proj / f'bg{e}' for e in MEDIA_EXT if (proj / f'bg{e}').exists()), None)
        if auto:
            value = auto.name
    if value in ('grid', 'room'):
        return value, None
    cands = [Path(value), proj / value, BG_DIR / value] + [BG_DIR / f'{value}{e}' for e in MEDIA_EXT]
    path = next((c for c in cands if c.suffix.lower() in MEDIA_EXT and c.exists()), None)
    if not path:
        raise SystemExit(f'background {value!r} not found in {proj} or {BG_DIR}')
    kind = MEDIA_EXT[path.suffix.lower()]
    frames = 0
    if kind == 'video':
        import subprocess
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                              str(path)], capture_output=True, text=True).stdout.strip()
        frames = max(1, math.floor(float(out) * fps) - 1)
    return kind, {'src': 'bg' + path.suffix.lower(), 'path': str(path.resolve()), 'frames': frames}


def half_beats(beat_frames):
    return [round((a + b) / 2) for a, b in zip(beat_frames, beat_frames[1:])]


def plan_camera(groups, laid, cfg, beat_frames, anchor_box):
    keys = []
    for i, (g, L) in enumerate(zip(groups, laid)):
        first = [ln['src']['chars'][0]['f'] for ln in L['lines'] if ln['src']['chars']]
        g0 = first[0]
        upto = 0  # last row already framed by the group's first key
        x, y, z = fit(L, 0, cfg, anchor_box)
        if i == 0:
            keys.append({'f': 0, 'd': 1, 'x': x, 'y': y, 'rot': L['cam_rot'], 'zoom': z, 'ease': 'out'})
        else:
            # always exactly one 90° turn; a paragraph break only makes it slower and smoother
            d = cfg['para_turn_frames'] if g['para'] else cfg['rot_frames']
            # the new sentence must already be showing while the page turns (it is carried in
            # by the rotation), so the turn starts right around its first char, never long before
            prev_last = laid[i - 1]['last_f']
            lead = 3 if g['para'] else 1
            want = g0 - lead
            lo, hi = max(prev_last + 1, want - 2), g0 + 4
            cands = [b for b in beat_frames if lo <= b <= hi]
            if not cands:  # fast songs: a beat gap can be wider than the window, the off-beat (and) is fine
                cands = [h for h in half_beats(beat_frames) if lo <= h <= hi]
            # without any beat start just before the first char, never with the paragraph lead
            f = min(cands, key=lambda b: abs(b - want)) if cands else max(lo, g0 - 1)
            # a char shown before the turn would flash sideways; hold it until the page turns
            for ln in L['lines']:
                for c in ln['src']['chars']:
                    c['f'] = max(c['f'], f)
            first = [ln['src']['chars'][0]['f'] for ln in L['lines'] if ln['src']['chars']]
            # rows that start while the page is still turning are framed by the turn itself:
            # a reframe key in the middle would cut the turn short of a clean 90°
            while upto + 1 < len(first) and first[upto + 1] <= f + d:
                upto += 1
            x, y, z = fit(L, upto, cfg, anchor_box)
            keys.append({'f': f, 'd': d, 'x': x, 'y': y, 'rot': L['cam_rot'], 'zoom': z,
                         'ease': 'spin' if g['para'] else 'out'})
            L['above_f'] = f + (d + 1) // 2  # slides under the card until the turn is half done
        for k in range(upto + 1, len(L['lines'])):
            if not L['lines'][k]['src']['chars']:
                continue
            x, y, z = fit(L, k, cfg, anchor_box)
            f = max(first[k] - 1, keys[-1]['f'] + 1)
            keys.append({'f': f, 'd': cfg['line_cam_frames'], 'x': x, 'y': y, 'rot': L['cam_rot'],
                         'zoom': z, 'ease': 'out'})
    return keys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    a = ap.parse_args()
    proj = Path(a.project)
    cfg = json.loads(json.dumps(DEFAULTS))
    user = {}
    if (proj / 'config.json').exists():
        user = json.loads((proj / 'config.json').read_text(encoding='utf-8'))
        cfg.update({k: v for k, v in user.items() if k != 'colors'})
        cfg['colors'].update(user.get('colors', {}))
    fps, W, H = cfg['fps'], cfg['width'], cfg['height']
    scatter = cfg['layout'] == 'scatter'
    if scatter and 'reveal_mix' not in user:
        cfg['reveal_mix'] = ['pop', 'tumble', 'rise']
    bg_kind, bg_media = resolve_background(cfg, user, proj, fps)
    if bg_media and 'text_shadow' not in user:
        cfg['text_shadow'] = 0.6  # white text over footage needs some separation
    col = cfg['colors']
    rng = random.Random(cfg['seed'])
    font_path, font_weight = resolve_font(cfg['font'], cfg['font_weight'])
    m = Measurer(font_path, font_weight)

    groups = parse((proj / 'script.txt').read_text(encoding='utf-8'))
    build = proj / 'build'
    words_p, beats_p = build / 'words.json', build / 'beats.json'
    beats = json.loads(beats_p.read_text(encoding='utf-8')) if beats_p.exists() else None
    voice = None if cfg.get('music_only') else next(
        (p.name for p in [proj / 'voice.mp3', proj / 'voice.wav', proj / 'voice.m4a'] if p.exists()), None)
    bgm = next((p.name for p in [proj / 'bgm.mp3', proj / 'bgm.wav', proj / 'bgm.m4a'] if p.exists()), None)

    if voice and words_p.exists():
        words = json.loads(words_p.read_text(encoding='utf-8'))
        n = sum(len(l['chars']) for g in groups for l in g['lines'])
        if len(words) != n:
            raise SystemExit(f'words.json has {len(words)} chars but script has {n}; rerun align.py')
        frames_from_words(groups, words, fps)
    elif beats:
        frames_from_beats(groups, beats, fps)
    else:
        raise SystemExit('need voice + build/words.json, or bgm + build/beats.json')

    beat_frames = [round(t * fps) for t in beats['beats']] if beats else []
    down_frames = [round(t * fps) for t in beats['downbeats']] if beats else []
    if beats and voice:
        snap_to_beats(groups, beat_frames, down_frames, cfg)

    if not scatter:
        laid = place_groups(groups, rng, cfg, m)
        for L in laid:
            L['last_f'] = max(c['f'] for ln in L['lines'] for c in ln['src']['chars'])

    card = None
    if (proj / 'card.png').exists():
        top = round(H * cfg['card_top'])
        card = {'src': 'card.png', 'x': round((W - cfg['card_width']) / 2), 'y': top, 'w': cfg['card_width']}
        region = (110, top - 40)
    else:
        region = (round(H * 0.1), round(H * 0.82)) if scatter else (round(H * 0.17), round(H * 0.79))
    if scatter:
        # world = screen px around the centre; the camera never moves
        anchor = {'x': W / 2, 'y': H / 2}
        pages = scatter_pages(groups, rng, cfg, m, W, region)
        laid = [{'x': 0, 'y': 0, 'rot': 0, 'last_f': max(c['f'] for q in p for c in q['chars']),
                 'lines': [q | {'x': q['x'] - anchor['x'], 'y': q['y'] - anchor['y'], 'src': q} for q in p]}
                for p in pages]
        camera = [{'f': 0, 'd': 1, 'x': 0, 'y': 0, 'rot': 0, 'zoom': 1, 'ease': 'out'}]
    else:
        anchor = {'x': W / 2, 'y': (region[0] + region[1]) / 2}
        anchor_box = (W, region[1] - region[0])
        camera = plan_camera(groups, laid, cfg, beat_frames, anchor_box)

    pulses = []
    if beats:
        downs = set(down_frames)
        pulses += [{'f': b, 'amp': cfg['pulse_downbeat'] if b in downs else cfg['pulse_beat']} for b in beat_frames]
    for g in groups:
        for line in g['lines']:
            if line['emphasis'] and line['chars']:
                pulses.append({'f': line['chars'][0]['f'], 'amp': cfg['pulse_emphasis']})

    last = max(L['last_f'] for L in laid)
    duration = last + round(cfg['tail_seconds'] * fps)
    if voice:
        import subprocess
        out = subprocess.run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0',
                              str(proj / voice)], capture_output=True, text=True).stdout.strip()
        if out:
            duration = max(duration, math.ceil((float(out) + 0.4) * fps))

    pulses = sorted((p for p in pulses if p['f'] < duration), key=lambda p: p['f'])

    fx_rng = random.Random(cfg['seed'] + 1)  # separate stream: changing effects never moves the layout
    out_groups = []
    for gi, L in enumerate(laid):
        lines = []
        for li, ln in enumerate(L['lines']):
            chars = []
            for c in ln['src']['chars']:
                color = (col['deep_red'] if ln['emphasis'] else col['red']) if c['red'] else col['white']
                chars.append({'c': c['c'], 'f': c['f'], 'color': color})
            # a row that arrives with the turn is slammed by the turn itself; scaling it up
            # while it is still sideways leaves a giant ghost over the card
            punch = ln['emphasis'] and (scatter or not (gi > 0 and li == 0))
            lines.append({k: round(ln[k], 2) for k in ('x', 'y', 'w', 'size')}
                         | {'emphasis': ln['emphasis'], 'punch': punch, 'chars': chars,
                            'fx': fx_rng.choice(cfg['reveal_mix']) if cfg['reveal'] == 'mix' else cfg['reveal']})
        out_groups.append({'x': round(L['x'], 2), 'y': round(L['y'], 2), 'rot': L['rot'],
                           'above': L.get('above_f', 0),
                           'f': min(c['f'] for ln in lines for c in ln['chars']), 'lines': lines})

    bgm_volume = cfg['bgm_volume'] if cfg['bgm_volume'] is not None else (0.28 if voice else 0.9)
    timeline = {
        'fps': fps, 'width': W, 'height': H, 'durationFrames': duration,
        'anchor': anchor,
        'style': {'bg': col['bg'], 'gridSize': cfg['grid_size'], 'gridColor': col['grid'], 'dim': col['dim'],
                  'font': font_path.name, 'fontSrc': str(font_path), 'weight': font_weight,
                  'background': bg_kind, 'bgMedia': bg_media, 'bgDim': cfg['bg_dim'], 'shadow': cfg['text_shadow'], 'stroke': cfg['text_stroke'], 'revealFrames': cfg['reveal_frames'],
                  'keepPrevGroups': 0 if scatter else cfg['keep_prev_groups']},
        'audio': {'voice': voice, 'voiceVolume': cfg['voice_volume'], 'bgm': bgm, 'bgmVolume': bgm_volume,
                  'bgmStartFrom': round(float(cfg['bgm_offset']) * fps)},
        'card': card,
        'cover': {'text': cfg['cover'], 'frames': cfg['cover_frames'], 'color': col['cover']} if cfg['cover'] else None,
        'groups': out_groups,
        'camera': [{k: (round(v, 3) if isinstance(v, float) else v) for k, v in key.items()} for key in camera],
        'pulses': pulses,
    }
    build.mkdir(exist_ok=True)
    (build / 'timeline.json').write_text(json.dumps(timeline, ensure_ascii=False), encoding='utf-8')
    print(f'{len(out_groups)} groups, {len(camera)} camera keys, {len(pulses)} pulses, '
          f'{duration} frames ({duration / fps:.1f}s) -> {build / "timeline.json"}')


if __name__ == '__main__':
    main()
