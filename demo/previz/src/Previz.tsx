import React from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';
import {shotlist, beatAt, Beat} from './data';
import {theme} from './proj';
import {Apartment} from './Apartment';
import {InfoPanel} from './InfoPanel';
import {Subtitle} from './Subtitle';
import {TimelineStrip} from './TimelineStrip';
import {Soundtrack} from './Soundtrack';

const Swatch: React.FC<{color: string; label: string; dashed?: boolean}> = ({color, label, dashed}) => (
  <span style={{display: 'inline-flex', alignItems: 'center', gap: 7, marginLeft: 22, fontSize: 13, color: theme.inkSoft}}>
    <span style={{width: 22, height: 0, borderTop: `3px ${dashed ? 'dashed' : 'solid'} ${color}`}} />
    {label}
  </span>
);

// What the film inserts in post at this moment, shown in a fixed box at the plan's top right.
const Insert: React.FC<{t: number; beat: Beat}> = ({t, beat}) => {
  const rel = t - beat.start;
  let title = '', body: React.ReactNode = null;
  const k = beat.key;
  if (k === 'bed') { title = 'INSERT · the blank reply'; body = <>Hi <u>___</u>, great to meet you at <u>___</u>! As promised, here's the <u>___</u><div style={{marginTop: 6, color: theme.inkSoft}}>Card: After every mixer.</div></>; }
  else if (k === 'out') { title = rel < beat.hot_at! ? 'INSERT · the name card' : 'TITLE'; body = rel < beat.hot_at! ? <>Lock screen: <b>Eric · Hallwise</b></> : <><b style={{fontSize: 24}}>Hallwise</b><div>A name badge that remembers the room.</div></>; }
  else if (k === 'door' && rel < 5.2) { title = 'DISCLOSURE'; body = <span style={{fontSize: 12.5}}>AI guests: voices by ElevenLabs, faces by Muse Image, their web pages invented. My friend and I are real.</span>; }
  else if (k === 'door') { title = 'PANEL'; body = <>● <s style={{color: theme.inkFaint}}>grey dot</s> → <b>Leo Wong · Bright Path</b><div>promise · deck · tonight</div></>; }
  else if (k === 'french') { title = 'PANEL'; body = <>● ● two grey dots, no names<div style={{color: theme.inkSoft}}>FR → EN, <i>translated</i></div></>; }
  else if (k === 'whisper') { title = 'SOUND · post'; body = <>Hard cut to silence. Only the whisper.<div style={{color: theme.inkSoft}}>The last French subtitle stays.</div></>; }
  else if (k === 'names' && rel >= 6.3) { title = 'NOTIFICATION · live'; body = <><b>She may be Chloé's colleague</b><div>Blockchain Week · Oct 23</div></>; }
  else if (k === 'names') { title = 'PANEL'; body = <>● ● the dots become <b>Margaux</b> and <b>Julien</b></>; }
  else if (k === 'chloe' && rel >= 21.5) { title = 'PANEL'; body = <>promise · <b>a call next week, the three of us</b> · Margaux, Chloé<div style={{color: theme.inkSoft}}>paid off on his sofa: the invite</div></>; }
  else if (k === 'chloe') { title = 'PANEL'; body = <>Margaux · Chloé's colleague · Corvane Capital<div style={{color: theme.inkSoft}}>Chloé Martin · Blockchain Week, Oct 23</div></>; }
  else if (k === 'waiter' && rel >= 3.0) { title = 'INSERT · the deck, rebuilt'; body = <><span style={{letterSpacing: 2}}>▭▭▭▭▭▭▭</span> → <b>▮ one page, numbers first</b><div style={{color: theme.hot, fontSize: 12.5}}>Julien Caron · unverified · confirm before you send</div></>; }
  else if (k === 'itdoes') { title = 'INSERT · the one-pager holds'; body = <><b>▮ one page, numbers first</b></>; }
  else if (k === 'xray') { title = 'X-RAY · post'; body = <>Freeze-frame; the film rewinds into the machinery.</>; }
  else if (k === 'call') { title = 'PANEL'; body = <>● grey dot · JA → EN, <i>translated</i><div style={{color: theme.inkSoft}}>topic kept: field logs for robots</div></>; }
  else if (k === 'table' && rel >= 9) { title = 'PANEL'; body = <>◎ <b>Siddharth</b> · met before · Blockchain Week</>; }
  else if (k === 'kenji' && rel >= 3.6) { title = 'PANEL'; body = <>◎ <b>Kenji</b> · met before · Hardware meetup, Oct 22</>; }
  else if (k === 'coffee' && rel >= 11.6) { title = 'PANEL'; body = <>coffee · <s>Thursday</s> → <b>Friday</b></>; }
  else if (k === 'stop') { title = 'STOP'; body = <>The split frame ends. Nothing from the morning yet.</>; }
  else if (k === 'invite' && rel >= 2.3) { title = 'INSERT · the invite (real draft)'; body = <><b>Call · Margaux Lefèvre, Chloé Martin</b> (Corvane) · 30 min<div style={{fontSize: 12.5}}><b>Tue Nov 3 · 11:00–11:30</b> · avoids your board call, Wed Nov 4 14:00–15:30</div><div style={{fontSize: 11.5, color: theme.inkSoft, marginTop: 3, lineHeight: 1.25}}>"Margaux, lovely to join you tonight. As Chloé told me you'd want to see this, I'll send an invite for a call next week with you and Chloé. Would Tuesday at 11:00 work? / Eric"</div><div style={{fontSize: 12.5, color: theme.friend}}>Send</div></>; }
  else if (k === 'connector' && rel >= 0.4) { title = 'INSERT · the connector'; body = <><b>Introduce Kenji to Ben?</b><div style={{fontSize: 12.5}}>Ben Walker, Stride Mobility (Founder dinner, Oct 24) wants a small robot arm for his Taoyuan frame line · Kenji builds them (Hoshizora)</div><div style={{fontSize: 12.5, color: theme.friend}}>Both at the Nangang hardware meetup · Thu Nov 5</div></>; }
  else if (k === 'end') { title = 'END CARD'; body = <><b>Hallwise</b> · Muse Voice Transcribe · Muse Spark · SAM 3.1 · Muse Spark Open on Baseten<div style={{color: theme.inkSoft, fontSize: 12.5}}>Open source, AGPL-3.0</div></>; }
  if (!title) return null;
  return (
    <div style={{position: 'absolute', left: 862, top: 92, width: 326, minHeight: 60, background: theme.panel, border: `1.5px solid ${theme.hot}`, borderRadius: 8, padding: '8px 12px', fontFamily: theme.sans, fontSize: 14, lineHeight: 1.3, color: theme.ink}}>
      <div style={{fontSize: 10.5, letterSpacing: 2, fontWeight: 700, color: theme.hot, marginBottom: 4}}>{title}</div>
      {body}
    </div>
  );
};

export const Previz: React.FC = () => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = frame / fps;
  const beat = beatAt(t);
  const hot = beat.temp === 'hot' || (beat.hot_at !== undefined && t - beat.start >= beat.hot_at);

  return (
    <AbsoluteFill style={{background: theme.paper, fontFamily: theme.sans, color: theme.ink}}>
      {/* title bar */}
      <div style={{position: 'absolute', left: 40, top: 22, fontSize: 18, fontWeight: 800, letterSpacing: 2.5}}>HALLWISE · DEMO SHOOT · PREVIZ</div>
      <div style={{position: 'absolute', left: 40, top: 48, fontSize: 12.5, color: theme.inkSoft}}>2.5D plan of the living-room take · who stands where, where the camera looks, which device plays which voice · from shotlist.json</div>
      <div style={{position: 'absolute', right: 40, top: 28, display: 'flex', alignItems: 'center'}}>
        <Swatch color={theme.eric} label="Eric (badge)" dashed />
        <Swatch color={theme.friend} label="Friend" dashed />
        <Swatch color={theme.camera} label="Camera + view" dashed />
        <Swatch color={theme.sound} label="Playing" />
        <Swatch color={theme.hot} label="Hot" />
        <Swatch color={theme.cold} label="Cold" />
      </div>

      {/* the plan's frame, coloured by temperature */}
      <div style={{position: 'absolute', left: 30, top: 82, width: 1170, height: 740, border: `3px solid ${hot ? theme.hot : theme.cold}`, borderRadius: 8, opacity: beat.silence || beat.xray ? 0 : 0.9}} />

      <Apartment t={t} beat={beat} frame={frame} />
      <Insert t={t} beat={beat} />
      <Subtitle t={t} beat={beat} />
      <InfoPanel t={t} beat={beat} />
      <TimelineStrip t={t} />
      <Soundtrack />

      {beat.key === 'end' && (
        <div style={{position: 'absolute', left: 30, top: 82, width: 1170, height: 740, background: '#1A1613', opacity: 0.92, borderRadius: 8, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', color: '#E8E2D6'}}>
          <div style={{fontSize: 64, fontWeight: 800, letterSpacing: 2}}>Hallwise</div>
          <div style={{fontSize: 22, marginTop: 10}}>A name badge that remembers the room.</div>
          <div style={{fontSize: 15, marginTop: 34, color: '#A39C90'}}>Built with Muse Voice Transcribe · Muse Spark · SAM 3.1 · Muse Spark Open on Baseten</div>
          <div style={{fontSize: 15, marginTop: 6, color: '#A39C90'}}>Open source, AGPL-3.0</div>
        </div>
      )}
    </AbsoluteFill>
  );
};
