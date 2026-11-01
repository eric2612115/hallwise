import React from 'react';
import {AbsoluteFill, Composition} from 'remotion';
import proof from '../public/data/proof.json';
import {Proof, PROOF_FRAMES, FPS} from './Proof';
import {XRay} from './comps/XRay';
import {BuzzPop} from './comps/BuzzPop';
import {Subtitles, subtitleTurnsFromRec, SubtitleTurn} from './comps/Subtitles';
import {Room} from './comps/Room';
import {DeckMorph} from './comps/DeckMorph';
import {CheckStrike} from './comps/CheckStrike';
import {Connector} from './comps/Connector';
import {EndCard} from './comps/EndCard';
import {Voices} from './comps/Voices';
import type {ProofData} from './lib/types';

// Every composition takes its data as a prop (defaultProps come from public/data/proof.json, written by
// tools/extract_data.py from an events.jsonl, its xray sidecar and the saved checks), so another recording is a
// matter of re-running the tool and passing --props. Overlay compositions (suffix "Overlay") draw on transparency,
// for a ProRes 4444 export composited over footage with ffmpeg.
const data = proof as unknown as ProofData;
const W = 1920,
  H = 1080;

// Kenji's Japanese aside from the ETH Taipei afterparty (recording c42b): the turn, its logged translation and
// turn_kind, the name and colour from that recording's own cast.
const jaTurns = (d: ProofData): SubtitleTurn[] => {
  const k = d.evidence.kenji_japanese;
  return subtitleTurnsFromRec({id: k.id, cast: k.cast, turns: k.turns.map((t) => ({...t, kind: t.turn === 10 ? k.turn_kind : null}))}, [10], {10: k.translation});
};

const SubtitlesFR: React.FC<{data: ProofData}> = ({data: d}) => (
  <AbsoluteFill>
    <Room rec={d.rec3f3e} startMs={52000} />
    <Subtitles turns={subtitleTurnsFromRec(d.rec3f3e, [11, 12, 13])} startMs={52000} />
  </AbsoluteFill>
);
const SubtitlesJA: React.FC<{data: ProofData}> = ({data: d}) => {
  const turns = jaTurns(d);
  return (
    <AbsoluteFill>
      <Room rec={d.rec3f3e} startMs={0} meter={false} slate={false} />
      <Subtitles turns={turns} startMs={turns[0].start_ms - 1500} />
    </AbsoluteFill>
  );
};
const XRayFull: React.FC<{data: ProofData}> = ({data: d}) => (
  <AbsoluteFill>
    <Room rec={d.rec3f3e} startMs={d.rec3f3e.freeze_ms} frozen={1} />
    <XRay data={d} freezeMs={d.rec3f3e.freeze_ms} />
  </AbsoluteFill>
);
const XRayOverlay: React.FC<{data: ProofData}> = ({data: d}) => <XRay data={d} freezeMs={d.rec3f3e.freeze_ms} transparent />;
// the cut without beats 04 and 05 while the FOA comparison is PENDING: the cards re-flow and renumber
const XRayFallback: React.FC<{data: ProofData}> = ({data: d}) => (
  <AbsoluteFill>
    <Room rec={d.rec3f3e} startMs={d.rec3f3e.freeze_ms} frozen={1} />
    <XRay data={d} freezeMs={d.rec3f3e.freeze_ms} beats={[1, 2, 3, 6, 7, 8, 9, 10, 11, 12]} />
  </AbsoluteFill>
);
const BuzzBoth: React.FC<{data: ProofData}> = ({data: d}) => <BuzzPop data={d} pops={['deck', 'hook']} />;
const BuzzDeck: React.FC<{data: ProofData}> = ({data: d}) => <BuzzPop data={d} pops={['deck']} />;
const BuzzHook: React.FC<{data: ProofData}> = ({data: d}) => <BuzzPop data={d} pops={['hook']} hero="She said her name. The badge knew her colleague." />;
const VoicesSofa: React.FC<{data: ProofData}> = ({data: d}) => <Voices data={d} startMs={50000} endMs={100000} />;

export const Root: React.FC = () => (
  <>
    <Composition id="Proof" component={Proof} width={W} height={H} fps={FPS} durationInFrames={PROOF_FRAMES} defaultProps={{data}} />
    <Composition id="XRay" component={XRayFull} width={W} height={H} fps={FPS} durationInFrames={360} defaultProps={{data}} />
    <Composition id="XRayOverlay" component={XRayOverlay} width={W} height={H} fps={FPS} durationInFrames={360} defaultProps={{data}} />
    <Composition id="XRayFallback" component={XRayFallback} width={W} height={H} fps={FPS} durationInFrames={330} defaultProps={{data}} />
    <Composition id="BuzzBoth" component={BuzzBoth} width={W} height={H} fps={FPS} durationInFrames={180} defaultProps={{data}} />
    <Composition id="BuzzDeck" component={BuzzDeck} width={W} height={H} fps={FPS} durationInFrames={120} defaultProps={{data}} />
    <Composition id="BuzzHook" component={BuzzHook} width={W} height={H} fps={FPS} durationInFrames={120} defaultProps={{data}} />
    <Composition id="SubtitlesFR" component={SubtitlesFR} width={W} height={H} fps={FPS} durationInFrames={300} defaultProps={{data}} />
    <Composition id="SubtitlesJA" component={SubtitlesJA} width={W} height={H} fps={FPS} durationInFrames={240} defaultProps={{data}} />
    <Composition id="DeckMorph" component={DeckMorph} width={W} height={H} fps={FPS} durationInFrames={150} defaultProps={{data, seconds: 5}} />
    <Composition id="CheckStrike" component={CheckStrike} width={W} height={H} fps={FPS} durationInFrames={150} defaultProps={{data}} />
    <Composition id="Connector" component={Connector} width={W} height={H} fps={FPS} durationInFrames={150} defaultProps={{data}} />
    <Composition id="Voices" component={VoicesSofa} width={W} height={H} fps={FPS} durationInFrames={300} defaultProps={{data}} />
    <Composition id="EndCard" component={EndCard} width={W} height={H} fps={FPS} durationInFrames={120} defaultProps={{data}} />
  </>
);
