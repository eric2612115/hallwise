import React from 'react';
import {Beat, SPEAKER_COLOR} from './data';
import {theme} from './proj';

// The spoken line, big, under the plan: who, the words, and the English for French and Japanese.
export const Subtitle: React.FC<{t: number; beat: Beat}> = ({t, beat}) => {
  const lines = beat.lines.filter((l) => t >= l.t && t < l.tEnd + 0.6);
  const l = lines[lines.length - 1];
  if (beat.xray) {
    const step = Math.min(7, Math.floor(t - beat.start));
    return (
      <div style={{position: 'absolute', left: 40, top: 838, width: 1150, height: 96, fontFamily: theme.sans}}>
        <div style={{fontSize: 15, letterSpacing: 2, color: theme.cold, fontWeight: 700}}>X-RAY · STEP {step + 1} OF 8 · POST</div>
        <div style={{fontSize: 30, fontWeight: 700, color: theme.ink, marginTop: 6}}>{beat.xraySteps?.[step]}</div>
      </div>
    );
  }
  if (!l) {
    return (
      <div style={{position: 'absolute', left: 40, top: 838, width: 1150, height: 96, fontFamily: theme.sans}}>
        <div style={{fontSize: 15, letterSpacing: 2, color: theme.inkFaint, fontWeight: 700}}>{beat.silence ? 'SILENCE' : 'ERIC'}</div>
        <div style={{fontSize: 18, color: theme.inkSoft, marginTop: 5, lineHeight: 1.3, maxHeight: 72, overflow: 'hidden'}}>{beat.eric.action}</div>
      </div>
    );
  }
  const color = SPEAKER_COLOR[l.who] ?? theme.inkSoft;
  return (
    <div style={{position: 'absolute', left: 40, top: 838, width: 1150, height: 96, fontFamily: theme.sans}}>
      <div style={{display: 'flex', alignItems: 'baseline', gap: 12}}>
        <span style={{fontSize: 15, letterSpacing: 2, color, fontWeight: 700}}>{l.who.toUpperCase()}</span>
        <span style={{fontSize: 13, color: theme.inkFaint, fontFamily: theme.mono}}>{l.device === 'live' ? 'LIVE' : l.device}{l.note ? ` · ${l.note}` : ''}</span>
        {l.choice && <span style={{fontSize: 12, color: '#fff', background: theme.eric, padding: '1px 8px', borderRadius: 4, fontWeight: 700}}>[CHOICE]</span>}
      </div>
      <div style={{fontSize: l.text.length > 90 ? 24 : 28, fontWeight: 600, color: theme.ink, marginTop: 4, lineHeight: 1.2, fontStyle: l.lang !== 'en' ? 'italic' : 'normal'}}>{l.text}</div>
      {l.english && <div style={{fontSize: 20, color: theme.inkSoft, marginTop: 3, lineHeight: 1.2}}>{l.english} <span style={{fontSize: 12, color: theme.cold, fontWeight: 700, letterSpacing: 1, marginLeft: 6}}>TRANSLATED</span></div>}
    </div>
  );
};
