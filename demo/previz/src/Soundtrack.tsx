import React from 'react';
import {Audio, Sequence, staticFile, useVideoConfig} from 'remotion';
import {shotlist} from './data';

// The real v5 guest files on the timeline, the hall bed under the party (dropping out where post
// makes silence), stand-in voices for the live lines, and a buzz for each live notification.
export const Soundtrack: React.FC = () => {
  const {fps} = useVideoConfig();
  const bed = shotlist.hallBed;
  const bedVolume = (f: number) => {
    const t = bed.on + f / fps;
    let v = bed.volume;
    for (const s of bed.silences) {
      const ramp = 0.15;
      if (t >= s.start - ramp && t < s.start) v *= (s.start - t) / ramp;
      else if (t >= s.start && t < s.end) v = 0;
      else if (t >= s.end && t < s.end + ramp) v *= (t - s.end) / ramp;
    }
    return Math.max(0, Math.min(1, v));
  };
  return (
    <>
      {shotlist.audio.map((a, i) => (
        <Sequence key={i} from={Math.round(a.at * fps)} durationInFrames={Math.ceil(a.duration * fps) + 2}>
          <Audio src={staticFile(`audio/${a.src}`)} volume={a.volume} />
        </Sequence>
      ))}
      <Sequence from={Math.round(bed.on * fps)} durationInFrames={Math.round((bed.off - bed.on) * fps)}>
        <Audio src={staticFile(`audio/${bed.src}`)} volume={bedVolume} />
      </Sequence>
    </>
  );
};
