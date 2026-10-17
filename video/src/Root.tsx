import React from 'react';
import {Composition} from 'remotion';
import {Episode} from './Episode';
import {timeline} from './timeline';

export const Root: React.FC = () => (
	<Composition id="Episode" component={Episode} width={1920} height={1080} fps={timeline.fps} durationInFrames={Math.ceil(timeline.duration * timeline.fps)} />
);
