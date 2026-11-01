import React from 'react';
import {shotlist, Beat, fmtTime, partLabel, SPEAKER_COLOR, poseAt} from './data';
import {theme} from './proj';

const X = 1228, Y = 84, W = 662, H = 858;

const Section: React.FC<{title: string; top: number; height: number; children: React.ReactNode}> = ({title, top, height, children}) => (
  <div style={{position: 'absolute', left: 22, top, width: W - 44, height, overflow: 'hidden'}}>
    <div style={{fontSize: 11, letterSpacing: 2.2, fontWeight: 700, color: theme.inkFaint, fontFamily: theme.sans, borderBottom: `1px solid ${theme.rule}`, paddingBottom: 4, marginBottom: 7}}>{title}</div>
    {children}
  </div>
);

const Bar: React.FC<{frac: number; color: string}> = ({frac, color}) => (
  <div style={{height: 6, background: theme.rule, borderRadius: 3, overflow: 'hidden', marginTop: 5}}>
    <div style={{width: `${Math.max(0, Math.min(1, frac)) * 100}%`, height: '100%', background: color}} />
  </div>
);

const Pill: React.FC<{text: string; bg: string; fg?: string}> = ({text, bg, fg = '#fff'}) => (
  <span style={{display: 'inline-block', fontSize: 12, fontWeight: 700, letterSpacing: 1.2, padding: '4px 10px', borderRadius: 999, background: bg, color: fg, fontFamily: theme.sans, marginLeft: 8}}>{text}</span>
);

export const InfoPanel: React.FC<{t: number; beat: Beat}> = ({t, beat}) => {
  const hot = beat.temp === 'hot' || (beat.hot_at !== undefined && t - beat.start >= beat.hot_at);
  const idx = shotlist.beats.indexOf(beat);
  const live = beat.lines.filter((l) => t >= l.t && t < l.tEnd + 0.4);
  const plays = shotlist.audio.filter((a) => a.kind === 'guest' && t >= a.at && t < a.at + a.duration);
  const placeholders = beat.plays.filter((p) => p.placeholder && t >= p.t && t < p.t + p.length);
  const bedOn = t >= shotlist.hallBed.on && t < shotlist.hallBed.off;
  const cam = poseAt(shotlist.keyframes.camera, t);
  const clicks = (beat.events ?? []).filter((e) => e.kind === 'click' && t >= e.t && t < e.t + 1.5);
  const xrayStep = beat.xray ? Math.min(7, Math.floor(t - beat.start)) : -1;

  return (
    <div style={{position: 'absolute', left: X, top: Y, width: W, height: H, background: theme.panel, border: `1px solid ${theme.rule}`, borderRadius: 12, fontFamily: theme.sans, color: theme.ink}}>
      {/* header */}
      <div style={{position: 'absolute', left: 22, top: 16, fontFamily: theme.mono, fontSize: 54, fontWeight: 700, letterSpacing: -1, lineHeight: 1}}>{fmtTime(t)}<span style={{fontSize: 20, color: theme.inkFaint, marginLeft: 8, fontWeight: 400}}>/ 3:00</span></div>
      <div style={{position: 'absolute', right: 22, top: 18, textAlign: 'right'}}>
        <div style={{fontFamily: theme.mono, fontSize: 15, color: theme.inkSoft}}>BEAT {beat.id} / {shotlist.beats.length}</div>
        <div style={{marginTop: 8}}>
          <Pill text={partLabel(beat.part).toUpperCase()} bg={theme.paperDeep} fg={theme.inkSoft} />
          <Pill text={hot ? 'HOT' : beat.silence ? 'COLD · SILENCE' : 'COLD'} bg={hot ? theme.hot : theme.cold} />
        </div>
      </div>
      <div style={{position: 'absolute', left: 22, top: 84, width: W - 44, fontSize: 31, fontWeight: 700, lineHeight: 1.1, letterSpacing: -0.3}}>{beat.name}</div>
      <div style={{position: 'absolute', left: 22, top: 126, width: W - 44, fontSize: 15, fontStyle: 'italic', color: theme.inkSoft, lineHeight: 1.3, height: 40, overflow: 'hidden'}}>{beat.proves}</div>

      {beat.xray ? (
        <Section title="X-RAY · THE FRENCH GOES THROUGH THE MACHINERY · 1 S A STEP" top={176} height={270}>
          {(beat.xraySteps ?? []).map((s, i) => (
            <div key={i} style={{display: 'flex', alignItems: 'center', gap: 10, fontSize: 17, lineHeight: 1.65, color: i <= xrayStep ? theme.ink : theme.inkFaint, fontWeight: i === xrayStep ? 700 : 400}}>
              <span style={{display: 'inline-block', width: 22, height: 22, borderRadius: 11, background: i <= xrayStep ? theme.cold : theme.rule, color: '#fff', fontSize: 12, textAlign: 'center', lineHeight: '22px', fontFamily: theme.mono}}>{i + 1}</span>
              {s}
            </div>
          ))}
        </Section>
      ) : (
        <>
          <Section title="SPEAKING" top={176} height={118}>
            {live.length === 0 && clicks.length === 0 && <div style={{fontSize: 15, color: theme.inkFaint}}>—</div>}
            {live.map((l, i) => {
              const color = SPEAKER_COLOR[l.who] ?? theme.inkSoft;
              const play = plays.find((p) => p.device === l.device);
              return (
                <div key={i} style={{marginBottom: 6}}>
                  <span style={{display: 'inline-block', background: color, color: '#fff', fontWeight: 700, fontSize: 13, padding: '2px 8px', borderRadius: 4, letterSpacing: 1}}>{l.who.toUpperCase()}</span>
                  <span style={{fontFamily: theme.mono, fontSize: 13, color: theme.inkSoft, marginLeft: 10}}>
                    {l.device === 'live' ? `LIVE${l.audio ? ' · stand-in voice' : ''}` : `${l.device}${play ? ' · ' + play.src : ''}`}
                    {l.lang !== 'en' && <span style={{marginLeft: 8, color: theme.cold}}>{l.lang === 'fr' ? 'French' : 'Japanese'} · translated</span>}
                    {l.choice && <span style={{marginLeft: 8, color: theme.eric}}>[CHOICE] not yet rendered</span>}
                  </span>
                  <Bar frac={(t - l.t) / (l.tEnd - l.t)} color={color} />
                </div>
              );
            })}
            {clicks.map((c, i) => <div key={'c' + i} style={{fontFamily: theme.mono, fontSize: 13, color: theme.hot, marginTop: 4}}>▸ presenter {c.label}</div>)}
          </Section>

          <Section title="PLAYS" top={304} height={142}>
            {plays.length === 0 && placeholders.length === 0 && !bedOn && <div style={{fontSize: 15, color: theme.inkFaint}}>nothing · {beat.silence ? 'silence (post)' : 'room tone'}</div>}
            {plays.map((p, i) => {
              const dev = shotlist.plan.devices.find((d) => d.id === p.device);
              return (
                <div key={i} style={{marginBottom: 6}}>
                  <span style={{fontWeight: 700, fontSize: 14, color: theme.sound}}>{dev?.label ?? p.device}</span>
                  <span style={{fontFamily: theme.mono, fontSize: 13, color: theme.inkSoft, marginLeft: 10}}>{p.src} · {Math.max(0, p.at + p.duration - t).toFixed(1)} s left</span>
                  <Bar frac={(t - p.at) / p.duration} color={theme.sound} />
                </div>
              );
            })}
            {placeholders.map((p, i) => (
              <div key={'ph' + i} style={{marginBottom: 6}}>
                <span style={{fontWeight: 700, fontSize: 14, color: theme.eric}}>{p.device}</span>
                <span style={{fontFamily: theme.mono, fontSize: 13, color: theme.eric, marginLeft: 10}}>{p.file}</span>
                <Bar frac={(t - p.t) / p.length} color={theme.eric} />
              </div>
            ))}
            {bedOn && (
              <div style={{fontSize: 13, color: beat.silence ? theme.cold : theme.inkSoft, fontFamily: theme.mono, marginTop: 2}}>
                TV · tv-hall-bed.wav · loop{beat.silence ? ' · muted in post' : ''}
              </div>
            )}
          </Section>
        </>
      )}

      <Section title="CAMERA" top={458} height={128}>
        <div style={{fontSize: 16, fontWeight: 700, color: theme.camera, lineHeight: 1.25}}>{cam.spot ? shotlist.plan.cameraSpots.find((c) => c.id === cam.spot)?.label ?? beat.camera.spot : beat.camera.spot}{cam.moving ? ' · walking' : ''}</div>
        <div style={{fontSize: 14.5, lineHeight: 1.3, marginTop: 4, height: 56, overflow: 'hidden'}}>{beat.camera.framing}</div>
        <div style={{fontSize: 14, color: theme.inkSoft, marginTop: 3}}>Looks at: <b style={{color: theme.ink}}>{beat.camera.lookAt}</b></div>
      </Section>

      <Section title="POST" top={596} height={176}>
        {beat.post.map((p, i) => (
          <div key={i} style={{display: 'flex', gap: 8, fontSize: 13.5, lineHeight: 1.3, marginBottom: 4, color: theme.ink}}>
            <span style={{color: theme.hot, fontWeight: 700}}>+</span>
            <span style={{display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden'}}>{p}</span>
          </div>
        ))}
      </Section>

      <Section title="MARKS" top={782} height={70}>
        <div style={{fontSize: 13.5, lineHeight: 1.45}}>
          <div><b style={{color: theme.eric}}>ERIC</b> · mark {beat.eric.mark} · faces {beat.eric.face} · {beat.eric.pose}</div>
          <div><b style={{color: theme.friend}}>FRIEND</b> · {beat.friend.spot} · faces {beat.friend.face}</div>
        </div>
      </Section>
    </div>
  );
};
