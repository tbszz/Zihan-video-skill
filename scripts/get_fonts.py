"""Download the extra fonts listed in assets/fonts/extra-fonts.json (free for commercial use,
but not redistributed in this repo).

usage: python get_fonts.py [file ...]     (no names = all)
"""
import json
import sys
import urllib.request
from pathlib import Path

FONTS = Path(__file__).resolve().parent.parent / 'assets' / 'fonts'


def main():
    items = {k: v for k, v in json.loads((FONTS / 'extra-fonts.json').read_text(encoding='utf-8')).items()
             if not k.startswith('_')}
    for name in sys.argv[1:] or list(items):
        out = FONTS / name
        if out.exists():
            print('have', name)
            continue
        req = urllib.request.Request(items[name]['file'], headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as r:
            out.write_bytes(r.read())
        print('got', name, items[name]['title'], items[name]['license'])


if __name__ == '__main__':
    main()
