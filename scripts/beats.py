"""Detect beats and downbeats of the given background music.

usage: python beats.py <project_dir> [--music bgm.mp3] [--offset 0]
writes build/beats.json: {"tempo", "beats", "downbeats", "duration"} in seconds,
already shifted so that t=0 is the first second used in the video (--offset).
"""
import argparse
import json
from pathlib import Path

import librosa
import numpy as np


def detect(path, offset=0.0):
    y, sr = librosa.load(str(path), sr=22050, mono=True, offset=offset)
    onset = librosa.onset.onset_strength(y=y, sr=sr)
    tempo, frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, units='frames')
    tempo = float(np.atleast_1d(tempo)[0])
    beats = librosa.frames_to_time(frames, sr=sr)
    # downbeat phase: the one of 4 positions with the most onset energy
    strength = onset[np.minimum(frames, len(onset) - 1)] if len(frames) else np.array([])
    phase = int(np.argmax([strength[p::4].sum() for p in range(4)])) if len(frames) >= 4 else 0
    downbeats = beats[phase::4]
    return {
        'tempo': round(tempo, 2),
        'beats': [round(float(t), 3) for t in beats],
        'downbeats': [round(float(t), 3) for t in downbeats],
        'duration': round(len(y) / sr, 3),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--music', default=None)
    ap.add_argument('--offset', type=float, default=None)
    a = ap.parse_args()
    proj = Path(a.project)
    cfg_path = proj / 'config.json'
    cfg = json.loads(cfg_path.read_text(encoding='utf-8')) if cfg_path.exists() else {}
    offset = a.offset if a.offset is not None else float(cfg.get('bgm_offset', 0))
    music = Path(a.music) if a.music else next(
        (p for p in [proj / 'bgm.mp3', proj / 'bgm.wav', proj / 'bgm.m4a'] if p.exists()), None
    )
    if music is None:
        raise SystemExit('no bgm file in project')
    info = detect(music, offset)
    (proj / 'build').mkdir(exist_ok=True)
    (proj / 'build' / 'beats.json').write_text(json.dumps(info), encoding='utf-8')
    print(f"tempo {info['tempo']} bpm, {len(info['beats'])} beats, {len(info['downbeats'])} downbeats")


if __name__ == '__main__':
    main()
