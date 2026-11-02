"""Check every camera turn of a rendered Zihan video.

usage: python check_turns.py <project_dir> [--video out/x.mp4] [--no-strips]

Replays the same camera math as engine/src/ZihanVideo.tsx (spiral similarity about a
fixed screen point) and checks, for each turn:
  - the camera turns exactly 90° (left or right), the angle grows monotonically;
  - after the turn the previous sentence stands vertical and the new one is level;
  - the pivot of the turn is on screen (a far-away pivot makes text sweep off like it was thrown);
  - the previous sentence mostly leaves the screen (only a peek stays);
  - the new sentence starts next to the previous sentence's first character;
  - the turn starts on a music beat.
It also writes out/turns/turn_XX.png: frames f-1 .. f+d+2 with the pivot marked, for eyeballing.
Exits with status 1 if any hard check fails.
"""
import argparse
import cmath
import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw


def ease_out(t):
    return 1 - (1 - t) ** 3


def ease_spin(t):
    return 4 * t ** 3 if t < 0.5 else 1 - (-2 * t + 2) ** 3 / 2


def to_ab(c, anchor):
    a = cmath.rect(c['zoom'], math.radians(-c['rot']))
    return a, anchor - a * complex(c['x'], c['y'])


def pivot_of(frm, k, anchor):
    a0, b0 = to_ab(frm, anchor)
    a1, b1 = to_ab(k, anchor)
    k1 = a1 / a0
    if abs(1 - k1) < 1e-4:
        return None
    return (b1 - k1 * b0) / (1 - k1)


def transition(frm, k, frame, anchor):
    t = min(1.0, max(0.0, (frame - k['f']) / max(1, k['d'])))
    e = ease_spin(t) if k['ease'] == 'spin' else ease_out(t)
    rot = frm['rot'] + (k['rot'] - frm['rot']) * e
    zoom = frm['zoom'] * (k['zoom'] / frm['zoom']) ** e
    a0, b0 = to_ab(frm, anchor)
    _, b1 = to_ab(k, anchor)
    s = pivot_of(frm, k, anchor)
    if s is None:
        b = b0 + (b1 - b0) * e
    else:
        kt = cmath.rect((k['zoom'] / frm['zoom']) ** e, math.radians(-(k['rot'] - frm['rot']) * e))
        b = kt * (b0 - s) + s
    c = (anchor - b) / cmath.rect(zoom, math.radians(-rot))
    return {'x': c.real, 'y': c.imag, 'rot': rot, 'zoom': zoom}


def camera_state(keys, frame, anchor):
    """(camera, active key, state the active key started from)"""
    frm, active = keys[0], keys[0]
    for k in keys[1:]:
        if k['f'] > frame:
            break
        frm = transition(frm, active, k['f'], anchor)
        active = k
    return transition(frm, active, frame, anchor), active, frm


def to_screen(cam, anchor, w):
    a, b = to_ab(cam, anchor)
    return a * w + b


def line_points(g, ln):
    """world corners and first-char centre of a line"""
    G, R = complex(g['x'], g['y']), cmath.rect(1, math.radians(g['rot']))
    h = ln['size'] * 1.18
    corners = [complex(ln['x'], ln['y']), complex(ln['x'] + ln['w'], ln['y']),
               complex(ln['x'] + ln['w'], ln['y'] + h), complex(ln['x'], ln['y'] + h)]
    first = complex(ln['x'] + ln['size'] / 2, ln['y'] + h / 2)
    return [G + R * p for p in corners], G + R * first


def visible_fraction(polys, W, H, n=24):
    """share of the text area that is inside the frame (sampled)"""
    inside = total = 0
    for p in polys:
        w = abs(p[1] - p[0]) * abs(p[3] - p[0])  # weight by area: a tiny last line must not count as much as a huge one
        for i in range(n):
            for j in range(n):
                u, v = (i + 0.5) / n, (j + 0.5) / n
                q = p[0] + (p[1] - p[0]) * u + (p[3] - p[0]) * v
                total += w
                inside += w * (0 <= q.real <= W and 0 <= q.imag <= H)
    return inside / total if total else 0


def norm_angle(a):
    return (a + 180) % 360 - 180


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--video', default=None)
    ap.add_argument('--no-strips', action='store_true')
    a = ap.parse_args()
    proj = Path(a.project).resolve()
    tl = json.loads((proj / 'build' / 'timeline.json').read_text(encoding='utf-8'))
    beats_p = proj / 'build' / 'beats.json'
    beat_frames, half_frames = set(), set()
    if beats_p.exists():
        bf = [round(t * tl['fps']) for t in json.loads(beats_p.read_text(encoding='utf-8'))['beats']]
        beat_frames = set(bf)
        half_frames = {round((a_ + b) / 2) for a_, b in zip(bf, bf[1:])}  # the off-beat "and"
    W, H = tl['width'], tl['height']
    anchor = complex(tl['anchor']['x'], tl['anchor']['y'])
    keys, groups = tl['camera'], tl['groups']

    turns = []  # (key index, group index)
    gi = 0
    for i in range(1, len(keys)):
        if abs(keys[i]['rot'] - keys[i - 1]['rot']) > 1e-6:
            gi += 1
            turns.append((i, gi))

    fails, warns, rows = [], [], []
    for n, (ki, gi) in enumerate(turns, 1):
        k = keys[ki]
        _, _, frm = camera_state(keys, k['f'], anchor)
        d_rot = k['rot'] - frm['rot']
        prev, cur = groups[gi - 1], groups[gi]
        end = k['f'] + k['d']
        cam_end = camera_state(keys, end, anchor)[0]
        # the frame just before the next turn (or the end) is where the reader sees the peek
        nxt = turns[n][0] if n < len(turns) else None
        settle = (keys[nxt]['f'] - 1) if nxt else tl['durationFrames'] - 1
        cam_settle = camera_state(keys, settle, anchor)[0]

        angles = [camera_state(keys, f, anchor)[0]['rot'] for f in range(k['f'], end + 1)]
        monotonic = all((b - a_) * d_rot >= -1e-6 for a_, b in zip(angles, angles[1:]))
        prev_screen = norm_angle(prev['rot'] - cam_end['rot'])
        cur_screen = norm_angle(cur['rot'] - cam_end['rot'])
        s = pivot_of(frm, k, anchor)
        pivot_ok = s is not None and -0.1 * W <= s.real <= 1.1 * W and -0.1 * H <= s.imag <= 1.1 * H

        prev_polys = [[to_screen(cam_settle, anchor, p) for p in line_points(prev, ln)[0]] for ln in prev['lines']]
        peek = visible_fraction(prev_polys, W, H)
        # the new first line sits level with the first char of the previous last line,
        # and its near end (start on a right turn, end on a left turn) touches that column
        pc, pf = line_points(prev, prev['lines'][-1])
        corners, _ = line_points(cur, cur['lines'][0])
        P = to_screen(cam_end, anchor, pf)
        col = [to_screen(cam_end, anchor, p).real for p in pc]  # x-extent of the vertical column
        Q = [to_screen(cam_end, anchor, p) for p in corners]
        unit = cur['lines'][0]['size'] * cam_end['zoom']
        level = abs(P.imag - (Q[0].imag + Q[3].imag) / 2) / unit
        near_x = min(Q[0].real, Q[1].real, key=lambda x: abs(x - P.real))
        edge = min(min(col), max(col), key=lambda x: abs(x - near_x))
        gap_chars = abs(edge - near_x) / unit  # edge to edge
        on_beat = (k['f'] in beat_frames or k['f'] in half_frames) if beat_frames else None

        checks = {
            '90°': abs(abs(d_rot) - 90) < 1e-6,
            'smooth': monotonic,
            'prev vertical': abs(abs(prev_screen) - 90) < 1e-6,
            'new level': abs(cur_screen) < 1e-6,
            'pivot on screen': pivot_ok,
            'prev off screen': peek <= 0.45,
            'joins prev first char': level <= 0.6 and gap_chars <= 1.0,
            # otherwise the old sentence swings away over an empty screen and looks thrown
            'new text shows during turn': k['f'] - 4 <= cur['f'] <= k['f'] + 2,
        }
        bad = [name for name, ok in checks.items() if not ok]
        fails += [f'turn {n}: {b}' for b in bad]
        if on_beat is False:
            warns.append(f'turn {n}: not on a beat (no beat close enough to the first char)')
        first_text = ''.join(c['c'] for c in cur['lines'][0]['chars'])
        rows.append((n, k, d_rot, s, peek, gap_chars, bad, first_text, frm))
        side = '字顺时针' if d_rot < 0 else '字逆时针'
        ps = f'({s.real:.0f},{s.imag:.0f})' if s is not None else '—'
        beat = '' if on_beat is None else (
            ' 踩拍' if k['f'] in beat_frames else ' 踩半拍' if on_beat else ' 未踩拍')
        print(f'turn {n:2d} f={k["f"]:4d} d={k["d"]:2d}{beat} 入字f={cur["f"]} {side} {d_rot:+.0f}°  pivot={ps}  '
              f'上一句可见 {peek:4.0%}  接口: 高差 {level:.2f} 字 / 间距 {gap_chars:.1f} 字  '
              f'{"OK" if not bad else "FAIL: " + ", ".join(bad)}  「{first_text}」')

    video = Path(a.video) if a.video else proj / 'out' / f'{proj.name}.mp4'
    if not a.no_strips and video.exists() and rows:
        write_strips(video, rows, proj / 'out' / 'turns', W, H, tl['durationFrames'])
        print('strips:', proj / 'out' / 'turns')

    print(f'{len(turns)} turns, {len(fails)} problems, {len(warns)} warnings')
    for f in fails + warns:
        print('  ', f)
    sys.exit(1 if fails else 0)


def write_strips(video, rows, out_dir, W, H, duration):
    out_dir.mkdir(parents=True, exist_ok=True)
    spans = [(max(0, k['f'] - 1), min(duration - 1, k['f'] + k['d'] + 2)) for _, k, *_ in rows]
    sel = '+'.join(f'between(n,{a},{b})' for a, b in spans)
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(video), '-vf', f"select='{sel}',scale=180:-1",
                        '-fps_mode', 'passthrough', str(Path(tmp) / '%05d.png')], check=True)
        files = sorted(Path(tmp).glob('*.png'))
        wanted = sorted({f for a, b in spans for f in range(a, b + 1)})
        frame_file = dict(zip(wanted, files))
        sc = 180 / W
        for (n, k, d_rot, s, *_rest), (a, b) in zip(rows, spans):
            tiles = [Image.open(frame_file[f]).convert('RGB') for f in range(a, b + 1) if f in frame_file]
            if not tiles:
                continue
            tw, th = tiles[0].size
            strip = Image.new('RGB', (tw * len(tiles), th + 18), 'black')
            dr = ImageDraw.Draw(strip)
            for i, (f, im) in enumerate(zip(range(a, b + 1), tiles)):
                strip.paste(im, (i * tw, 18))
                dr.text((i * tw + 4, 3), f'f{f}' + (' turn' if f == k['f'] else ''), fill='yellow')
                if s is not None:
                    x, y = i * tw + s.real * sc, 18 + s.imag * sc
                    dr.ellipse((x - 4, y - 4, x + 4, y + 4), outline='cyan', width=2)
            strip.save(out_dir / f'turn_{n:02d}.png')


if __name__ == '__main__':
    main()
