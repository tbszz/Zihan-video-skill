// Timeline produced by scripts/build_timeline.py. All positions are in world units
// (group-local for lines), all times are in frames.

export type Char = { c: string; f: number; color: string };

export type Line = {
  x: number; // left edge, relative to group centre
  y: number; // top edge, relative to group centre
  w: number;
  size: number;
  emphasis: boolean;
  punch: boolean; // slam in from a bigger scale (emphasis rows that don't arrive with a turn)
  fx: 'slide' | 'waterfall' | 'flip'; // how each char comes in
  chars: Char[];
};

export type Group = {
  x: number;
  y: number;
  rot: number;
  f: number;
  above: number; // from this frame on the group is drawn above the card (mid-turn)
  lines: Line[];
};

export type CameraKey = {
  f: number; // transition start
  d: number; // transition length
  x: number;
  y: number;
  rot: number;
  zoom: number;
  ease: 'out' | 'spin';
};

export type Pulse = { f: number; amp: number };

export type Timeline = {
  fps: number;
  width: number;
  height: number;
  durationFrames: number;
  anchor: { x: number; y: number };
  style: {
    bg: string;
    gridSize: number;
    gridColor: string;
    dim: string;
    font: string;
    weight: number;
    shadow: number; // black text-shadow opacity, 0 = none
    stroke: number; // black outline width in world px, 0 = none
    revealFrames: number;
    keepPrevGroups: number;
  };
  audio: {
    voice: string | null;
    voiceVolume: number;
    bgm: string | null;
    bgmVolume: number;
    bgmStartFrom: number;
  };
  card: { src: string; x: number; y: number; w: number } | null;
  cover: { text: string; frames: number; color: string } | null;
  groups: Group[];
  camera: CameraKey[];
  pulses: Pulse[];
};
