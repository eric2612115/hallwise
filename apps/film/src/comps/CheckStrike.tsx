import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {castFor} from '../lib/cast';
import {fmt, seg} from '../lib/motion';
import {Card, Chip, Corner, Eyebrow, Frame, Kept, Receipt, Struck} from '../ui';
import {theme} from '../theme';
import type {ProofData} from '../lib/types';

// Check strike-outs (spec 5.7). Left: the edge finder's two answers on the aside take, as the server's own check
// (Extractor.take_edges -> extract.kept_edges) judged them during the finder check: the edge whose `said` joined
// two turns, dropped; the edge resting on her words in one turn of her own voice, kept. Right: the Julien card with
// the two readings side by side and the confirmation withdrawn, from the retired two-model comparison run 51b4
// logged. Bottom: the promise as Muse Spark corrected it (a field the model fills; no code check). Receipts carry
// the verbatim event rows; the verdicts on the left are logged by the finder check, not re-run here, and the stamp
// says so. edge_removed is a diff withdrawal and is never drawn as a rejection.
export type CheckStrikeProps = {data: ProofData};

export const CheckStrike: React.FC<CheckStrikeProps> = ({data}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const aside = data.aside;
  const CA = castFor(aside);
  const C51 = castFor(data.run1);
  const dropCall = aside.finder.c.calls[0];
  const dropped = dropCall.dropped[0];
  const keptCall = aside.finder.c_final.calls[0];
  const kept = keptCall.kept.find((e) => e.said === aside.aside_turn) ?? keptCall.kept[0];
  const keptLabel = aside.people.find((p) => p.key === kept.person)?.speakers[0] ?? '';
  const keptName = aside.people.find((p) => p.key === kept.person)?.name ?? kept.person;
  const run = data.run1;
  const dis = run.disagreement!;
  const conf = run.confirmed.find((c) => c.key === dis.key)!;
  const rm = run.confirmed_removed[0];
  const sr5 = run.second_runs.find((s) => s.disagreed > 0) ?? run.second_runs[run.second_runs.length - 1];
  const coffee = data.rec3f3e.promises['coffee-to-kenji-watanabe-hoshizora-robotics'];
  const disLabel = Object.entries(run.cast).find(([, c]) => c.key === dis.key)?.[0] ?? '';
  const name = disLabel ? C51.at(disLabel, dis.t_ms).name : (run.people_final[dis.key]?.name ?? dis.key);
  const kenji = data.rec3f3e.people[coffee.owed_to]?.name ?? coffee.owed_to;

  const headP = seg(frame, 0, Math.round(fps * 0.5));
  const c1 = seg(frame, Math.round(fps * 0.2), Math.round(fps * 0.45));
  const s1 = seg(frame, Math.round(fps * 0.85), Math.round(fps * 0.35)); // the strike draws 0.2 s after the claim lands
  const x1 = seg(frame, Math.round(fps * 1.2), Math.round(fps * 0.25));
  const u1 = seg(frame, Math.round(fps * 1.35), Math.round(fps * 0.3));
  const k1 = seg(frame, Math.round(fps * 1.65), Math.round(fps * 0.25));
  const c2 = seg(frame, Math.round(fps * 1.1), Math.round(fps * 0.45));
  const s2 = seg(frame, Math.round(fps * 2.0), Math.round(fps * 0.35));
  const x2 = seg(frame, Math.round(fps * 2.4), Math.round(fps * 0.25));
  const c3 = seg(frame, Math.round(fps * 2.2), Math.round(fps * 0.45));
  const s3 = seg(frame, Math.round(fps * 2.9), Math.round(fps * 0.3));

  const claim: React.CSSProperties = {fontFamily: theme.serif, fontWeight: 500, fontSize: 40, lineHeight: 1.12, margin: 0, color: theme.inkStrong};
  const meta: React.CSSProperties = {fontSize: 22, lineHeight: 1.3, color: theme.ink, margin: '8px 0 0'};
  const k: React.CSSProperties = {fontFamily: theme.mono, fontSize: 20, color: theme.inkSoft, marginRight: 8};
  const kind: React.CSSProperties = {fontFamily: theme.mono, fontSize: 20, letterSpacing: '0.1em', textTransform: 'uppercase', color: theme.inkSoft};
  const usage = (c: typeof dropCall) => `${c.seconds} s · ${fmt(c.usage.prompt_tokens)} in / ${fmt(c.usage.completion_tokens)} out`;

  return (
    <Frame>
      <div style={{position: 'absolute', left: 96, top: 56, right: 96, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', opacity: headP}}>
        <div style={{flex: 1}}>
          <Eyebrow size={22}>The check · every model output, held to the transcript</Eyebrow>
          <h1 style={{fontFamily: theme.serif, fontWeight: 500, fontSize: 60, lineHeight: 1.04, letterSpacing: '-0.012em', margin: '8px 0 0', color: theme.inkStrong, whiteSpace: 'nowrap'}}>Kept only if the words are there.</h1>
        </div>
        <div style={{display: 'flex', gap: 12, flexWrap: 'wrap', justifyContent: 'flex-end', maxWidth: 760}}>
          <Chip kind="code" size={22}>code · extract.py · kept_edges</Chip>
          <Chip kind="pending" size={19}>
            verdicts logged by the finder check · no check event in events.jsonl yet
          </Chip>
        </div>
      </div>

      <div style={{position: 'absolute', left: 96, right: 96, top: 212, display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1fr)', gap: 40}}>
        <Card style={{padding: '22px 32px 18px', minHeight: 560, display: 'flex', flexDirection: 'column', opacity: c1, transform: `translateY(${(1 - c1) * 26}px)`}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 14, marginBottom: 14, flexWrap: 'wrap'}}>
            <Chip>Muse Spark Open on Baseten</Chip>
            <span style={kind}>edges · the aside take</span>
          </div>
          <p style={{...claim, fontSize: 31}}>
            <Struck p={s1} thick={0.12} multiline>
              <span style={{fontStyle: 'italic'}}>“{dropped.said}”</span>
            </Struck>
          </p>
          <p style={meta}>
            <span style={k}>said</span>joins two turns {dropped.turns.join(' and ')}; the check wants the words inside one turn in her own voice
          </p>
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16, marginTop: 10}}>
            <span style={{opacity: x1, transform: `scale(${0.9 + 0.1 * x1})`, display: 'inline-block'}}>
              <Chip kind="struck" size={24}>
                dropped by the check
              </Chip>
            </span>
            <Receipt size={17} lines={2} align="right" style={{flex: 1}} parts={[`${aside.finder.c.file} · call ${dropCall.call}`, `raw ${dropCall.raw} → kept ${dropCall.kept.length} · ${usage(dropCall)}`]} />
          </div>
          <div style={{marginTop: 16, paddingTop: 14, borderTop: `1.5px dashed ${theme.rule}`}}>
            <p style={{...claim, fontSize: 36}}>
              <span style={{fontStyle: 'italic'}}>“{kept.said}”</span>
            </p>
            <p style={{...meta, margin: '6px 0 0'}}>
              <span style={k}>act</span>
              {kept.act}
            </p>
            <p style={{fontSize: 22, lineHeight: 1.3, margin: '10px 0 0'}}>Her words, in a turn in her own voice:</p>
            <div style={{marginTop: 8, padding: '10px 20px', borderRadius: 16, background: theme.paper, border: `1.5px solid ${theme.rule}`, fontFamily: theme.serif, fontSize: 30, lineHeight: 1.3}}>
              <span style={{fontFamily: theme.sans, fontWeight: 700, fontSize: 22, marginRight: 12, color: CA.color(keptLabel, 'paper')}}>
                {keptLabel} · {keptName}
              </span>
              <Kept p={u1}>{aside.aside_turn}</Kept>
              <span style={{...k, marginLeft: 12, fontSize: 18}}>turn {kept.turns[kept.turns.length - 1]}</span>
            </div>
          </div>
          <div style={{marginTop: 'auto', paddingTop: 14, display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16}}>
            <span style={{opacity: k1, transform: `scale(${0.9 + 0.1 * k1})`, display: 'inline-block'}}>
              <Chip kind="kept" size={26}>
                kept
              </Chip>
            </span>
            <Receipt size={17} lines={2} align="right" style={{flex: 1}} parts={[`${aside.finder.c_final.file} · call ${keptCall.call}`, `raw ${keptCall.raw} → kept ${keptCall.kept.length} · ${usage(keptCall)}`]} />
          </div>
        </Card>

        <Card style={{padding: '22px 32px 18px', minHeight: 560, display: 'flex', flexDirection: 'column', opacity: c2, transform: `translateY(${(1 - c2) * 26}px)`}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16, flexWrap: 'wrap'}}>
            <Chip>Muse Spark</Chip>
            <Chip>Muse Spark Open</Chip>
            <span style={kind}>confirmed · person</span>
          </div>
          <p style={claim}>
            <Struck p={s2} thick={0.14}>
              {name} · {dis.a.text}
            </Struck>
          </p>
          <p style={meta}>
            <span style={k}>confirmed by both at</span>
            {(conf.t_ms / 1000).toFixed(1)} s<span style={{...k, marginLeft: 18}}>then at</span>
            {(dis.t_ms / 1000).toFixed(1)} s, on <span style={{fontFamily: theme.mono}}>{dis.field}</span>:
          </p>
          <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 18, marginTop: 14}}>
            {[dis.a, dis.b].map((m) => (
              <div key={m.by} style={{padding: '12px 20px', borderRadius: 16, background: theme.paper, border: `1.5px solid ${theme.rule}`}}>
                <div style={{fontFamily: theme.mono, fontSize: 19, color: theme.inkSoft, letterSpacing: '0.06em', marginBottom: 2}}>{m.by}</div>
                <div style={{fontFamily: theme.serif, fontSize: 34, fontWeight: 500}}>
                  {m.text.split(' ').map((wd, i) => (
                    <span key={i} style={{color: i > 0 && !dis.b.text.includes(wd) ? theme.live : theme.inkStrong}}>
                      {i > 0 ? ' ' : ''}
                      {wd}
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
          <div style={{marginTop: 14, paddingTop: 14, borderTop: `1.5px dashed ${theme.rule}`}}>
            <div style={{display: 'flex', gap: 10, flexWrap: 'wrap'}}>
              <Chip kind="code" size={20}>code · disagreement · field: {dis.field}</Chip>
              <Chip kind="nomodel" size={18}>
                retired comparison · edge_finder.py · logged {run.date}
              </Chip>
            </div>
            <p style={{fontSize: 22, lineHeight: 1.3, margin: '10px 0 0'}}>Two readings of one introduction. The mark comes off, and nothing restores it: the two-model comparison has since been retired (edge_finder.py); the events stay in the log.</p>
          </div>
          <div style={{marginTop: 'auto', paddingTop: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', gap: 16}}>
            <span style={{opacity: x2, transform: `scale(${0.9 + 0.1 * x2})`, display: 'inline-block'}}>
              <Chip kind="struck" size={26}>
                confirmation withdrawn
              </Chip>
            </span>
            <Receipt size={16} wrap align="right" style={{maxWidth: 440, lineHeight: 1.35}} parts={[`run ${run.id.slice(-4)}`, `confirmed ${(conf.t_ms / 1000).toFixed(2)} s`, `second_run call ${sr5.call}`, `${sr5.seconds} s`, `${fmt(sr5.usage.total_tokens)} tokens`, `agreed ${sr5.agreed}`, `disagreed ${sr5.disagreed}`, `${rm.type} ${(rm.t_ms / 1000).toFixed(3)} s`]} />
          </div>
        </Card>
      </div>

      <div style={{position: 'absolute', left: 96, right: 96, bottom: 82, display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 30, padding: '12px 32px', borderRadius: 20, border: `1.5px solid ${theme.rule}`, background: theme.paperRaised, opacity: c3, transform: `translateY(${(1 - c3) * 26}px)`}}>
        <div style={{flex: 'none'}}>
          <Eyebrow size={18} style={{marginBottom: 4}}>
            A promise, as the model corrected it
          </Eyebrow>
          <p style={{...claim, fontSize: 36, whiteSpace: 'nowrap'}}>
            coffee with {kenji} · <Struck p={s3}>{coffee.replaces}</Struck> <b>{coffee.due}</b>
          </p>
        </div>
        <div style={{textAlign: 'right', flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8}}>
          <Chip size={21}>Muse Spark · corrected its own promise · not a code check</Chip>
          <Receipt size={16} lines={2} align="right" style={{maxWidth: 640}} parts={[data.rec3f3e.id, `promise · turns ${coffee.evidence_turns.join(', ')}`, `replaces “${coffee.replaces}”: a field the model fills (extract.py schema)`]} />
        </div>
      </div>
      <Corner name="check" parts={['aside take · finder_check.py', `run ${run.id.slice(-4)}`, data.rec3f3e.id]} left={96} />
    </Frame>
  );
};
