import { Composition } from 'remotion';
import { ZihanVideo } from './ZihanVideo';
import type { Timeline } from './types';

const placeholder: Timeline = {
  fps: 24,
  width: 720,
  height: 1280,
  durationFrames: 48,
  anchor: { x: 360, y: 520 },
  style: {
    bg: '#000000',
    gridSize: 40,
    gridColor: '#262626',
    dim: '#6b6b6b',
    background: 'grid',
    font: 'NotoSansSC-VF.ttf',
    weight: 900,
    shadow: 0,
    stroke: 0,
    revealFrames: 4,
    keepPrevGroups: 2,
  },
  audio: { voice: null, voiceVolume: 1, bgm: null, bgmVolume: 0.3, bgmStartFrom: 0 },
  card: null,
  cover: null,
  groups: [],
  camera: [{ f: 0, d: 1, x: 0, y: 0, rot: 0, zoom: 1, ease: 'out' }],
  pulses: [],
};

export const Root: React.FC = () => (
  <Composition
    id="ZihanVideo"
    component={ZihanVideo}
    defaultProps={placeholder}
    width={720}
    height={1280}
    fps={24}
    durationInFrames={48}
    calculateMetadata={({ props }) => ({
      durationInFrames: props.durationFrames,
      fps: props.fps,
      width: props.width,
      height: props.height,
    })}
  />
);
