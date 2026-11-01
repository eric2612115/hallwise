import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {castFor} from '../lib/cast';
import {seg} from '../lib/motion';
import {Card, Chip, Corner, Eyebrow, Frame, Receipt, Struck} from '../ui';
import {theme} from '../theme';
import type {ProofData} from '../lib/types';

// The connector reveal (spec 5.6): the week as a line of evenings, then three cards in hud's reveal order:
// Kenji (met before · matched: full name · recall.py · no model) → what the log owes him (the two hooks with their
// quotes · hooks.py) → the proposal (Muse Spark · next move · coffee · Thursday struck, Friday), and the bottom
// banner naming where they could meet, stamped CORPUS · NOT YET WIRED INTO A DRAFT. No model chip on that card.
// Every date, name and count comes from the data: the meetup's date from its page, Lena from the evening she was
// met, the number of earlier evenings from the run's own log.
export type ConnectorProps = {data: ProofData};

const W = 1728;

export const Connector: React.FC<ConnectorProps> = ({data}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const run = data.run1,
    ev = data.evidence;
  const C51 = castFor(run);
  const ph = run.person_history.find((p) => p.key.startsWith('kenji') && p.provisional)!;
  const owe = run.hooks.find((h) => h.title.startsWith('you owe Lena'))!;
  const ment = run.hooks.find((h) => h.title.startsWith('Lena mentioned'))!;
  const move = run.next_moves.find((m) => m.person_key.startsWith('kenji'))!;
  const coffee = run.promises_final['coffee-to-kenji-watanabe-hoshizora-robotics'];
  const turn = run.turns.find((t) => t.turn === 23)!;
  const meetup = data.meetup;
  const kenjiLabel = Object.entries(run.cast).find(([, c]) => c.key === ph.key)?.[0] ?? '';
  const kenjiColor = kenjiLabel ? C51.color(kenjiLabel, 'paper') : theme.accent;
  const lena = ev.lena;

  const evenings = [
    {d: ev.lena_promise.date, e: ev.lena_promise.event, x: 0.07},
    {d: ev.hardware_meetup.date, e: ev.hardware_meetup.event, x: 0.23},
    {d: ev.chloe.date, e: ev.chloe.event, x: 0.39},
    {d: ev.lena_asks.date, e: ev.lena_asks.event, x: 0.55},
    {d: run.now_date, e: 'tonight · ' + run.event, x: 0.72, now: true},
    ...(meetup ? [{d: meetup.short, e: meetup.name, x: 0.92, ahead: true}] : []),
  ];
  const enc = ph.encounters.map((x) => ({e: x.event, d: [ev.lena_promise, ev.hardware_meetup, ev.chloe, ev.lena_asks].find((m) => m.id === x.recording)?.date || ''}));

  // reveal order: the week → Kenji (met before) → the owed introduction → the proposal → where they could meet
  const headP = seg(frame, 0, Math.round(fps * 0.5));
  const week = seg(frame, Math.round(fps * 0.1), Math.round(fps * 0.6));
  const pK = seg(frame, Math.round(fps * 0.55), Math.round(fps * 0.45));
  const pLines = seg(frame, Math.round(fps * 0.9), Math.round(fps * 0.5));
  const pOwe = seg(frame, Math.round(fps * 1.35), Math.round(fps * 0.45));
  const pProp = seg(frame, Math.round(fps * 1.8), Math.round(fps * 0.45));
  const sThu = seg(frame, Math.round(fps * 2.3), Math.round(fps * 0.3));
  const pMeet = seg(frame, Math.round(fps * 2.4), Math.round(fps * 0.45));

  const draft = move.body;
  const marks = ['the introduction to Lena I still owe you', 'coffee on Friday instead of Thursday'];
  const draftNodes: React.ReactNode[] = [];
  let rest = draft;
  let key = 0;
  while (rest.length) {
    const hit = marks.map((m) => ({m, i: rest.indexOf(m)})).filter((h) => h.i >= 0).sort((a, b) => a.i - b.i)[0];
    if (!hit) {
      draftNodes.push(<React.Fragment key={key++}>{rest}</React.Fragment>);
      break;
    }
    draftNodes.push(<React.Fragment key={key++}>{rest.slice(0, hit.i)}</React.Fragment>);
    draftNodes.push(
      <span key={key++} style={{color: theme.accent, textDecoration: 'underline', textDecorationThickness: 3, textUnderlineOffset: 5}}>
        {hit.m}
      </span>,
    );
    rest = rest.slice(hit.i + hit.m.length);
  }

  const hookBox = (h: typeof owe, src: string, p: number) => (
    <div style={{marginTop: 10, padding: '10px 16px', borderRadius: 14, background: theme.paper, border: `1.5px solid ${theme.rule}`, opacity: p, transform: `translateY(${(1 - p) * 12}px)`}}>
      <div style={{fontFamily: theme.sans, fontWeight: 700, fontSize: 24, color: theme.accent}}>{h.title}</div>
      <p style={{fontFamily: theme.serif, fontStyle: 'italic', fontSize: 23, lineHeight: 1.22, margin: '3px 0 3px'}}>“{h.evidence[0].quote}”</p>
      <div style={{fontFamily: theme.mono, fontSize: 16, color: theme.inkSoft}}>{src}</div>
    </div>
  );

  const ringX = 96 + 28 + 46,
    ringY = 386 + 22 + 50;
  const heroLine = turn.text.split('.')[0].trim().replace(/^it/, 'It');
  return (
    <Frame>
      <div style={{position: 'absolute', left: 96, top: 56, right: 96, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 30, opacity: headP}}>
        <div>
          <Eyebrow>The connector · a name said at the table, and the week behind it</Eyebrow>
          <h1 style={{fontFamily: theme.serif, fontWeight: 500, fontSize: 64, lineHeight: 1.04, letterSpacing: '-0.012em', margin: '8px 0 0', color: theme.inkStrong, whiteSpace: 'nowrap', display: 'flex', alignItems: 'baseline', gap: 22}}>
            <span>“{heroLine}.”</span>
            <span style={{fontFamily: theme.mono, fontSize: 19, color: theme.inkSoft, letterSpacing: '0.04em'}}>
              run {run.id.slice(-4)} · turn {turn.turn} · {C51.at(turn.speaker, turn.end_ms).name}
            </span>
          </h1>
        </div>
        <div style={{display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'flex-end', maxWidth: 700}}>
          <Chip kind="code">code · recall.py</Chip>
          <Chip kind="code">code · hooks.py</Chip>
          <Chip>Muse Spark · the draft</Chip>
        </div>
      </div>

      {/* the week */}
      <div style={{position: 'absolute', left: 96, right: 96, top: 222, height: 150, opacity: week}}>
        <svg viewBox={`0 0 ${W} 150`} width={W} height={150} style={{position: 'absolute', inset: 0, overflow: 'visible'}}>
          <line x1={0} y1={40} x2={W * 0.78 * week} y2={40} stroke={theme.ink} strokeWidth={2.5} strokeLinecap="round" />
          <line x1={W * 0.78} y1={40} x2={W} y2={40} stroke={theme.inkSoft} strokeWidth={2} strokeDasharray="8 10" opacity={week} />
          {evenings.map((e, i) => (
            <circle key={i} cx={W * e.x} cy={40} r={e.now ? 13 : 9} fill={e.ahead ? theme.paper : e.now ? theme.ink : theme.inkSoft} stroke={e.ahead ? theme.accent : 'none'} strokeWidth={3} opacity={week * 1.4 - i * 0.08 > 0 ? 1 : 0} />
          ))}
          <polygon points={`${W - 2},33 ${W + 16},40 ${W - 2},47`} fill={theme.inkSoft} />
        </svg>
        {evenings.map((e, i) => (
          <div key={i} style={{position: 'absolute', left: W * e.x, top: 58, transform: 'translateX(-50%)', textAlign: 'center', width: 250}}>
            <div style={{fontFamily: theme.mono, fontSize: 20, letterSpacing: '0.08em', color: e.ahead ? theme.accent : theme.inkSoft}}>{e.d}</div>
            <div style={{fontFamily: theme.serif, fontSize: 25, fontWeight: e.now ? 600 : 500, lineHeight: 1.1, marginTop: 4, color: e.ahead ? theme.accent : theme.inkStrong}}>{e.e}</div>
          </div>
        ))}
      </div>

      {/* dashed ink from Kenji's ring to the two evenings, and from the hooks card to the dinner */}
      <svg viewBox="0 0 1920 1080" style={{position: 'absolute', inset: 0, width: 1920, height: 1080, pointerEvents: 'none'}}>
        {[0, 1].map((i) => {
          const ex = 96 + W * evenings[i].x,
            ey = 262;
          return <path key={i} d={`M${ringX} ${ringY - 46} C ${ringX} ${ringY - 110}, ${ex} ${ey + 120}, ${ex} ${ey + 14}`} fill="none" stroke={theme.inkSoft} strokeWidth={2.5} strokeDasharray="7 9" pathLength={100} strokeDashoffset={100 - 100 * pLines} opacity={0.8} />;
        })}
        {(() => {
          const hx = 96 + 540 + 30 + (1728 - 540 - 60) / 4,
            hy = 386;
          const ex3 = 96 + W * evenings[3].x;
          return <path d={`M${hx} ${hy} C ${hx} ${hy - 50}, ${ex3} ${262 + 100}, ${ex3} ${262 + 14}`} fill="none" stroke={theme.inkSoft} strokeWidth={2.5} strokeDasharray="7 9" pathLength={100} strokeDashoffset={100 - 100 * pOwe} opacity={0.8} />;
        })()}
      </svg>

      <div style={{position: 'absolute', left: 96, right: 96, top: 386, display: 'grid', gridTemplateColumns: '540px minmax(0,1fr) minmax(0,1fr)', gap: 30, alignItems: 'start'}}>
        <Card style={{padding: '22px 28px 20px', opacity: pK, transform: `translateY(${(1 - pK) * 26}px)`}}>
          <div style={{display: 'flex', gap: 22, alignItems: 'flex-start'}}>
            <div style={{display: 'grid', placeItems: 'center', width: 92, height: 92, borderRadius: '50%', border: `4px solid ${kenjiColor}`, boxShadow: `0 0 0 6px ${theme.paperRaised}, 0 0 0 9px ${kenjiColor}`, fontFamily: theme.serif, fontWeight: 600, fontSize: 40, color: kenjiColor, flex: 'none', marginTop: 4}}>{ph.name.slice(0, 1)}</div>
            <div>
              <p style={{fontFamily: theme.serif, fontSize: 40, fontWeight: 600, lineHeight: 1.05, margin: 0, color: theme.inkStrong}}>{ph.name}</p>
              <p style={{fontSize: 26, color: theme.inkSoft, margin: '4px 0 0'}}>{ph.company}</p>
            </div>
          </div>
          <div style={{marginTop: 18, paddingTop: 16, borderTop: `1.5px dashed ${theme.rule}`}}>
            <span style={{fontFamily: theme.mono, fontSize: 20, letterSpacing: '0.08em', textTransform: 'uppercase', color: kenjiColor}}>met before · matched: {ph.matched}</span>
            <ul style={{listStyle: 'none', margin: '8px 0 0', padding: 0, fontSize: 26, lineHeight: 1.35}}>
              {enc.map((x) => (
                <li key={x.e}>
                  {x.e}
                  <span style={{fontFamily: theme.mono, fontSize: 20, color: theme.inkSoft, marginLeft: 10}}>{x.d}</span>
                </li>
              ))}
            </ul>
          </div>
          <div style={{display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginTop: 14}}>
            <Chip kind="code">code · recall.py</Chip>
            <Chip kind="nomodel">no model call</Chip>
          </div>
          <Receipt size={19} wrap style={{display: 'block', marginTop: 10}} parts={['person_history', `${(ph.t_ms / 1000).toFixed(1)} s`, `turn ${ph.turn}`, 'provisional → confirmed']} />
        </Card>

        <Card style={{padding: '22px 28px 20px', opacity: pOwe, transform: `translateY(${(1 - pOwe) * 26}px)`}}>
          <p style={{fontFamily: theme.serif, fontWeight: 500, fontSize: 30, margin: '0 0 10px', color: theme.inkStrong}}>What the log owes him</p>
          {hookBox(owe, `${owe.evidence[0].event} · turn ${owe.evidence[0].turn}${lena ? ` · to ${lena.name}, ${lena.company}` : ''}`, seg(frame, Math.round(fps * 1.45), Math.round(fps * 0.4)))}
          {hookBox(ment, `${ment.evidence[0].event} · turn ${ment.evidence[0].turn}`, seg(frame, Math.round(fps * 1.65), Math.round(fps * 0.4)))}
          <div style={{display: 'flex', alignItems: 'center', gap: 14, marginTop: 14, flexWrap: 'wrap'}}>
            <Chip kind="code">code · hooks.py</Chip>
            <Receipt size={19} wrap parts={['hook', `${(owe.t_ms / 1000).toFixed(1)} s`, `evidence from ${new Set([owe, ment].map((h) => h.evidence[0].recording)).size} earlier logs`]} />
          </div>
        </Card>

        <Card style={{padding: '22px 28px 20px', opacity: pProp, transform: `translateY(${(1 - pProp) * 26}px)`}}>
          <p style={{fontFamily: theme.serif, fontWeight: 500, fontSize: 30, margin: '0 0 10px', color: theme.inkStrong}}>The proposal</p>
          <p style={{fontFamily: theme.serif, fontSize: 24.5, lineHeight: 1.28, margin: 0, whiteSpace: 'pre-line'}}>{draftNodes}</p>
          <p style={{marginTop: 10, fontSize: 25}}>
            coffee · <Struck p={sThu}>{coffee.replaces}</Struck> <b>{coffee.due}</b>{' '}
            <span style={{fontFamily: theme.mono, fontSize: 20, color: theme.inkSoft}}>{move.when.slice(0, 16).replace('T', ' ')}</span>
          </p>
          <div style={{display: 'flex', alignItems: 'center', gap: 14, marginTop: 10, flexWrap: 'wrap'}}>
            <Chip>Muse Spark · next move</Chip>
            <Receipt size={19} parts={['next_move', move.kind, `${(move.t_ms / 1000).toFixed(1)} s`]} />
          </div>
        </Card>
      </div>

      {meetup ? (
        <div style={{position: 'absolute', left: 96, right: 96, bottom: 78, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 30, padding: '12px 30px', borderRadius: 20, border: `1.5px solid ${theme.accent}`, background: theme.paperRaised, opacity: pMeet, transform: `translateY(${(1 - pMeet) * 26}px)`}}>
          <div>
            <p style={{fontFamily: theme.serif, fontSize: 30, fontWeight: 600, lineHeight: 1.1, margin: 0}}>Where they could meet: {meetup.name}</p>
            <p style={{fontSize: 22, margin: '4px 0 0'}}>
              <b style={{color: theme.accent}}>{meetup.date}</b> · from the corpus the research runs against
            </p>
          </div>
          <div style={{textAlign: 'right', flex: 'none'}}>
            <Chip kind="pending" size={22}>
              corpus · not yet wired into a draft
            </Chip>
            <Receipt size={19} wrap style={{display: 'block', marginTop: 8, maxWidth: 560}} parts={[String(data.generated_from.web ?? ''), meetup.url.replace('https://', '')]} />
          </div>
        </div>
      ) : null}
      <Corner name="connector" parts={[`run ${run.id.slice(-4)}`, `people index: ${run.index_evenings.length} earlier evenings`, String(data.generated_from.web ?? '')]} left={96} />
    </Frame>
  );
};
