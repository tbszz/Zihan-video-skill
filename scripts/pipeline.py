"""Run the whole Zihan video chain for one project folder.

usage: python pipeline.py <project_dir> [--tts] [--voice-name zh-CN-YunxiNeural] [--rate +20%]
                          [--skip-render] [--frames 0-120]

steps: card.txt -> card.png (if no card.png)
       --tts or no voice file -> voice.mp3 via edge-tts (skipped in music-only mode)
       voice -> build/words.json
       bgm -> build/beats.json
       build/timeline.json -> out/<name>.mp4 + check sheet
       check_turns.py: every turn exactly 90°, pivoting, on beat -> out/turns/turn_XX.png
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(script, *args):
    print(f'\n== {script} {" ".join(args)}')
    subprocess.run([sys.executable, str(HERE / script), *args], check=True)


def find(proj, stem):
    return next((p for p in [proj / f'{stem}.mp3', proj / f'{stem}.wav', proj / f'{stem}.m4a'] if p.exists()), None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--tts', action='store_true', help='regenerate voice.mp3 even if one exists')
    ap.add_argument('--voice-name', default='zh-CN-YunxiNeural')
    ap.add_argument('--rate', default='+20%')
    ap.add_argument('--skip-render', action='store_true')
    ap.add_argument('--frames', default=None)
    a = ap.parse_args()
    proj = Path(a.project).resolve()
    if not (proj / 'script.txt').exists():
        raise SystemExit(f'{proj}/script.txt is missing')
    cfg = json.loads((proj / 'config.json').read_text(encoding='utf-8')) if (proj / 'config.json').exists() else {}
    music_only = bool(cfg.get('music_only'))

    if (proj / 'card.txt').exists() and not (proj / 'card.png').exists():
        run('make_card.py', str(proj))
    if not music_only and (a.tts or not find(proj, 'voice')):
        run('tts.py', str(proj), '--voice', a.voice_name, '--rate', a.rate)
    if not music_only:
        run('align.py', str(proj))
    if find(proj, 'bgm'):
        run('beats.py', str(proj))
    elif music_only:
        raise SystemExit('music_only needs bgm.mp3 in the project')
    run('build_timeline.py', str(proj))
    chain = cfg.get('layout', 'chain') == 'chain'  # scatter has no camera turns to check
    if chain:
        run('check_turns.py', str(proj), '--no-strips')  # stop here rather than render a bad camera
    if not a.skip_render:
        run('render.py', str(proj), *(['--frames', a.frames] if a.frames else []))
        if chain and not a.frames:
            run('check_turns.py', str(proj))  # per-turn frame strips for the visual check


if __name__ == '__main__':
    main()
