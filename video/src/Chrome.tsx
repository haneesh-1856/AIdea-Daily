import React from 'react';
import {AbsoluteFill, Img, interpolate, random, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, H, W, body, mono} from './theme';
import {chapterOf, chapters, levelAt, shotAt, timeline, wordTimes} from './timeline';

const GRAIN =
	"url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.55 0'/></filter><rect width='300' height='300' filter='url(%23n)'/></svg>\")";

/** The set the shots stand in: a slow red glow, a drifting grid, film grain and a vignette. */
export const Background: React.FC = () => {
	const f = useCurrentFrame();
	const t = f / 30;
	const gx = 50 + 28 * Math.sin(t / 9);
	const gy = 45 + 18 * Math.cos(t / 11);
	const pulse = levelAt(f);
	return (
		<AbsoluteFill style={{background: C.bg, overflow: 'hidden'}}>
			<AbsoluteFill
				style={{
					background: `radial-gradient(circle at ${gx}% ${gy}%, rgba(255,43,51,${0.13 + pulse * 0.07}) 0%, rgba(255,43,51,0.03) 32%, transparent 60%)`,
				}}
			/>
			<AbsoluteFill
				style={{
					backgroundImage: `linear-gradient(${C.line} 1px, transparent 1px), linear-gradient(90deg, ${C.line} 1px, transparent 1px)`,
					backgroundSize: '96px 96px',
					backgroundPosition: `${(-f * 0.35) % 96}px ${(-f * 0.2) % 96}px`,
					maskImage: 'radial-gradient(ellipse at center, black 20%, transparent 75%)',
					WebkitMaskImage: 'radial-gradient(ellipse at center, black 20%, transparent 75%)',
				}}
			/>
			<AbsoluteFill
				style={{
					backgroundImage: GRAIN,
					opacity: 0.06,
					backgroundPosition: `${Math.floor(random(`gx${f}`) * 300)}px ${Math.floor(random(`gy${f}`) * 300)}px`,
				}}
			/>
			<AbsoluteFill style={{background: 'radial-gradient(ellipse at center, transparent 55%, rgba(0,0,0,0.65) 100%)'}} />
		</AbsoluteFill>
	);
};

// One heartbeat, as in the logo: a small bump, a dip, the tall spike, a deeper dip, a slow bump.
const beat = (phase: number) => {
	const g = (c: number, w: number, a: number) => a * Math.exp(-((phase - c) ** 2) / (2 * w * w));
	return g(0.16, 0.025, 0.12) + g(0.3, 0.012, -0.18) + g(0.34, 0.012, 1) + g(0.38, 0.014, -0.42) + g(0.58, 0.04, 0.2);
};

/** The heartbeat line from the logo, running along the bottom; it beats harder while the voice is louder. */
export const Ecg: React.FC<{y: number; height: number; opacity?: number; speed?: number}> = ({y, height, opacity = 1, speed = 6}) => {
	const f = useCurrentFrame();
	const period = 360;
	const points: string[] = [];
	for (let x = 0; x <= W; x += 4) {
		const back = Math.round((W - x) / speed); // frames ago that this point was "now"
		const level = levelAt(f - back);
		const world = x + f * speed;
		const phase = (((world % period) + period) % period) / period;
		const amp = 0.12 + level * 0.88;
		points.push(`${x},${(y - beat(phase) * amp * height).toFixed(1)}`);
	}
	const headY = Number(points[points.length - 1].split(',')[1]);
	return (
		<svg width={W} height={H} style={{position: 'absolute', inset: 0, opacity}}>
			<defs>
				<linearGradient id="ecgFade" x1="0" x2="1">
					<stop offset="0" stopColor={C.red} stopOpacity="0" />
					<stop offset="0.35" stopColor={C.red} stopOpacity="0.55" />
					<stop offset="1" stopColor={C.red} stopOpacity="1" />
				</linearGradient>
				<filter id="ecgGlow">
					<feGaussianBlur stdDeviation="4" result="b" />
					<feMerge>
						<feMergeNode in="b" />
						<feMergeNode in="SourceGraphic" />
					</feMerge>
				</filter>
			</defs>
			<polyline points={points.join(' ')} fill="none" stroke="url(#ecgFade)" strokeWidth={3} strokeLinejoin="round" filter="url(#ecgGlow)" />
			<circle cx={W - 2} cy={headY} r={6} fill={C.red} filter="url(#ecgGlow)" />
		</svg>
	);
};

/** The parts that stay on screen through the stories: logo, date, chapter bar and captions. */
export const Chrome: React.FC = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const now = f / fps;
	const {shot, index} = shotAt(now);
	const firstStory = chapters[0]?.start ?? 0;
	const closing = timeline.shots.find((s) => s.part === 'closing')?.start ?? timeline.duration;
	const inStories = now >= firstStory && now < closing;
	const stinger = shot.part === 'cue';
	const showBug = now > 7.5 && now < closing && !stinger;
	const bugIn = spring({frame: f - Math.round(7.5 * fps), fps, config: {damping: 200}});
	const chapter = chapterOf(shot.story);

	return (
		<AbsoluteFill style={{pointerEvents: 'none'}}>
			{showBug && (
				<div style={{position: 'absolute', left: 64, top: 46, width: 210, height: 84, overflow: 'hidden', opacity: bugIn, transform: `translateY(${(1 - bugIn) * -20}px)`}}>
					<Img src={staticFile('aidea-daily-logo-3000.png')} style={{position: 'absolute', width: 224, left: -4, top: -76}} />
				</div>
			)}
			{showBug && (
				<div style={{position: 'absolute', right: 70, top: 62, display: 'flex', alignItems: 'center', gap: 14, fontFamily: mono, fontSize: 20, letterSpacing: 4, color: C.mute, opacity: bugIn}}>
					<div style={{width: 12, height: 12, borderRadius: 6, background: C.red, opacity: 0.4 + 0.6 * Math.abs(Math.sin(now * 2.2))}} />
					{dateStamp(timeline.date)}
				</div>
			)}
			{inStories && !stinger && <ChapterBar now={now} />}
			{inStories && chapter && shot.part !== 'cue' && shot.part !== 'title' && (
				<div style={{position: 'absolute', left: 150, bottom: 74, fontFamily: mono, fontSize: 19, letterSpacing: 3, color: C.mute, display: 'flex', gap: 18, maxWidth: 1500, whiteSpace: 'nowrap', overflow: 'hidden'}}>
					<span style={{color: C.red}}>{String(chapter.number).padStart(2, '0')}/{chapters.length}</span>
					<span style={{color: C.ink, opacity: 0.75, overflow: 'hidden', textOverflow: 'ellipsis'}}>{chapter.title.replace(/\.$/, '').toUpperCase()}</span>
				</div>
			)}
			<Ecg y={1012} height={34} opacity={inStories ? 0.9 : 0.5} />
			<Captions index={index} />
		</AbsoluteFill>
	);
};

const dateStamp = (iso: string) => {
	const d = new Date(iso + 'T12:00:00Z');
	return d.toLocaleDateString('en-GB', {weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', timeZone: 'UTC'}).toUpperCase().replace(/,/g, '');
};

const ChapterBar: React.FC<{now: number}> = ({now}) => {
	const total = timeline.shots.find((s) => s.part === 'closing')?.start ?? timeline.duration;
	const first = chapters[0].start;
	const span = total - first;
	return (
		<div style={{position: 'absolute', left: 150, right: 150, bottom: 52, height: 6, display: 'flex', gap: 6}}>
			{chapters.map((c, i) => {
				const end = chapters[i + 1]?.start ?? total;
				const fill = Math.max(0, Math.min(1, (now - c.start) / (end - c.start)));
				const active = now >= c.start && now < end;
				return (
					<div key={c.story} style={{flex: (end - c.start) / span, background: 'rgba(242,238,230,0.12)', borderRadius: 3, overflow: 'hidden', height: active ? 6 : 4, alignSelf: 'center'}}>
						<div style={{width: `${fill * 100}%`, height: '100%', background: active ? C.red : 'rgba(242,238,230,0.55)'}} />
					</div>
				);
			})}
		</div>
	);
};

// Shots that already show the sentence as large type do not need captions.
const CAPTIONED = new Set(['stat', 'names']);

/** Captions in short groups of words, the current word lit, like a well-cut YouTube video. */
const Captions: React.FC<{index: number}> = ({index}) => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	const shot = timeline.shots[index];
	if (!CAPTIONED.has(shot.layout.kind) || (shot.part === 'credits' && index !== timeline.shots.findIndex((s) => s.part === 'credits'))) return null;
	const local = f / fps - shot.start;
	if (local > shot.end - shot.start + 0.4) return null;
	const words = wordTimes(shot);
	const current = Math.max(0, words.findIndex((w, i) => local >= w.t && (i === words.length - 1 || local < words[i + 1].t)));
	const groupSize = 6;
	const group = Math.floor(current / groupSize);
	const shown = words.slice(group * groupSize, group * groupSize + groupSize);
	const groupStart = Math.round((shot.start + (words[group * groupSize]?.t ?? 0)) * fps);
	const pop = spring({frame: f - groupStart, fps, config: {damping: 14, stiffness: 220, mass: 0.5}});
	return (
		<div style={{position: 'absolute', left: 0, right: 0, bottom: 150, display: 'flex', justifyContent: 'center'}}>
			<div
				style={{
					fontFamily: body,
					fontWeight: 800,
					fontSize: 46,
					color: C.ink,
					padding: '12px 26px',
					background: 'rgba(14,11,11,0.72)',
					borderRadius: 14,
					display: 'flex',
					gap: 14,
					transform: `scale(${0.92 + 0.08 * pop})`,
					boxShadow: '0 20px 60px rgba(0,0,0,0.5)',
				}}
			>
				{shown.map((w, i) => {
					const n = group * groupSize + i;
					const said = n <= current;
					return (
						<span key={n} style={{color: n === current ? C.red : said ? C.ink : 'rgba(242,238,230,0.45)', transform: n === current ? 'translateY(-2px)' : undefined}}>
							{w.word}
						</span>
					);
				})}
			</div>
		</div>
	);
};

export const interpolateClamp = (v: number, a: number[], b: number[]) => interpolate(v, a, b, {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
