"""Give every display char of script.txt a start time, from the voice track.

faster-whisper supplies word timestamps; the script text is the source of truth,
so recognition typos (负能/赋能) only borrow timing, never wording.

usage: python align.py <project_dir> [--voice voice.mp3] [--model small]
writes build/words.json: [{"c": "华", "t": 0.12}, ...] in display order.
"""
import argparse
import difflib
import json
from pathlib import Path

from script_format import alignable, display_chars, normalize, parse


def whisper_chars(audio, model_name):
    from faster_whisper import WhisperModel

    model = WhisperModel(model_name, device='cpu', compute_type='int8')
    segs, _ = model.transcribe(
        str(audio), language='zh', word_timestamps=True,
        # never pass the script itself: whisper then treats it as already heard and skips audio
        initial_prompt='以下是普通话的句子。',
    )
    out = []
    for seg in segs:
        for w in seg.words or []:
            cs = [c for c in w.word if alignable(c)]
            if not cs:
                continue
            step = (w.end - w.start) / len(cs)
            out += [(normalize(c), float(w.start) + i * step) for i, c in enumerate(cs)]
    return out


def align(script_chars, heard):
    idx = [i for i, c in enumerate(script_chars) if alignable(c)]
    a = [normalize(script_chars[i]) for i in idx]
    b = [c for c, _ in heard]
    times = [None] * len(a)
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal' or (tag == 'replace' and i2 - i1 == j2 - j1):
            for k in range(i2 - i1):
                times[i1 + k] = heard[j1 + k][1]
        elif tag == 'replace':  # uneven replace: spread the heard span over the script span
            t0, t1 = heard[j1][1], heard[j2 - 1][1]
            for k in range(i2 - i1):
                times[i1 + k] = t0 + (t1 - t0) * k / max(1, i2 - i1 - 1)
    matched = sum(t is not None for t in times)
    # fill the gaps linearly between known neighbours
    known = [i for i, t in enumerate(times) if t is not None]
    for i in range(len(times)):
        if times[i] is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        if prev is None and nxt is None:
            times[i] = 0.0
        elif prev is None:
            times[i] = times[nxt]
        elif nxt is None:
            times[i] = times[prev] + 0.12 * (i - prev)
        else:
            times[i] = times[prev] + (times[nxt] - times[prev]) * (i - prev) / (nxt - prev)
    full = [None] * len(script_chars)
    for k, i in enumerate(idx):
        full[i] = times[k]
    for i in range(len(full) - 1, -1, -1):  # spaces/punct take the next char's time
        if full[i] is None:
            full[i] = full[i + 1] if i + 1 < len(full) else (full[i - 1] if i else 0.0)
    for i in range(1, len(full)):  # never go backwards
        full[i] = max(full[i], full[i - 1])
    return full, matched / max(1, len(a))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--voice', default=None)
    ap.add_argument('--model', default='small')
    a = ap.parse_args()
    proj = Path(a.project)
    groups = parse((proj / 'script.txt').read_text(encoding='utf-8'))
    chars = display_chars(groups)
    voice = Path(a.voice) if a.voice else next(
        (p for p in [proj / 'voice.mp3', proj / 'voice.wav', proj / 'voice.m4a'] if p.exists()), None
    )
    if voice is None:
        raise SystemExit('no voice file in project')
    heard = whisper_chars(voice, a.model)
    times, ratio = align(chars, heard)
    (proj / 'build').mkdir(exist_ok=True)
    out = proj / 'build' / 'words.json'
    out.write_text(
        json.dumps([{'c': c, 't': round(t, 3)} for c, t in zip(chars, times)], ensure_ascii=False),
        encoding='utf-8',
    )
    print(f'aligned {len(chars)} chars, {ratio:.0%} matched exactly -> {out}')
    if ratio < 0.7:
        print('WARNING: low match ratio; check that script.txt matches what the voice says')


if __name__ == '__main__':
    main()
