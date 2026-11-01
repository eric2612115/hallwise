import React from 'react';
import {Composition} from 'remotion';
import {Previz} from './Previz';
import {shotlist} from './data';

export const Root: React.FC = () => (
  <Composition
    id="Previz"
    component={Previz}
    width={1920}
    height={1080}
    fps={shotlist.fps}
    durationInFrames={shotlist.durationInFrames}
  />
);
