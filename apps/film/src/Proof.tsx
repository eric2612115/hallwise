import React from 'react';
import {AbsoluteFill, Sequence, useCurrentFrame, useVideoConfig, staticFile} from 'remotion';
import {Audio} from '@remotion/media';
import {Room} from './comps/Room';
import {Subtitles, subtitleTurnsFromRec} from './comps/Subtitles';
import {BuzzPop} from './comps/BuzzPop';
import {XRay} from './comps/XRay';
import {DeckMorph} from './comps/DeckMorph';
import {CheckStrike} from './comps/CheckStrike';
import {Connector} from './comps/Connector';
import {EndCard} from './comps/EndCard';
import {clamp, fadeInOut, seg} from './lib/motion';
import {theme} from './theme';
import type {ProofData} from './lib/types';

// The Proof: 39.5 s at 1920x1080 that strings every component over the FOA rehearsal's audio and events as stand-in
// footage. The shot list is `SHOTS`; each shot is a Sequence with a fade in and out, and the audio windows are the
// badge's own W/Y channels decoded to stereo (tools/prep_audio.sh).
export type ProofProps = {data: ProofData};

// ms into recording 20261027-064036-3f3e where each audio window file starts (tools/prep_audio.sh arguments)
const AUDIO = {
  aside: {file: 'audio/aside_52-62.wav', startMs: 52000},
  onepage: {file: 'audio/onepage_83-92.wav', startMs: 83000},
  kenji: {file: 'audio/kenji_121-129.wav', startMs: 121500},
  bed: {file: 'audio/bed_44-100.wav', startMs: 44000},
};

export const FPS = 30;
export const SHOTS = [
  {id: 'aside', seconds: 7.5},
  {id: 'hook', seconds: 4.5},
  {id: 'xray', seconds: 11.5},
  {id: 'deck', seconds: 4.5},
  {id: 'check', seconds: 4.0},
  {id: 'connector', seconds: 4.0},
  {id: 'end', seconds: 3.5},
] as const;
export const PROOF_FRAMES = SHOTS.reduce((n, s) => n + Math.round(s.seconds * FPS), 0);

const startOf = (id: (typeof SHOTS)[number]['id']) => {
  let f = 0;
  for (const s of SHOTS) {
    if (s.id === id) return f;
    f += Math.round(s.seconds * FPS);
  }
  return f;
};
const framesOf = (id: (typeof SHOTS)[number]['id']) => Math.round(SHOTS.find((s) => s.id === id)!.seconds * FPS);

const Fade: React.FC<{total: number; children: React.ReactNode; inF?: number; outF?: number}> = ({total, children, inF = 6, outF = 6}) => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{opacity: fadeInOut(frame, total, inF, outF)}}>{children}</AbsoluteFill>;
};

// The X-ray shot: the room freezes (0.3 s xfade into desaturated blur), the cards rise, and the freeze releases on
// the buzz with the same xfade. The room's slate and meter stay hidden until the X-ray's header has all but gone,
// so the two never double-expose in the same corner.
const XRayShot: React.FC<{data: ProofData; total: number; freezeMs: number}> = ({data, total, freezeMs}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const freezeIn = Math.round(fps * 0.3);
  const beats = Math.round(fps * 0.85) * 12;
  const release = beats + Math.round(fps * 0.9);
  const frozen = frame < release ? seg(frame, 0, freezeIn) : 1 - seg(frame, release, Math.round(fps * 0.4));
  const xrayP = frame < release ? 1 : 1 - seg(frame, release, Math.round(fps * 0.35));
  const hudBack = frame < freezeIn || xrayP < 0.15;
  return (
    <AbsoluteFill>
      <Room rec={data.rec3f3e} startMs={freezeMs - (freezeIn / fps) * 1000} frozen={frozen} meter={hudBack} slate={hudBack} holdFrom={freezeIn} />
      <Sequence from={freezeIn} durationInFrames={total - freezeIn} layout="none">
        <AbsoluteFill style={{opacity: xrayP}}>
          <XRay data={data} freezeMs={freezeMs} />
        </AbsoluteFill>
      </Sequence>
    </AbsoluteFill>
  );
};

export const Proof: React.FC<ProofProps> = ({data}) => {
  const rec = data.rec3f3e;
  const FREEZE = rec.freeze_ms; // the end of "One page with numbers tomorrow." (tools/extract_data.py --freeze-turn)
  const aside = subtitleTurnsFromRec(rec, [11, 12, 13]);
  const asideStart = AUDIO.aside.startMs;
  const duck = (fadeAt: number, len: number) => (f: number) => clamp(1 - (f - fadeAt) / len) * 1;

  return (
    <AbsoluteFill style={{backgroundColor: theme.dark}}>
      {/* 1 · the French aside, subtitled, over the live room */}
      <Sequence from={startOf('aside')} durationInFrames={framesOf('aside')} name="aside">
        <Fade total={framesOf('aside')}>
          <Room rec={rec} startMs={asideStart} />
          <Subtitles turns={aside} startMs={asideStart} />
        </Fade>
        <Audio src={staticFile(AUDIO.aside.file)} volume={duck(framesOf('aside') - 12, 12)} />
      </Sequence>

      {/* 2 · the hook on the badge: she may be Chloé's colleague, as the room page shows it (no notification) */}
      <Sequence from={startOf('hook')} durationInFrames={framesOf('hook')} name="hook">
        <Fade total={framesOf('hook')}>
          <BuzzPop data={data} pops={['hook']} buzzAt={10} hero="She said her name. The badge knew her colleague." />
        </Fade>
        <Audio src={staticFile(AUDIO.bed.file)} trimBefore={Math.round(((69600 - AUDIO.bed.startMs) / 1000) * FPS)} volume={1} />
      </Sequence>

      {/* 3 · the X-ray freeze, released on the buzz */}
      <Sequence from={startOf('xray')} durationInFrames={framesOf('xray')} name="xray">
        <Fade total={framesOf('xray')} inF={6} outF={6}>
          <XRayShot data={data} total={framesOf('xray')} freezeMs={FREEZE} />
        </Fade>
        <Audio src={staticFile(AUDIO.onepage.file)} trimBefore={0} volume={(f) => (f < 9 ? 1 : clamp(1 - (f - 9) / 12) * 0.65 + 0.35) * clamp(1 - (f - 250) / 30)} />
      </Sequence>

      {/* 4 · the deck, rebuilt */}
      <Sequence from={startOf('deck')} durationInFrames={framesOf('deck')} name="deck">
        <Fade total={framesOf('deck')}>
          <DeckMorph data={data} seconds={SHOTS[3].seconds} />
        </Fade>
      </Sequence>

      {/* 5 · the check */}
      <Sequence from={startOf('check')} durationInFrames={framesOf('check')} name="check">
        <Fade total={framesOf('check')}>
          <CheckStrike data={data} />
        </Fade>
      </Sequence>

      {/* 6 · the connector, with Kenji's turn under it */}
      <Sequence from={startOf('connector')} durationInFrames={framesOf('connector')} name="connector">
        <Fade total={framesOf('connector')}>
          <Connector data={data} />
        </Fade>
        <Audio src={staticFile(AUDIO.kenji.file)} volume={(f) => 0.7 * clamp(1 - (f - (framesOf('connector') - 15)) / 15)} />
      </Sequence>

      {/* 7 · end card */}
      <Sequence from={startOf('end')} durationInFrames={framesOf('end')} name="end">
        <Fade total={framesOf('end')} outF={16}>
          <EndCard data={data} />
        </Fade>
      </Sequence>
    </AbsoluteFill>
  );
};
