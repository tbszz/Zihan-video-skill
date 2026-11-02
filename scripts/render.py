"""Render build/timeline.json with the Remotion engine, then make a check sheet.

usage: python render.py <project_dir> [--out out/video.mp4] [--frames 0-120]
The engine (../engine) is shared; each project only supplies a public dir.
"""
import argparse
import json
import shutil
import subprocess
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
ENGINE = SKILL / 'engine'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--out', default=None)
    ap.add_argument('--frames', default=None, help='e.g. 0-120 for a quick partial render')
    a = ap.parse_args()
    proj = Path(a.project).resolve()
    tl_path = proj / 'build' / 'timeline.json'
    tl = json.loads(tl_path.read_text(encoding='utf-8'))

    if not (ENGINE / 'node_modules').exists():
        subprocess.run('npm install --no-audit --no-fund', cwd=ENGINE, shell=True, check=True)

    public = proj / 'build' / 'public'
    public.mkdir(parents=True, exist_ok=True)
    font = public / tl['style']['font']
    if not font.exists():
        shutil.copy(tl['style'].get('fontSrc') or SKILL / 'assets' / 'fonts' / tl['style']['font'], font)
    for name in [tl['audio']['voice'], tl['audio']['bgm'], tl['card'] and tl['card']['src']]:
        if name:
            shutil.copy(proj / name, public / name)
    media = tl['style'].get('bgMedia')
    if media:
        shutil.copy(media['path'], public / media['src'])

    out = Path(a.out) if a.out else proj / 'out' / f'{proj.name}.mp4'
    out = out if out.is_absolute() else proj / out
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = ['npx', 'remotion', 'render', 'src/index.ts', 'ZihanVideo', str(out),
           f'--props={tl_path}', f'--public-dir={public}']
    if a.frames:
        cmd.append(f'--frames={a.frames}')
    subprocess.run(' '.join(f'"{c}"' if ' ' in c else c for c in cmd), cwd=ENGINE, shell=True, check=True)

    sheet = out.with_name(out.stem + '_sheet.png')
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(out), '-vf',
                    'fps=1,scale=180:-1,tile=8x5', '-frames:v', '1', str(sheet)], check=True)
    print('video:', out)
    print('check sheet:', sheet)


if __name__ == '__main__':
    main()
