"""Parse the Zihan script markup (see references/script-format.md).

One non-empty line   = one group = one 90° camera turn.
`/`                  = line break inside the group.
`[词]` or `【词】`     = red keyword.
`!` at a line start  = emphasis line (bigger, punched in, keywords deep red).
blank line           = paragraph break -> the next 90° turn is slower and smoother.
`#` at line start    = comment.
"""
import re

PUNCT = set('，。、！？；：,.!?;:“”"‘’\'（）()《》<>…—-~～·')
END_PUNCT = set('，。！？；：,.!?;:…')


def parse(text):
    groups = []
    pending_para = False
    for raw in text.splitlines():
        s = raw.strip()
        if s.startswith('#'):
            continue
        if not s:
            pending_para = bool(groups)
            continue
        lines = []
        for part in s.split('/'):
            part = part.strip()
            if not part:
                continue
            emphasis = part[0] in '!！'
            if emphasis:
                part = part[1:].strip()
            chars, spoken, red = [], [], False
            for ch in part:
                if ch in '[【':
                    red = True
                    continue
                if ch in ']】':
                    red = False
                    continue
                spoken.append(ch)
                if ch in PUNCT:
                    continue
                chars.append({'c': ch, 'red': red})
            if not any(c['red'] for c in chars) and emphasis:
                for c in chars:  # an emphasis line with no marked keyword is red as a whole
                    c['red'] = c['c'] != ' '
            lines.append({'emphasis': emphasis, 'chars': chars, 'spoken': ''.join(spoken).strip()})
        if lines:
            groups.append({'lines': lines, 'para': pending_para})
        pending_para = False
    return groups


def narration(groups):
    """Text to send to TTS: lines joined with commas, groups ended with full stops."""
    out = []
    for g in groups:
        parts = []
        for i, line in enumerate(g['lines']):
            t = line['spoken']
            if not t:
                continue
            last = i == len(g['lines']) - 1
            if t[-1] not in END_PUNCT:
                t += '。' if last else '，'
            parts.append(t)
        out.append(''.join(parts))
    return '\n'.join(out)


def display_chars(groups):
    """Flat list of display chars in reading order (spaces included)."""
    return [c['c'] for g in groups for line in g['lines'] for c in line['chars']]


def normalize(ch):
    ch = ch.lower()
    # full-width ASCII -> half-width
    if '！' <= ch <= '～':
        ch = chr(ord(ch) - 0xFEE0)
    return ch


def alignable(ch):
    return bool(ch.strip()) and ch not in PUNCT and not re.match(r'\s', ch)
