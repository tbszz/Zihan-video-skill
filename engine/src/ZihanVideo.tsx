import { useEffect, useMemo, useState } from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  Loop,
  OffthreadVideo,
  Sequence,
  cancelRender,
  continueRender,
  delayRender,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import type { CameraKey, Char, Group, Line, Timeline } from './types';

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeOut = (t: number) => 1 - Math.pow(1 - t, 3);
// Whip spin: slow start, violent middle, soft landing.
const easeSpin = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

type Cam = { x: number; y: number; rot: number; zoom: number };
type Pt = { x: number; y: number };

// The camera is a similarity screen = a·world + b in complex numbers, a = zoom·e^(-i·rot).
const cmul = (p: Pt, q: Pt): Pt => ({ x: p.x * q.x - p.y * q.y, y: p.x * q.y + p.y * q.x });
const cdiv = (p: Pt, q: Pt): Pt => {
  const n = q.x * q.x + q.y * q.y;
  return { x: (p.x * q.x + p.y * q.y) / n, y: (p.y * q.x - p.x * q.y) / n };
};
const polar = (r: number, deg: number): Pt => ({
  x: r * Math.cos((deg * Math.PI) / 180),
  y: r * Math.sin((deg * Math.PI) / 180),
});
const toAB = (c: Cam, anchor: Pt) => {
  const a = polar(c.zoom, -c.rot);
  const ac = cmul(a, c);
  return { a, b: { x: anchor.x - ac.x, y: anchor.y - ac.y } };
};

// Spiral similarity: every point of the page orbits one fixed screen point, so a turn reads
// as the whole page pivoting 90° (with a zoom) instead of x, y, rot and zoom flying apart.
const transition = (from: Cam, k: CameraKey, frame: number, anchor: Pt): Cam => {
  const t = clamp01((frame - k.f) / Math.max(1, k.d));
  const e = k.ease === 'spin' ? easeSpin(t) : easeOut(t);
  const rot = from.rot + (k.rot - from.rot) * e;
  const zoom = from.zoom * Math.pow(k.zoom / from.zoom, e);
  const A = toAB(from, anchor);
  const B = toAB(k, anchor);
  const k1 = cdiv(B.a, A.a);
  const den = { x: 1 - k1.x, y: -k1.y };
  let b: Pt;
  if (Math.hypot(den.x, den.y) < 1e-4) {
    b = { x: A.b.x + (B.b.x - A.b.x) * e, y: A.b.y + (B.b.y - A.b.y) * e };
  } else {
    const kb = cmul(k1, A.b);
    const pivot = cdiv({ x: B.b.x - kb.x, y: B.b.y - kb.y }, den);
    const kt = polar(Math.pow(k.zoom / from.zoom, e), -(k.rot - from.rot) * e);
    const r = cmul(kt, { x: A.b.x - pivot.x, y: A.b.y - pivot.y });
    b = { x: r.x + pivot.x, y: r.y + pivot.y };
  }
  // back to (centre, rot, zoom): centre = (anchor - b) / a
  const c = cdiv({ x: anchor.x - b.x, y: anchor.y - b.y }, polar(zoom, -rot));
  return { x: c.x, y: c.y, rot, zoom };
};

// A key that starts before the previous one finished picks up from wherever the camera is.
const cameraAt = (keys: CameraKey[], frame: number, anchor: Pt): Cam => {
  let from: Cam = keys[0];
  let active = keys[0];
  for (let i = 1; i < keys.length && keys[i].f <= frame; i++) {
    from = transition(from, active, keys[i].f, anchor);
    active = keys[i];
  }
  return transition(from, active, frame, anchor);
};

const hexToRgb = (hex: string) => {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
};

const mix = (a: string, b: string, t: number) => {
  const A = hexToRgb(a);
  const B = hexToRgb(b);
  const c = A.map((v, i) => Math.round(v + (B[i] - v) * t));
  return `rgb(${c[0]},${c[1]},${c[2]})`;
};

const easeOutBack = (t: number) => 1 + 2.70158 * Math.pow(t - 1, 3) + 1.70158 * Math.pow(t - 1, 2);
const rnd = (n: number) => {
  const x = Math.sin(n * 12.9898 + 78.233) * 43758.5453;
  return x - Math.floor(x);
};

// the bouncy / noisy entrances need a couple of frames more than the plain ones to read
const FX_LEN: Partial<Record<Line['fx'], number>> = { tumble: 1.5, pop: 1.25, glitch: 1.5 };

// Per-char entrances, all a few frames long so they never hold up the page turns.
// t = 0..1 progress of this char, seed = stable per char.
const charMotion = (fx: Line['fx'], t: number, size: number, seed: number): React.CSSProperties => {
  const r = 1 - easeOut(t);
  if (fx === 'waterfall') return { transform: `translateY(${(-0.7 * size * r).toFixed(2)}px)` };
  if (fx === 'flip') return { transform: `perspective(${(size * 6).toFixed(0)}px) rotateY(${(180 * r).toFixed(1)}deg)` };
  if (fx === 'slide') return { transform: `translateX(${(-0.45 * size * r).toFixed(2)}px)` };
  if (fx === 'tumble') {
    // tipped over at a random angle, falls into place and settles with a small bounce
    const b = 1 - easeOutBack(t);
    const dir = rnd(seed) < 0.5 ? -1 : 1;
    const ang = dir * (30 + 40 * rnd(seed + 1));
    return {
      transform: `translate(${(0.25 * dir * size * b).toFixed(2)}px, ${(0.45 * size * b).toFixed(2)}px) rotate(${(ang * b).toFixed(1)}deg) scale(${(1 + 0.3 * b).toFixed(3)})`,
    };
  }
  if (fx === 'pop') return { transform: `scale(${(0.2 + 0.8 * easeOutBack(t)).toFixed(3)})` };
  if (fx === 'rise') return { transform: `translateY(${(100 * r).toFixed(1)}%)` };
  if (fx === 'glitch') {
    const k = 1 - t;
    const dx = (0.08 * size * k).toFixed(1);
    return {
      transform: `translateX(${((rnd(seed * 7 + Math.floor(t * 8)) - 0.5) * 0.14 * size * k).toFixed(2)}px)`,
      textShadow: `${dx}px 0 rgba(255,0,64,0.85), -${dx}px 0 rgba(0,229,255,0.85)`,
    };
  }
  return {};
};

const CharSpan: React.FC<{
  ch: Char;
  idx: number;
  frame: number;
  size: number;
  dim: string;
  fx: Line['fx'] | null;
  dur: number;
}> = ({ ch, idx, frame, size, dim, fx, dur }) => {
  if (frame < ch.f) return <span style={{ opacity: 0 }}>{ch.c}</span>;
  const t = clamp01((frame - ch.f) / (dur * ((fx && FX_LEN[fx]) || 1)));
  const e = easeOut(t);
  const glyph = (
    <span
      style={{
        display: 'inline-block',
        opacity: (fx === 'waterfall' ? 0.15 : 0.35) + (fx === 'waterfall' ? 0.85 : 0.65) * e,
        color: mix(dim, ch.color, e),
        ...(t < 1 && fx ? charMotion(fx, t, size, ch.f * 31 + idx * 17) : {}),
        whiteSpace: 'pre',
      }}
    >
      {ch.c}
    </span>
  );
  // rise slides up out of a mask the size of the char
  if (fx === 'rise' && t < 1) {
    return <span style={{ display: 'inline-block', overflow: 'hidden', verticalAlign: 'top' }}>{glyph}</span>;
  }
  return glyph;
};

// A 3D grid room: ceiling and floor in perspective, fading into the dark at eye level.
// Each line has its own faint tint, like the coloured fringes of a filmed grid.
type Seg = { x1: number; y1: number; x2: number; y2: number; w: number; c: string };
const roomLines = (W: number, H: number): Seg[] => {
  const cx = W / 2;
  const cy = H / 2;
  const f = H * 0.55; // focal length
  const eye = 5; // eye height above the floor / below the ceiling, in grid cells (fewer = bigger cells)
  const zNear = ((f * eye) / (H / 2)) * 0.8; // a little in front of the screen edge
  const zFar = 32; // stop before the dark band, converging lines there only make moire
  const segs: Seg[] = [];
  for (const side of [-1, 1]) {
    const y = (z: number) => cy + (side * f * eye) / z;
    for (let x = -22; x <= 22; x++) {
      segs.push({
        x1: cx + (f * x) / zNear, y1: y(zNear), x2: cx + (f * x) / zFar, y2: y(zFar), w: 3.2,
        c: `hsl(${(x * 47 + side * 70 + 720) % 360} 45% 72%)`,
      });
    }
    for (let z = Math.ceil(zNear); z <= zFar; z++) {
      segs.push({
        x1: 0, y1: y(z), x2: W, y2: y(z), w: Math.max(0.8, (3.4 * zNear) / z),
        c: `hsl(${(z * 61 + side * 40 + 720) % 360} 35% 74%)`,
      });
    }
  }
  return segs;
};

const Room: React.FC<{ w: number; h: number; glow: number }> = ({ w, h, glow }) => {
  const segs = useMemo(() => roomLines(w, h), [w, h]);
  return (
    <AbsoluteFill>
      <svg width={w} height={h} style={{ position: 'absolute', opacity: glow }}>
        {segs.map((s, i) => (
          <line key={i} x1={s.x1} y1={s.y1} x2={s.x2} y2={s.y2} stroke={s.c} strokeWidth={s.w} strokeOpacity={0.7} />
        ))}
      </svg>
      <AbsoluteFill
        style={{
          background:
            'linear-gradient(rgba(0,0,0,0) 12%, rgba(0,0,0,0.92) 39%, #000 50%, rgba(0,0,0,0.92) 61%, rgba(0,0,0,0) 88%)',
        }}
      />
    </AbsoluteFill>
  );
};

const LineView: React.FC<{ line: Line; frame: number; dim: string; dur: number }> = ({ line, frame, dim, dur }) => {
  const start = line.chars.length ? line.chars[0].f : 0;
  if (frame < start) return null;
  // Emphasis lines are slammed in from a huge scale instead of sliding.
  const punch = line.punch ? 1 + 0.8 * (1 - easeOut(clamp01((frame - start) / 6))) : 1;
  return (
    <div
      style={{
        position: 'absolute',
        left: line.x,
        top: line.y,
        width: line.w,
        height: line.size * 1.18,
        fontSize: line.size,
        lineHeight: 1.18,
        whiteSpace: 'nowrap',
        transform: `scale(${punch})`,
        transformOrigin: '50% 55%',
      }}
    >
      {line.chars.map((ch, i) => (
        <CharSpan
          key={i}
          idx={i}
          ch={ch}
          frame={frame}
          size={line.size}
          dim={dim}
          // an emphasis row that slams in doesn't also slide sideways
          fx={line.punch && line.fx === 'slide' ? null : line.fx}
          dur={dur}
        />
      ))}
    </div>
  );
};

const GroupView: React.FC<{ group: Group; frame: number; opacity: number; dim: string; dur: number }> = ({
  group,
  frame,
  opacity,
  dim,
  dur,
}) => (
  <div
    style={{
      position: 'absolute',
      left: 0,
      top: 0,
      transform: `translate(${group.x}px, ${group.y}px) rotate(${group.rot}deg)`,
      opacity,
    }}
  >
    {group.lines.map((line, i) => (
      <LineView key={i} line={line} frame={frame} dim={dim} dur={dur} />
    ))}
  </div>
);

const useFont = (file: string) => {
  const [handle] = useState(() => delayRender('font ' + file));
  useEffect(() => {
    const face = new FontFace('ZihanSans', `url(${staticFile(file)})`, { weight: '100 900' });
    face
      .load()
      .then((f) => {
        document.fonts.add(f);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
  }, [file, handle]);
};

export const ZihanVideo: React.FC<Timeline> = (tl) => {
  const frame = useCurrentFrame();
  useFont(tl.style.font);

  const cam = cameraAt(tl.camera, frame, tl.anchor);
  const prevCam = cameraAt(tl.camera, Math.max(0, frame - 1), tl.anchor);
  const spinSpeed = Math.abs(cam.rot - prevCam.rot); // deg per frame
  const blur = Math.min(4, spinSpeed * 0.12);

  let pulse = 1;
  for (const p of tl.pulses) {
    const dt = frame - p.f;
    if (dt >= 0 && dt < 10) pulse += p.amp * Math.exp(-dt / 2.5);
  }
  // beat pulse scales about the anchor: a' = pulse·a, b' = anchor + pulse·(b - anchor)
  const { a, b } = toAB(cam, tl.anchor);
  const m = [
    a.x * pulse,
    a.y * pulse,
    -a.y * pulse,
    a.x * pulse,
    tl.anchor.x + pulse * (b.x - tl.anchor.x),
    tl.anchor.y + pulse * (b.y - tl.anchor.y),
  ];

  const started = tl.groups.filter((g) => frame >= g.f).length;
  const s = tl.style;

  // Older groups sit under the card; only the group being read is drawn above it,
  // and only once its turn is half done so it never sweeps across the card.
  const world = (current: boolean) => (
    <div
      style={{
        position: 'absolute',
        left: 0,
        top: 0,
        fontFamily: 'ZihanSans, "Noto Sans SC", sans-serif',
        fontWeight: s.weight,
        textShadow: s.shadow ? `0 0.05em 0.12em rgba(0,0,0,${s.shadow})` : undefined,
        WebkitTextStroke: s.stroke ? `${s.stroke}px #000` : undefined,
        paintOrder: 'stroke fill',
        filter: blur > 0.3 ? `blur(${blur.toFixed(2)}px)` : undefined,
        transform: `matrix(${m.map((v) => v.toFixed(5)).join(',')})`,
        transformOrigin: '0 0',
      }}
    >
      {tl.groups.map((g, i) => {
        if (frame < g.f) return null;
        const age = started - 1 - i; // 0 = current group
        if (age > s.keepPrevGroups || (age === 0 && frame >= g.above) !== current) return null;
        const opacity = age === 0 ? 1 : age === 1 ? 0.9 : 0.3;
        return <GroupView key={i} group={g} frame={frame} opacity={opacity} dim={s.dim} dur={s.revealFrames} />;
      })}
    </div>
  );

  return (
    <AbsoluteFill style={{ backgroundColor: s.bg, overflow: 'hidden' }}>
      {(s.background === 'video' || s.background === 'image') && s.bgMedia ? (
        // footage fills the frame and bumps a little on every beat
        <AbsoluteFill style={{ transform: `scale(${1 + (pulse - 1) * 0.6})` }}>
          {s.background === 'video' ? (
            <Loop durationInFrames={s.bgMedia.frames}>
              <OffthreadVideo
                src={staticFile(s.bgMedia.src)}
                muted
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            </Loop>
          ) : (
            <Img src={staticFile(s.bgMedia.src)} style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          )}
          <AbsoluteFill style={{ backgroundColor: `rgba(0,0,0,${s.bgDim ?? 0})` }} />
        </AbsoluteFill>
      ) : s.background === 'room' ? (
        // the room brightens a touch on every beat
        <Room w={tl.width} h={tl.height} glow={Math.min(1, 0.8 + (pulse - 1) * 4)} />
      ) : (
        <AbsoluteFill
          style={{
            backgroundImage: `linear-gradient(${s.gridColor} 1px, transparent 1px), linear-gradient(90deg, ${s.gridColor} 1px, transparent 1px)`,
            backgroundSize: `${s.gridSize}px ${s.gridSize}px`,
            backgroundPosition: `${(tl.width / 2) % s.gridSize}px ${(tl.height / 2) % s.gridSize}px`,
          }}
        />
      )}

      {world(false)}

      {tl.card ? (
        <Img
          src={staticFile(tl.card.src)}
          style={{
            position: 'absolute',
            left: tl.card.x,
            top: tl.card.y,
            width: tl.card.w,
            boxShadow: '0 10px 40px rgba(0,0,0,0.6)',
          }}
        />
      ) : null}

      {world(true)}

      {tl.cover ? (
        <Sequence durationInFrames={tl.cover.frames}>
          <AbsoluteFill
            style={{
              justifyContent: 'center',
              alignItems: 'center',
              backgroundColor: s.bg,
              fontFamily: 'ZihanSans, "Noto Sans SC", sans-serif',
              fontWeight: s.weight,
              fontSize: 76,
              lineHeight: 1.2,
              color: tl.cover.color,
              textAlign: 'center',
              padding: '0 60px',
              whiteSpace: 'pre-line',
            }}
          >
            {tl.cover.text}
          </AbsoluteFill>
        </Sequence>
      ) : null}

      {tl.audio.voice ? <Audio src={staticFile(tl.audio.voice)} volume={tl.audio.voiceVolume} /> : null}
      {tl.audio.bgm ? (
        <Audio
          src={staticFile(tl.audio.bgm)}
          volume={tl.audio.bgmVolume}
          startFrom={tl.audio.bgmStartFrom}
        />
      ) : null}
    </AbsoluteFill>
  );
};
