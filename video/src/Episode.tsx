import React from 'react';
import {AbsoluteFill, Audio, Sequence, staticFile, useVideoConfig} from 'remotion';
import {Background, Chrome} from './Chrome';
import {Cut, ShotView} from './Shots';
import {Shot, musicVolume, shots} from './timeline';

const frames = (fps: number, s: Shot) => {
	const from = Math.round(s.start * fps);
	return {from, dur: Math.max(1, Math.round(s.next * fps) - from)};
};

// Which sound each kind of cut gets, and how loud. Whooshes peak about 0.25 s in, so they start just before the cut.
const SOUND: Record<string, {file: string; volume: number; lead: number}> = {
	title: {file: 'hit.wav', volume: 0.42, lead: 0},
	cue: {file: 'whoosh-long.wav', volume: 0.32, lead: 0.3},
	intro: {file: 'hit.wav', volume: 0.32, lead: 0},
	stat: {file: 'tick.wav', volume: 0.25, lead: 0},
	headline: {file: 'whoosh-b.wav', volume: 0.16, lead: 0.2},
	opening: {file: 'pulse.wav', volume: 0.5, lead: 0},
};

const Sfx: React.FC = () => {
	const {fps} = useVideoConfig();
	return (
		<>
			{shots.map((s, i) => {
				const sound = SOUND[s.layout.kind] ?? (i % 3 === 0 ? {file: i % 2 ? 'whoosh-a.wav' : 'whoosh-b.wav', volume: 0.1, lead: 0.22} : null);
				if (!sound) return null;
				const from = Math.max(0, Math.round((s.start - sound.lead) * fps));
				return (
					<Sequence key={`sfx${i}`} from={from} durationInFrames={Math.round(1.3 * fps)} layout="none">
						<Audio src={staticFile(`sfx/${sound.file}`)} volume={sound.volume} />
					</Sequence>
				);
			})}
		</>
	);
};

export const Episode: React.FC = () => {
	const {fps} = useVideoConfig();
	return (
		<AbsoluteFill style={{background: '#0E0B0B'}}>
			<Background />
			{shots.map((s, i) => {
				const {from, dur} = frames(fps, s);
				return (
					<Sequence key={i} from={from} durationInFrames={dur} name={`${i} ${s.layout.kind}`}>
						<Cut shot={s} index={i} dur={dur}>
							<ShotView shot={s} index={i} dur={dur} />
						</Cut>
					</Sequence>
				);
			})}
			<Chrome />
			<Audio src={staticFile('episode.mp3')} />
			{/* The music bed from make_music.py, looped, ducked under the voice. */}
			<Audio src={staticFile('music/bed.wav')} loop volume={musicVolume} />
			<Sfx />
		</AbsoluteFill>
	);
};
