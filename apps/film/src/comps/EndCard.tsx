import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {seg} from '../lib/motion';
import {Chip, Corner, Eyebrow, Frame, Receipt} from '../ui';
import {theme} from '../theme';
import type {ProofData} from '../lib/types';

// The end card (spec 5.8): the badge glyph with the live-red dot, the H mark, Hallwise, the deck's own first line,
// the pipeline row (THE BADGE · CODE → the four Meta models) with the line about what the code checks, BUILT WITH
// chips, Open source · AGPL-3.0, and "One person, nine days". Paper ground, no particles.
export type EndCardProps = {data: ProofData};

const MODELS = ['Muse Voice Transcribe', 'Muse Spark', 'Muse Spark with web search', 'Muse Spark Open on Baseten', 'SAM 3.1'];

export const EndCard: React.FC<EndCardProps> = ({data}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const p0 = seg(frame, 0, Math.round(fps * 0.6));
  const p1 = seg(frame, Math.round(fps * 0.3), Math.round(fps * 0.6));
  const p2 = seg(frame, Math.round(fps * 0.8), Math.round(fps * 0.6));
  const p3 = seg(frame, Math.round(fps * 1.2), Math.round(fps * 0.6));
  const pipe = ['the badge · code', 'Muse Voice Transcribe', 'Muse Spark · + web search', 'Muse Spark Open · Baseten', 'SAM 3.1'];
  return (
    <Frame>
      <div style={{position: 'absolute', inset: 0, display: 'grid', placeItems: 'center', textAlign: 'center'}}>
        <div>
          <svg width={220} height={178} viewBox="0 0 260 210" style={{display: 'block', margin: '0 auto 6px', opacity: p0, transform: `translateY(${(1 - p0) * 20}px)`}}>
            <path d="M130 4 L58 98 M130 4 L202 98" stroke={theme.ink} strokeWidth={3} fill="none" strokeLinecap="round" />
            <path d="M58 98 h144 a10 10 0 0 1 10 10 v82 a10 10 0 0 1 -10 10 h-144 a10 10 0 0 1 -10 -10 v-82 a10 10 0 0 1 10 -10 z" stroke={theme.ink} strokeWidth={3} fill="none" />
            <circle cx={130} cy={98} r={9} stroke={theme.ink} strokeWidth={3} fill="none" />
            <text x={72} y={166} fontFamily={theme.serif} fontSize={54} fontWeight={600} fill={theme.inkStrong}>
              Eric
            </text>
            <circle cx={226} cy={124} r={7} fill={theme.live} />
          </svg>
          <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 30, marginTop: 6, opacity: p0, transform: `translateY(${(1 - p0) * 26}px)`}}>
            <span style={{width: 110, height: 110, borderRadius: '50%', background: theme.ink, color: theme.paper, display: 'grid', placeItems: 'center', fontFamily: theme.serif, fontWeight: 600, fontSize: 66}}>H</span>
            <span style={{fontFamily: theme.serif, fontWeight: 600, fontSize: 150, letterSpacing: '-0.02em', lineHeight: 1, color: theme.inkStrong}}>Hallwise</span>
          </div>
          <p style={{fontFamily: theme.serif, fontStyle: 'italic', fontWeight: 400, fontSize: 56, color: theme.ink, margin: '22px 0 0', opacity: p1, transform: `translateY(${(1 - p1) * 20}px)`}}>{data.onepager.page.lede}</p>

          <div style={{marginTop: 54, opacity: p2, transform: `translateY(${(1 - p2) * 20}px)`}}>
            <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 14, flexWrap: 'wrap'}}>
              {pipe.map((s, i) => (
                <React.Fragment key={s}>
                  {i > 0 ? <span style={{fontFamily: theme.mono, color: theme.inkSoft, fontSize: 24}}>→</span> : null}
                  {i === 0 ? (
                    <Chip kind="code" size={24}>
                      {s}
                    </Chip>
                  ) : (
                    <Chip size={24}>{s}</Chip>
                  )}
                </React.Fragment>
              ))}
            </div>
            <p style={{fontFamily: theme.mono, fontSize: 21, letterSpacing: '0.02em', color: theme.inkSoft, margin: '18px 0 0'}}>
              every model output checked by code: asides kept aside · edges on real words · no source, no line · every number from the deck
            </p>
          </div>

          <div style={{marginTop: 44, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 18, opacity: p3, transform: `translateY(${(1 - p3) * 20}px)`}}>
            <Eyebrow size={22}>Built with</Eyebrow>
            <div style={{display: 'flex', justifyContent: 'center', gap: 14, flexWrap: 'wrap', maxWidth: 1500}}>
              {MODELS.map((m) => (
                <Chip key={m} size={26}>
                  {m}
                </Chip>
              ))}
            </div>
            <div style={{fontFamily: theme.mono, fontSize: 24, letterSpacing: '0.06em', color: theme.inkSoft, marginTop: 10}}>Open source · AGPL-3.0</div>
          </div>
        </div>
      </div>
      <Corner name="end card" parts={['SCRIPT.md · end card', 'hallwise-deck.md · slide 1']} />
      <div style={{position: 'absolute', right: 48, bottom: 40}}>
        <Receipt parts={['One person, nine days', 'Oct 26 to Nov 4, 2026']} />
      </div>
    </Frame>
  );
};
