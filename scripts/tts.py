"""Generate voice.mp3 from script.txt with edge-tts.

usage: python tts.py <project_dir> [--voice zh-CN-YunxiNeural] [--rate +20%]
"""
import argparse
import asyncio
from pathlib import Path

import edge_tts

from script_format import narration, parse


async def synth(text, voice, rate, out):
    await edge_tts.Communicate(text, voice, rate=rate).save(str(out))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('project')
    ap.add_argument('--voice', default='zh-CN-YunxiNeural')
    ap.add_argument('--rate', default='+20%')
    a = ap.parse_args()
    proj = Path(a.project)
    text = narration(parse((proj / 'script.txt').read_text(encoding='utf-8')))
    (proj / 'build').mkdir(exist_ok=True)
    (proj / 'build' / 'narration.txt').write_text(text, encoding='utf-8')
    asyncio.run(synth(text, a.voice, a.rate, proj / 'voice.mp3'))
    print('wrote', proj / 'voice.mp3')


if __name__ == '__main__':
    main()
