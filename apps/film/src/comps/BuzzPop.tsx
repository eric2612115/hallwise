import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {castFor} from '../lib/cast';
import {fmt, lin, seg} from '../lib/motion';
import {Chip, Eyebrow, Frame, Receipt} from '../ui';
import {hexA, theme} from '../theme';
import type {ProofData} from '../lib/types';

// The phone worn face-out as a badge: its lock screen is the name card (paper/buzz.html), with hud/notify.html's
// LISTENING red state and two-ring pulse. The right side, on dark, says what fired it: a model chip and a code chip
// with a receipt.
//
// Two things can land on the phone, each drawn the way the app draws it:
// - 'deck': the one notification the app has (RebuiltNotice.swift): the .success haptic, the banner with the
//   headline and subline composed from the rebuilt event's own name (here the run's person, through
//   onepager.find_person, the way a cued page lands). The rings and the shake are this one's.
// - 'hook': the app has no hook notification. A hook shows as a tag under the person's name on the room page
//   (LivePages.swift HookTagLine) and as a hook row with its title, reason and evidence (HookRow). So the phone
//   shows that row; nothing buzzes.
export type Pop = 'deck' | 'hook';
export type BuzzPopProps = {
  data: ProofData;
  pops: Pop[]; // in the order they land
  buzzAt?: number; // frame of the first pop
  gap?: number; // frames between pops
  hero?: string;
};

const Banner: React.FC<{p: number; p2: number; icon: string; when: string; head: React.ReactNode; body: React.ReactNode; foot?: React.ReactNode}> = ({p, p2, icon, when, head, body, foot}) => (
  <div
    style={{
      display: 'grid',
      gridTemplateColumns: '76px minmax(0, 1fr)',
      gap: 22,
      padding: '26px 30px 26px 26px',
      borderRadius: 34,
      background: 'rgba(244,240,231,0.97)',
      border: `1.5px solid ${theme.rule}`,
      boxShadow: '0 14px 40px rgba(42,38,34,0.22), 0 2px 6px rgba(42,38,34,0.10)',
      opacity: p,
      transform: `translateY(${(1 - p) * -40}px)`,
    }}
  >
    <div style={{width: 76, height: 76, borderRadius: 20, background: theme.ink, color: theme.paper, display: 'grid', placeItems: 'center', fontFamily: theme.serif, fontWeight: 600, fontSize: 44}}>{icon}</div>
    <div style={{minWidth: 0}}>
      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', fontFamily: theme.mono, fontSize: 21, letterSpacing: '0.1em', textTransform: 'uppercase', color: theme.inkSoft, marginBottom: 8}}>
        <span>Hallwise</span>
        <span>{when}</span>
      </div>
      <p style={{fontFamily: theme.serif, fontWeight: 600, fontSize: 38, lineHeight: 1.12, color: theme.inkStrong, margin: 0}}>{head}</p>
      <div style={{fontSize: 27, lineHeight: 1.3, color: theme.ink, margin: '8px 0 0', opacity: p2}}>{body}</div>
      {foot ? <div style={{marginTop: 10, opacity: p2}}>{foot}</div> : null}
    </div>
  </div>
);

// The room page's person row and hook row, as LivePages.swift lays them out (a dot, the name in serif, the hook tag
// in the accent under it; then the hook row: a glyph, the title in serif, the reason). Scaled for the frame.
const HookOnBadge: React.FC<{p: number; p2: number; name: string; company: string; color: string; tag: string; title: string; reason: string; evidence: string[]}> = ({p, p2, name, company, color, tag, title, reason, evidence}) => (
  <div style={{opacity: p, transform: `translateY(${(1 - p) * -24}px)`}}>
    <div style={{fontFamily: theme.mono, fontSize: 19, letterSpacing: '0.1em', textTransform: 'uppercase', color: theme.inkSoft, margin: '0 0 12px 8px'}}>the room · met tonight</div>
    <div style={{display: 'flex', alignItems: 'flex-start', gap: 18, padding: '18px 24px', borderRadius: 24, background: 'rgba(244,240,231,0.97)', border: `1.5px solid ${theme.rule}`}}>
      <span style={{width: 26, height: 26, borderRadius: '50%', background: color, flex: 'none', marginTop: 8}} />
      <div style={{minWidth: 0}}>
        <p style={{fontFamily: theme.serif, fontWeight: 600, fontSize: 38, lineHeight: 1.1, color: theme.inkStrong, margin: 0}}>{name}</p>
        <p style={{fontFamily: theme.sans, fontWeight: 600, fontSize: 27, color: theme.accent, margin: '6px 0 0', display: 'flex', alignItems: 'center', gap: 6}}>
          <span style={{fontSize: 22}}>✦</span>
          {tag}
        </p>
        <p style={{fontSize: 23, color: theme.inkSoft, margin: '4px 0 0'}}>{company}</p>
      </div>
    </div>
    <div style={{marginTop: 14, padding: '18px 24px', borderRadius: 24, background: 'rgba(244,240,231,0.97)', border: `1.5px solid ${theme.rule}`, opacity: p2}}>
      <p style={{fontFamily: theme.serif, fontWeight: 600, fontSize: 30, lineHeight: 1.12, color: theme.inkStrong, margin: 0, display: 'flex', gap: 10, alignItems: 'baseline'}}>
        <span style={{color: theme.accent, fontFamily: theme.sans, fontSize: 24}}>⇄</span>
        {title}
      </p>
      <p style={{fontSize: 24, lineHeight: 1.32, color: theme.ink, margin: '8px 0 0'}}>{reason}</p>
      {evidence.map((q) => (
        <p key={q} style={{fontFamily: theme.serif, fontStyle: 'italic', fontSize: 21, color: theme.inkSoft, margin: '6px 0 0'}}>
          “{q}”
        </p>
      ))}
    </div>
  </div>
);

export const Phone: React.FC<{children?: React.ReactNode; shake?: number; rings?: number; listening?: boolean; owner: string}> = ({children, shake = 0, rings = 0, listening = true, owner}) => {
  // a short decaying shake for the haptic; two concentric rings pulse once (hud notify-t1). The phone is cropped by
  // the bottom of the frame like a badge seen up close; the name and LISTENING sit inside it.
  const dx = shake > 0 && shake < 1 ? Math.sin(shake * 28) * 7 * (1 - shake) : 0;
  return (
    <>
      {[0, 1].map((k) => {
        const q = rings <= 0 || rings >= 1 ? 0 : Math.max(0, rings - k * 0.18) / (1 - k * 0.18);
        if (!q) return null;
        const r = 420 + q * 520;
        return (
          <div
            key={k}
            style={{
              position: 'absolute',
              left: 500 - r,
              top: 640 - r,
              width: r * 2,
              height: r * 2,
              borderRadius: '50%',
              border: `2px solid ${hexA(theme.darkLive, 0.55 * (1 - q))}`,
              boxShadow: `0 0 40px ${hexA(theme.darkLive, 0.18 * (1 - q))}`,
            }}
          />
        );
      })}
      <div
        style={{
          position: 'absolute',
          left: 150,
          top: 96,
          width: 700,
          height: 1400,
          borderRadius: 96,
          border: `4px solid ${theme.darkInk}`,
          boxShadow: '0 40px 120px rgba(0,0,0,0.6), inset 0 0 0 10px #1C1A17',
          background: theme.paper,
          overflow: 'hidden',
          transform: `translateX(${dx}px) rotate(${dx * 0.05}deg)`,
        }}
      >
        <div style={{position: 'absolute', inset: 14, borderRadius: 82, background: theme.paper, overflow: 'hidden'}}>
          <div style={{position: 'absolute', top: 32, left: '50%', transform: 'translateX(-50%)', width: 190, height: 54, borderRadius: 999, background: theme.dark}} />
          <div style={{position: 'absolute', left: 0, right: 0, top: 690, padding: '0 64px'}}>
            <p style={{fontFamily: theme.serif, fontWeight: 600, fontSize: 96, lineHeight: 0.95, letterSpacing: '-0.02em', color: theme.inkStrong, margin: 0}}>{owner}</p>
            <p style={{fontFamily: theme.serif, fontWeight: 400, fontSize: 44, color: theme.inkSoft, margin: '8px 0 0'}}>Hallwise</p>
            {listening ? (
              <div style={{marginTop: 26, display: 'inline-flex', alignItems: 'center', gap: 14, fontFamily: theme.mono, fontSize: 24, letterSpacing: '0.1em', textTransform: 'uppercase', color: theme.live}}>
                <span style={{width: 16, height: 16, borderRadius: '50%', background: theme.live, boxShadow: `0 0 0 6px ${hexA(theme.live, 0.18)}`}} />
                listening
              </div>
            ) : null}
          </div>
          <div style={{position: 'absolute', left: 30, right: 30, top: 118, display: 'flex', flexDirection: 'column', gap: 18}}>{children}</div>
        </div>
      </div>
    </>
  );
};

export const BuzzPop: React.FC<BuzzPopProps> = ({data, pops, buzzAt = 12, gap = 70, hero}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const op = data.onepager;
  const run = data.run1;
  const L = data.app_labels;
  const C51 = castFor(run);
  const hook = run.hooks.find((h) => h.title.startsWith('Chloé'))!;
  const ev = data.evidence.chloe;
  const hookLabel = Object.entries(run.cast).find(([, c]) => c.key === hook.person_key)?.[0] ?? '';
  const person = hookLabel ? C51.at(hookLabel, hook.t_ms) : {name: hook.person_key, key: hook.person_key};
  const personCompany = run.people_final[hook.person_key]?.company ?? '';
  const personColor = hookLabel ? C51.color(hookLabel, 'paper') : theme.accent;
  // the lines a HookRow shows under the reason: the evidence quotes the reason does not already carry
  const evidenceLines = hook.evidence.filter((e) => e.quote && !hook.reason.includes(e.quote)).map((e) => e.quote);
  const daysAgo = run.now ? Math.round((new Date(run.now).getTime() / 1000 - ev.started) / 86400) : null;
  const owner = data.rec3f3e.owner_name; // the badge's name card, from the recording's meta

  const pop = (i: number) => {
    const at = buzzAt + i * gap;
    return {
      shake: lin(frame, at, Math.round(fps * 0.5)),
      rings: lin(frame, at, Math.round(fps * 0.9)),
      p: seg(frame, at + Math.round(fps * 0.5), Math.round(fps * 0.5)),
      p2: seg(frame, at + Math.round(fps * 0.65), Math.round(fps * 0.45)),
      ex: seg(frame, at + Math.round(fps * 0.8), Math.round(fps * 0.6)),
    };
  };
  const states = pops.map((_, i) => pop(i));
  // only the rebuilt notice buzzes (the app's one notification); a hook never does
  const buzzing = states.filter((_, i) => pops[i] === 'deck');
  const shake = Math.max(0, ...buzzing.map((s) => (s.shake > 0 && s.shake < 1 ? s.shake : 0)));
  const rings = Math.max(0, ...buzzing.map((s) => (s.rings > 0 && s.rings < 1 ? s.rings : 0)));
  const heroP = seg(frame, 0, Math.round(fps * 0.6));
  const bottom: React.ReactNode[] = [`run ${run.id.slice(-4)}`];
  if (pops.includes('deck')) bottom.push(`ios/Sources/${L.rebuilt_source}`, L.rebuilt_name_source);
  if (pops.includes('hook')) bottom.push(`ios/Sources/${L.hook_tag_source}`, `ios/Sources/${L.hook_row_source}`);

  return (
    <Frame dark>
      <Phone shake={shake} rings={rings} owner={owner}>
        {pops.map((k, i) => {
          const s = states[i];
          return k === 'deck' ? (
            <Banner
              key={k}
              p={s.p}
              p2={s.p2}
              icon="H"
              when="now"
              head={L.rebuilt_headline}
              body={L.rebuilt_subline}
              foot={<Receipt size={20} wrap parts={[`${op.slides.length} slides → 1 page`, `${op.page.figures.length} figures`]} />}
            />
          ) : (
            <HookOnBadge key={k} p={s.p} p2={s.p2} name={person.name} company={personCompany} color={personColor} tag={hook.tag} title={hook.title} reason={hook.reason} evidence={evidenceLines} />
          );
        })}
      </Phone>

      <div style={{position: 'absolute', left: 1010, top: 120, width: 850, opacity: heroP, transform: `translateY(${(1 - heroP) * 20}px)`}}>
        <Eyebrow dark>On the badge · mid-evening</Eyebrow>
        <h1 style={{fontFamily: theme.serif, fontWeight: 500, fontSize: 88, lineHeight: 1.04, letterSpacing: '-0.012em', margin: '14px 0 0', color: theme.darkInk}}>
          {hero ?? 'The phone on his chest buzzes once.'}
        </h1>
        <div style={{marginTop: 44, display: 'flex', flexDirection: 'column', gap: 30}}>
          {pops.map((k, i) => {
            const s = states[i];
            return (
              <div key={k} style={{borderTop: `1.5px solid ${theme.darkRule}`, paddingTop: 24, opacity: s.ex, transform: `translateY(${(1 - s.ex) * 18}px)`}}>
                {k === 'deck' ? (
                  <>
                    <p style={{fontFamily: theme.serif, fontSize: 40, fontWeight: 500, color: theme.darkInk, margin: '0 0 14px'}}>His deck, rebuilt for her as one page, numbers first.</p>
                    <div style={{display: 'flex', gap: 12, marginBottom: 14, flexWrap: 'wrap'}}>
                      <Chip dark>Muse Spark</Chip>
                      <Chip kind="code" dark>
                        code · onepager.py
                      </Chip>
                      <Chip kind="pending" size={20}>
                        page cued into the run · name from its person event
                      </Chip>
                    </div>
                    <Receipt
                      dark
                      size={21}
                      wrap
                      parts={[`${op.slides.length} slides → 1 page`, `${op.page.figures.length} figures`, `${op.dropped.length} lines dropped`, `${op.seconds} s`, `${fmt(op.usage.total_tokens)} tokens`, op.model]}
                    />
                  </>
                ) : (
                  <>
                    <p style={{fontFamily: theme.serif, fontSize: 40, fontWeight: 500, color: theme.darkInk, margin: '0 0 14px'}}>
                      Her colleague said her name {daysAgo != null ? `${daysAgo} days ago` : 'at an earlier evening'}. The log remembers.
                    </p>
                    <div style={{display: 'flex', gap: 12, marginBottom: 14, flexWrap: 'wrap'}}>
                      <Chip kind="code" dark>
                        code · hooks.py
                      </Chip>
                      <Chip kind="nomodel" dark>
                        no model call
                      </Chip>
                    </div>
                    <Receipt dark size={21} wrap parts={['hook', `${(hook.t_ms / 1000).toFixed(1)} s`, `evidence ${ev.id}`, `turn ${ev.turn.turn}`, ev.date]} />
                    <p style={{fontFamily: theme.mono, fontSize: 19, lineHeight: 1.35, color: theme.darkInkSoft, margin: '12px 0 0'}}>
                      shown as the tag under her name and as a hook row, the way the app draws a hook; the app has no hook notification
                    </p>
                  </>
                )}
              </div>
            );
          })}
        </div>
      </div>
      <div style={{position: 'absolute', left: 1010, right: 48, bottom: 40}}>
        <Receipt dark size={19} wrap parts={bottom} />
      </div>
    </Frame>
  );
};

