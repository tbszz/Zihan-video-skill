"""Download the template background videos listed in assets/backgrounds/backgrounds.json.

usage: python get_backgrounds.py [name ...]     (no names = all)
Each clip is cut to 20s, 720x1280, 24fps, no sound -> assets/backgrounds/<name>.mp4,
ready for config "background": "<name>".
"""
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

BG = Path(__file__).resolve().parent.parent / 'assets' / 'backgrounds'


def main():
    items = {k: v for k, v in json.loads((BG / 'backgrounds.json').read_text(encoding='utf-8')).items()
             if not k.startswith('_')}
    names = sys.argv[1:] or list(items)
    for name in names:
        out = BG / f'{name}.mp4'
        if out.exists():
            print('have', out.name)
            continue
        raw = BG / f'_{name}.raw.mp4'
        req = urllib.request.Request(items[name]['file'], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as r, open(raw, 'wb') as f:
            f.write(r.read())
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(raw), '-t', '20', '-an', '-vf',
                        'scale=720:1280:force_original_aspect_ratio=increase,crop=720:1280,fps=24',
                        '-c:v', 'libx264', '-crf', '23', '-pix_fmt', 'yuv420p', str(out)], check=True)
        raw.unlink()
        print('got', out.name, out.stat().st_size // 1024, 'KB')


if __name__ == '__main__':
    main()
