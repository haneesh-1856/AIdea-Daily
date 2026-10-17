import React from 'react';
import {AbsoluteFill, Easing, Img, interpolate, spring, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {C, SAFE, body, display, mono} from './theme';
import {Picture, Shot, TimedWord, chapterOf, chapters, formatDate, shots, timeOfChar, timeline, wordTimes} from './timeline';

const clamp = {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'} as const;

type P = {shot: Shot; index: number; dur: number};

const useLocal = () => {
	const f = useCurrentFrame();
	const {fps} = useVideoConfig();
	return {f, fps, t: f / fps};
};

// ---------------------------------------------------------------- the cut: how each shot comes in

const ENTRIES = ['whipLeft', 'punch', 'wipeUp', 'whipRight', 'zoomOut', 'slideUp'] as const;
const OWN_ENTRY = new Set(['opening', 'cue', 'title', 'intro']);

/** Every shot is a cut: it comes in with a fast move, then the camera keeps pushing in slowly. */
export const Cut: React.FC<P & {children: React.ReactNode}> = ({shot, index, dur, children}) => {
	const {f, fps} = useLocal();
	const push = 1 + 0.045 * (f / Math.max(1, dur));
	const drift = Math.sin((index * 1.7 + f / fps) * 0.4) * 6;
	if (OWN_ENTRY.has(shot.layout.kind)) {
		return <AbsoluteFill style={{transform: `scale(${push})`}}>{children}</AbsoluteFill>;
	}
	const p = spring({frame: f, fps, config: {damping: 200, mass: 0.55}, durationInFrames: 10});
	const blur = (1 - p) * 26;
	const kind = ENTRIES[index % ENTRIES.length];
	let transform = '';
	let clipPath: string | undefined;
	if (kind === 'whipLeft') transform = `translateX(${(1 - p) * -260}px)`;
	if (kind === 'whipRight') transform = `translateX(${(1 - p) * 260}px)`;
	if (kind === 'punch') transform = `scale(${1 + (1 - p) * 0.28})`;
	if (kind === 'zoomOut') transform = `scale(${1 - (1 - p) * 0.14})`;
	if (kind === 'slideUp') transform = `translateY(${(1 - p) * 140}px)`;
	if (kind === 'wipeUp') clipPath = `inset(${(1 - p) * 100}% 0 0 0)`;
	return (
		<AbsoluteFill style={{transform: `${transform} scale(${push}) translateX(${drift}px)`, filter: blur > 0.5 ? `blur(${blur}px)` : undefined, clipPath, opacity: Math.min(1, f / 2 + 0.2)}}>
			{children}
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- helpers for type

const fitSize = (text: string, sizes: [number, number][]) => {
	for (const [chars, size] of sizes) if (text.length <= chars) return size;
	return sizes[sizes.length - 1][1];
};

const isKey = (w: TimedWord, key: string | null | undefined, text: string) => {
	if (!key) return false;
	const at = text.indexOf(key);
	return at >= 0 && w.charAt >= at && w.charAt < at + key.length;
};

const Tag: React.FC<{children: React.ReactNode; solid?: boolean; style?: React.CSSProperties}> = ({children, solid, style}) => (
	<div
		style={{
			fontFamily: mono,
			fontWeight: 700,
			fontSize: 22,
			letterSpacing: 4,
			padding: '10px 18px',
			borderRadius: 6,
			color: solid ? C.bg : C.red,
			background: solid ? C.red : 'transparent',
			border: `2px solid ${C.red}`,
			textTransform: 'uppercase',
			...style,
		}}
	>
		{children}
	</div>
);

/** Words that light up as they are said. */
const Karaoke: React.FC<{shot: Shot; size: number; weight?: number; keyPhrase?: string | null; font?: string; lineHeight?: number}> = ({shot, size, weight = 700, keyPhrase, font = body, lineHeight = 1.18}) => {
	const {t} = useLocal();
	const words = wordTimes(shot);
	return (
		<div style={{fontFamily: font, fontWeight: weight, fontSize: size, lineHeight, color: C.ink, letterSpacing: -0.5}}>
			{words.map((w, i) => {
				const lit = interpolate(t, [w.t - 0.05, w.t + 0.12], [0, 1], clamp);
				const key = isKey(w, keyPhrase, shot.text);
				return (
					<span key={i} style={{color: key ? C.red : C.ink, opacity: 0.22 + 0.78 * lit}}>
						{w.word}{' '}
					</span>
				);
			})}
		</div>
	);
};

const GhostWord: React.FC<{word: string; index: number}> = ({word, index}) => {
	const {f} = useLocal();
	return (
		<div
			style={{
				position: 'absolute',
				top: index % 2 ? 90 : 560,
				left: -200 + ((f * (index % 2 ? 0.8 : -0.8)) % 4000),
				fontFamily: display,
				fontWeight: 900,
				fontSize: 380,
				whiteSpace: 'nowrap',
				color: 'transparent',
				WebkitTextStroke: '2px rgba(242,238,230,0.06)',
				letterSpacing: -10,
				textTransform: 'uppercase',
			}}
		>
			{word}
		</div>
	);
};

// ---------------------------------------------------------------- pictures

/** A still that is never still: a slow push-in and drift across the whole shot, the direction set by `seed`. */
const KenBurns: React.FC<{picture: Picture; dur: number; seed: number; style?: React.CSSProperties}> = ({picture, dur, seed, style}) => {
	const {f} = useLocal();
	const p = interpolate(f, [0, Math.max(1, dur)], [0, 1], clamp);
	const zoomIn = seed % 2 === 0;
	const scale = zoomIn ? 1.06 + 0.12 * p : 1.18 - 0.1 * p;
	const dx = (seed % 3 === 0 ? -1 : 1) * 2.4 * (p - 0.5);
	const dy = (seed % 4 < 2 ? -1 : 1) * 1.4 * (p - 0.5);
	return (
		<AbsoluteFill style={{overflow: 'hidden', ...style}}>
			<Img src={staticFile(picture.file)} style={{width: '100%', height: '100%', objectFit: 'cover', transform: `scale(${scale}) translate(${dx}%, ${dy}%)`}} />
		</AbsoluteFill>
	);
};

const Credit: React.FC<{picture: Picture; style?: React.CSSProperties}> = ({picture, style}) => (
	<div style={{position: 'absolute', fontFamily: mono, fontSize: 17, letterSpacing: 3, color: 'rgba(242,238,230,0.7)', background: 'rgba(14,11,11,0.6)', padding: '6px 12px', borderRadius: 4, ...style}}>
		{picture.credit === 'AI-generated' ? 'AI-GENERATED ILLUSTRATION' : `IMAGE · ${picture.credit.toUpperCase()}`}
	</div>
);

/** A picture with the sentence over it: full screen with the words on a dark side, or a tilted frame beside them. */
export const Photo: React.FC<P> = ({shot, index, dur}) => {
	const {f, fps} = useLocal();
	const picture = shot.layout.image!;
	const reveal = spring({frame: f, fps, config: {damping: 200, mass: 0.6}, durationInFrames: 16});
	const bar = spring({frame: f - 6, fps, config: {damping: 200}});
	const size = fitSize(shot.text, [[90, 60], [150, 52], [220, 46], [999, 40]]);
	if (index % 2 === 0) {
		return (
			<AbsoluteFill>
				<AbsoluteFill style={{clipPath: `inset(0 0 0 ${(1 - reveal) * 100}%)`}}>
					<KenBurns picture={picture} dur={dur} seed={index} />
					<AbsoluteFill style={{background: 'linear-gradient(90deg, rgba(14,11,11,0.97) 0%, rgba(14,11,11,0.9) 42%, rgba(14,11,11,0.25) 72%, rgba(14,11,11,0.35) 100%)'}} />
					<AbsoluteFill style={{background: 'linear-gradient(0deg, rgba(14,11,11,0.9) 0%, transparent 35%)'}} />
				</AbsoluteFill>
				<div style={{position: 'absolute', left: SAFE.left, top: 0, bottom: 210, width: 860, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
					<div style={{height: 6, width: 160 * bar, background: C.red, marginBottom: 34}} />
					<Karaoke shot={shot} size={size} weight={700} keyPhrase={shot.layout.key} />
				</div>
				<Credit picture={picture} style={{right: 70, top: 120, opacity: reveal}} />
			</AbsoluteFill>
		);
	}
	const tilt = interpolate(f, [0, dur], [-9, -4], clamp);
	return (
		<AbsoluteFill>
			<AbsoluteFill style={{opacity: 0.35 * reveal, filter: 'blur(40px) saturate(1.2)'}}>
				<KenBurns picture={picture} dur={dur} seed={index + 1} />
			</AbsoluteFill>
			<div
				style={{
					position: 'absolute',
					right: 110,
					top: 170,
					width: 960,
					height: 540,
					borderRadius: 18,
					overflow: 'hidden',
					border: `2px solid rgba(242,238,230,0.12)`,
					boxShadow: `0 40px 120px rgba(0,0,0,0.7), -14px 0 0 ${C.red}`,
					transform: `perspective(1600px) rotateY(${tilt}deg) translateX(${(1 - reveal) * 220}px) scale(${0.92 + 0.08 * reveal})`,
					opacity: reveal,
				}}
			>
				<KenBurns picture={picture} dur={dur} seed={index} />
				<Credit picture={picture} style={{right: 16, bottom: 16}} />
			</div>
			<div style={{position: 'absolute', left: SAFE.left, top: 0, bottom: 210, width: 640, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
				<div style={{height: 6, width: 120 * bar, background: C.red, marginBottom: 30}} />
				<Karaoke shot={shot} size={Math.round(size * 0.82)} weight={700} keyPhrase={shot.layout.key} />
			</div>
		</AbsoluteFill>
	);
};

/** A story's lead picture as a red-toned backdrop, behind its title card and its headline. */
const Backdrop: React.FC<{picture: Picture; dur: number; seed: number; opacity: number}> = ({picture, dur, seed, opacity}) => (
	<AbsoluteFill style={{opacity}}>
		<KenBurns picture={picture} dur={dur} seed={seed} style={{filter: 'grayscale(1) contrast(1.2) brightness(0.75)'}} />
		<AbsoluteFill style={{background: C.redDeep, mixBlendMode: 'multiply', opacity: 0.85}} />
		<AbsoluteFill style={{background: 'linear-gradient(90deg, rgba(14,11,11,0.95) 0%, rgba(14,11,11,0.7) 50%, rgba(14,11,11,0.35) 100%)'}} />
	</AbsoluteFill>
);

// ---------------------------------------------------------------- opening

export const Opening: React.FC<P> = () => {
	const {f, fps} = useLocal();
	const draw = interpolate(f, [0, 40], [0, 1], {...clamp, easing: Easing.inOut(Easing.cubic)});
	const reveal = interpolate(f, [18, 52], [0, 100], {...clamp, easing: Easing.out(Easing.cubic)});
	const settle = spring({frame: f - 18, fps, config: {damping: 18, mass: 0.9}});
	const d = formatDate(timeline.date);
	const sub = spring({frame: f - 58, fps, config: {damping: 200}});
	const date = spring({frame: f - 74, fps, config: {damping: 200}});
	const letters = 'YOUR DAILY BRIEFING ON ARTIFICIAL INTELLIGENCE';
	const typed = Math.floor(interpolate(f, [58, 100], [0, letters.length], clamp));
	return (
		<AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
			<svg width={1920} height={1080} style={{position: 'absolute', inset: 0}}>
				<line x1={0} y1={540} x2={1920 * draw} y2={540} stroke={C.red} strokeWidth={4} opacity={1 - reveal / 100} />
			</svg>
			<div style={{position: 'relative', width: 1100, height: 470, overflow: 'hidden', clipPath: `inset(0 ${100 - reveal}% 0 0)`, transform: `scale(${1.12 - 0.12 * settle})`, marginTop: -120}}>
				<Img src={staticFile('aidea-logo-3000.png')} style={{position: 'absolute', width: 1100, top: -340, left: 0}} />
			</div>
			<div style={{fontFamily: mono, fontSize: 30, letterSpacing: 10, color: C.ink, marginTop: 10, opacity: sub, height: 40}}>
				{letters.slice(0, typed)}
				<span style={{opacity: f % 16 < 8 ? 1 : 0, color: C.red}}>▌</span>
			</div>
			<div style={{display: 'flex', gap: 24, marginTop: 40, opacity: date, transform: `translateY(${(1 - date) * 40}px)`}}>
				<Tag solid>{d.weekday}</Tag>
				<Tag>
					{d.day} {d.month} {d.year}
				</Tag>
			</div>
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- headlines rundown

const headlineShots = shots.filter((s) => s.part === 'headline');
const shortLabel = (text: string) => {
	const m = text.match(/^(.*?)\s+(?:has|have|releases|released|reports|launches|is|are|says|announces|unveils|makes|made)\b/);
	return (m ? m[1] : text.split(' ').slice(0, 3).join(' ')).replace(/^(The|A)\s/, '');
};

export const Headline: React.FC<P> = ({shot, dur}) => {
	const {f, fps} = useLocal();
	const n = headlineShots.indexOf(shot);
	const first = n === 0;
	const listIn = first ? spring({frame: f, fps, config: {damping: 200}}) : 1;
	const swap = spring({frame: f, fps, config: {damping: 16, mass: 0.6}});
	return (
		<AbsoluteFill>
			{shot.layout.image && (
				<AbsoluteFill style={{left: 640, maskImage: 'linear-gradient(90deg, transparent, black 30%)', WebkitMaskImage: 'linear-gradient(90deg, transparent, black 30%)'}}>
					<Backdrop picture={shot.layout.image} dur={dur} seed={n} opacity={0.75 * swap} />
					<Credit picture={shot.layout.image} style={{right: 70, bottom: 110, opacity: swap}} />
				</AbsoluteFill>
			)}
			<div style={{position: 'absolute', left: SAFE.left, top: 170, width: 520, opacity: listIn, transform: `translateX(${(1 - listIn) * -80}px)`}}>
				<div style={{fontFamily: mono, fontSize: 22, letterSpacing: 6, color: C.red, marginBottom: 12}}>TODAY</div>
				<div style={{fontFamily: display, fontWeight: 900, fontSize: 64, color: C.ink, lineHeight: 0.95, marginBottom: 46, textTransform: 'uppercase'}}>The headlines</div>
				{headlineShots.map((h, i) => {
					const active = i === n;
					return (
						<div key={i} style={{display: 'flex', alignItems: 'center', gap: 20, height: 66, opacity: active ? 1 : i < n ? 0.5 : 0.28}}>
							<div style={{width: active ? 10 * swap : 0, height: 44, background: C.red, borderRadius: 2}} />
							<div style={{fontFamily: mono, fontSize: 22, color: active ? C.red : C.mute}}>{String(i + 1).padStart(2, '0')}</div>
							<div style={{fontFamily: body, fontWeight: 700, fontSize: 30, color: C.ink, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 400}}>{shortLabel(h.text)}</div>
						</div>
					);
				})}
			</div>
			<div style={{position: 'absolute', left: 760, right: SAFE.right, top: 220, transform: `translateY(${(1 - swap) * 60}px)`, opacity: swap}}>
				<div style={{fontFamily: display, fontWeight: 900, fontSize: 210, lineHeight: 0.8, color: 'transparent', WebkitTextStroke: `3px ${C.red}`, marginBottom: 30}}>{String(n + 1).padStart(2, '0')}</div>
				<Karaoke shot={shot} size={fitSize(shot.text, [[90, 66], [130, 58], [999, 52]])} weight={800} />
			</div>
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- the stinger before each story

export const Cue: React.FC<P> = ({shot, dur}) => {
	const {f, fps} = useLocal();
	const chapter = chapterOf(shot.story);
	const inP = spring({frame: f, fps, config: {damping: 200, mass: 0.5}, durationInFrames: 8});
	const out = interpolate(f, [dur - 6, dur], [0, 1], clamp);
	const word = shot.text.replace(/\.$/, '').toUpperCase();
	return (
		<AbsoluteFill style={{overflow: 'hidden'}}>
			<AbsoluteFill style={{background: C.red, clipPath: `polygon(${(1 - inP) * 120 - 20}% 0, 120% 0, 120% 100%, ${(1 - inP) * 120 - 40}% 100%)`, transform: `translateX(${out * -110}%)`}} />
			<AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', transform: `translateX(${(1 - inP) * 600 - out * 900}px) skewX(-8deg)`}}>
				<div style={{fontFamily: display, fontWeight: 900, fontSize: fitSize(word, [[10, 260], [16, 200], [99, 150]]), color: C.bg, letterSpacing: -6, lineHeight: 1}}>{word}</div>
				{chapter && (
					<div style={{fontFamily: mono, fontWeight: 700, fontSize: 34, letterSpacing: 10, color: C.bg, marginTop: 10}}>
						STORY {String(chapter.number).padStart(2, '0')} / {chapters.length}
					</div>
				)}
			</AbsoluteFill>
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- chapter title card

export const Title: React.FC<P> = ({shot, dur}) => {
	const {f, fps} = useLocal();
	const chapter = chapterOf(shot.story);
	const words = wordTimes(shot);
	const flash = interpolate(f, [0, 7], [0.85, 0], clamp);
	const numIn = spring({frame: f, fps, config: {damping: 20, mass: 1.1}});
	const tagsIn = spring({frame: f - 4, fps, config: {damping: 200}});
	const srcIn = spring({frame: f - 16, fps, config: {damping: 200}});
	const size = fitSize(shot.text, [[45, 104], [80, 88], [120, 74], [999, 60]]);
	const label = chapter?.label;
	return (
		<AbsoluteFill>
			{shot.layout.image && <Backdrop picture={shot.layout.image} dur={dur} seed={chapter?.number ?? 0} opacity={interpolate(f, [0, 12], [0, 1], clamp)} />}
			{shot.layout.image && <Credit picture={shot.layout.image} style={{right: 70, bottom: 110, opacity: srcIn}} />}
			<div
				style={{
					position: 'absolute',
					right: -60 + (f / dur) * -40,
					top: 40,
					fontFamily: display,
					fontWeight: 900,
					fontSize: 640,
					lineHeight: 1,
					color: 'transparent',
					WebkitTextStroke: `4px ${C.red}`,
					opacity: 0.3 * numIn,
					transform: `translateY(${(1 - numIn) * 200}px)`,
					letterSpacing: -30,
				}}
			>
				{String(chapter?.number ?? '').padStart(2, '0')}
			</div>
			<div style={{position: 'absolute', left: SAFE.left, top: 230, maxWidth: 1350}}>
				<div style={{display: 'flex', gap: 16, marginBottom: 44, opacity: tagsIn, transform: `translateX(${(1 - tagsIn) * -60}px)`}}>
					<Tag solid>{chapter?.segment ?? 'Story'}</Tag>
					{label && label !== 'confirmed' && <Tag>{label}</Tag>}
					{label === 'confirmed' && <Tag style={{color: C.ink, borderColor: C.ink}}>✓ confirmed</Tag>}
				</div>
				<div style={{fontFamily: display, fontWeight: 800, fontSize: size, lineHeight: 1.02, color: C.ink, letterSpacing: -2}}>
					{words.map((w, i) => {
						const at = Math.round(w.t * fps * 0.6) + 3; // titles build a little ahead of the voice
						const p = spring({frame: f - at, fps, config: {damping: 16, mass: 0.6}});
						return (
							<span key={i} style={{display: 'inline-block', marginRight: size * 0.24, opacity: p, transform: `translateY(${(1 - p) * 50}px)`, filter: `blur(${(1 - p) * 8}px)`}}>
								{w.word.replace(/\.$/, '')}
							</span>
						);
					})}
				</div>
				{chapter?.sources && chapter.sources.length > 0 && (
					<div style={{marginTop: 56, display: 'flex', alignItems: 'center', gap: 18, fontFamily: mono, fontSize: 24, letterSpacing: 3, color: C.mute, opacity: srcIn}}>
						<span style={{color: C.red}}>SOURCES</span>
						<span style={{width: 40, height: 2, background: C.red}} />
						{chapter.sources.join('  ·  ')}
					</div>
				)}
			</div>
			<AbsoluteFill style={{background: C.red, opacity: flash}} />
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- number callouts

const countText = (value: number, text: string, progress: number) => {
	const decimals = (text.split('.')[1] ?? '').length;
	const v = value * progress;
	const s = v.toFixed(decimals);
	return text.includes(',') ? Number(s).toLocaleString('en-US', {minimumFractionDigits: decimals, maximumFractionDigits: decimals}) : s;
};

const unitLabel = (unit: string) => {
	const u = unit.toLowerCase().replace(/^\s+/, '');
	if (u === 'percent' || u === '%') return '%';
	if (u === 'x' || u === '×') return '×';
	if (['billion', 'million', 'trillion', 'thousand'].includes(u)) return ` ${u[0].toUpperCase() + u.slice(1)}`;
	if (u === 'bit') return '-bit';
	return unit.toUpperCase();
};

const contextAfter = (text: string, figureAt: number) => {
	const rest = text.slice(figureAt).replace(/^\$?[\d.,]+\s?(%|x|×|GB|TB|B|M|K|-?billion|-?million|-?trillion|-?thousand|-?bit|\s?percent)?-?/i, '');
	const phrase = rest.split(/[,.;:]/)[0].trim().split(/\s+/).slice(0, 6).join(' ');
	if (phrase.length > 3) return phrase;
	return text.slice(0, figureAt).trim().split(/\s+/).slice(-5).join(' ');
};

export const Stat: React.FC<P> = ({shot, index}) => {
	const {f, fps, t} = useLocal();
	const figs = shot.layout.figures ?? [];
	const main = figs[0];
	const mainAt = Math.max(0, timeOfChar(shot, main.at) - 0.25);
	const count = interpolate(t, [mainAt, mainAt + 0.9], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
	const pop = spring({frame: f - Math.round(mainAt * fps), fps, config: {damping: 12, mass: 0.7}});
	const u = unitLabel(main.unit);
	const isPct = u === '%';
	const isMult = u === '×';
	const label = contextAfter(shot.text, main.at);
	const numberText = `${main.prefix}${countText(main.value, main.text, count)}`;
	const numberSize = numberText.length + u.length > 9 ? 190 : 270;
	const rest = figs.slice(1);
	if (rest.length === 0 && !isPct && !isMult) {
		return (
			<AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', paddingBottom: 170}}>
				<Burst progress={pop} />
				<div style={{fontFamily: mono, fontSize: 24, letterSpacing: 8, color: C.red, marginBottom: 10, opacity: pop}}>BY THE NUMBERS</div>
				<div style={{fontFamily: display, fontWeight: 900, fontSize: numberText.length + u.length > 9 ? 230 : 330, lineHeight: 0.95, color: C.ink, letterSpacing: -10, transform: `scale(${0.8 + 0.2 * pop})`, whiteSpace: 'nowrap'}}>
					{numberText}
					<span style={{color: C.red, fontSize: (numberText.length + u.length > 9 ? 230 : 330) * (u.length > 3 ? 0.4 : 0.7), letterSpacing: -2}}>{u}</span>
				</div>
				<div style={{height: 8, width: 520 * count, background: C.red, margin: '22px 0 26px', borderRadius: 4}} />
				<div style={{fontFamily: body, fontWeight: 700, fontSize: 54, color: C.ink, opacity: 0.9 * pop, maxWidth: 1300, textAlign: 'center'}}>{label}</div>
			</AbsoluteFill>
		);
	}
	return (
		<AbsoluteFill>
			<div style={{position: 'absolute', left: SAFE.left, top: 190, maxWidth: rest.length || isPct || isMult ? 1000 : 1600}}>
				<div style={{fontFamily: mono, fontSize: 24, letterSpacing: 6, color: C.red, marginBottom: 18, opacity: pop}}>BY THE NUMBERS</div>
				<div style={{fontFamily: display, fontWeight: 900, fontSize: numberSize, lineHeight: 0.9, color: C.ink, letterSpacing: -8, transform: `scale(${0.85 + 0.15 * pop})`, transformOrigin: 'left center', whiteSpace: 'nowrap'}}>
					{numberText}
					<span style={{color: C.red, fontSize: numberSize * (u.length > 3 ? 0.42 : 0.7), letterSpacing: -2}}>{u}</span>
				</div>
				<div style={{height: 8, width: `${count * 100}%`, maxWidth: 620, background: C.red, margin: '30px 0 26px', borderRadius: 4}} />
				<div style={{fontFamily: body, fontWeight: 700, fontSize: 52, lineHeight: 1.1, color: C.ink, opacity: 0.9 * pop, maxWidth: 980}}>{label}</div>
			</div>
			{isPct && rest.length === 0 && <Gauge value={main.value} progress={count} />}
			{isMult && rest.length === 0 && <Bars value={main.value} progress={count} />}
			{rest.length > 0 && (
				<div style={{position: 'absolute', right: SAFE.right, top: 230, width: 560, display: 'flex', flexDirection: 'column', gap: 26}}>
					{rest.map((r, i) => {
						const at = Math.max(mainAt + 0.4 * (i + 1), timeOfChar(shot, r.at) - 0.2);
						const p = spring({frame: f - Math.round(at * fps), fps, config: {damping: 15, mass: 0.6}});
						const c = interpolate(t, [at, at + 0.7], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
						return (
							<div key={i} style={{background: C.panel, border: `1px solid rgba(255,43,51,0.35)`, borderLeft: `8px solid ${C.red}`, borderRadius: 14, padding: '26px 32px', opacity: p, transform: `translateX(${(1 - p) * 120}px)`}}>
								<div style={{fontFamily: display, fontWeight: 900, fontSize: 92, color: C.ink, lineHeight: 1, letterSpacing: -3}}>
									{r.prefix}
									{countText(r.value, r.text, c)}
									<span style={{color: C.red, fontSize: 52}}>{unitLabel(r.unit)}</span>
								</div>
								<div style={{fontFamily: body, fontWeight: 600, fontSize: 28, color: C.mute, marginTop: 8}}>{contextAfter(shot.text, r.at)}</div>
							</div>
						);
					})}
				</div>
			)}
			<GhostWord word={`${main.prefix}${main.text}${u.trim()}`} index={index} />
		</AbsoluteFill>
	);
};

const Burst: React.FC<{progress: number}> = ({progress}) => {
	const {f} = useLocal();
	return (
		<svg width={1920} height={1080} style={{position: 'absolute', inset: 0}}>
			{Array.from({length: 36}).map((_, i) => {
				const a = (i / 36) * Math.PI * 2 + f * 0.002;
				const r1 = 640 + 60 * Math.sin(i * 1.7);
				const r2 = r1 + 40 + 160 * progress * (0.5 + 0.5 * Math.sin(i * 2.3));
				return <line key={i} x1={960 + Math.cos(a) * r1} y1={455 + Math.sin(a) * r1 * 0.5} x2={960 + Math.cos(a) * r2} y2={455 + Math.sin(a) * r2 * 0.5} stroke={i % 4 === 0 ? C.red : 'rgba(242,238,230,0.12)'} strokeWidth={i % 4 === 0 ? 4 : 2} strokeLinecap="round" opacity={progress} />;
			})}
		</svg>
	);
};

const Gauge: React.FC<{value: number; progress: number}> = ({value, progress}) => {
	const r = 230;
	const c = 2 * Math.PI * r;
	return (
		<svg width={600} height={600} style={{position: 'absolute', right: 170, top: 170}}>
			<circle cx={300} cy={300} r={r} fill="none" stroke="rgba(242,238,230,0.08)" strokeWidth={34} />
			<circle cx={300} cy={300} r={r} fill="none" stroke={C.red} strokeWidth={34} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - (Math.min(100, value) / 100) * progress)} transform="rotate(-90 300 300)" />
			{Array.from({length: 40}).map((_, i) => {
				const a = (i / 40) * Math.PI * 2;
				return <line key={i} x1={300 + Math.cos(a) * 180} y1={300 + Math.sin(a) * 180} x2={300 + Math.cos(a) * 192} y2={300 + Math.sin(a) * 192} stroke="rgba(242,238,230,0.2)" strokeWidth={2} />;
			})}
		</svg>
	);
};

const Bars: React.FC<{value: number; progress: number}> = ({value, progress}) => {
	const max = 560;
	const small = max / Math.max(1, value);
	return (
		<div style={{position: 'absolute', right: 230, bottom: 280, display: 'flex', alignItems: 'flex-end', gap: 60}}>
			{[
				{h: small, label: '1×', color: 'rgba(242,238,230,0.25)'},
				{h: max * progress, label: `${value}×`, color: C.red},
			].map((b, i) => (
				<div key={i} style={{display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 16}}>
					<div style={{width: 150, height: Math.max(8, b.h), background: b.color, borderRadius: 10}} />
					<div style={{fontFamily: mono, fontSize: 30, color: C.ink}}>{b.label}</div>
				</div>
			))}
		</div>
	);
};

// ---------------------------------------------------------------- kinetic type

export const Kinetic: React.FC<P> = ({shot, index}) => {
	const key = shot.layout.key;
	let variant = shot.layout.variant ?? 0;
	if (variant === 1 && (!key || key.length > 34)) variant = 2;
	return (
		<AbsoluteFill>
			{key && <GhostWord word={key} index={index} />}
			{variant === 0 && <Slam shot={shot} keyPhrase={key} />}
			{variant === 1 && <Entity shot={shot} keyPhrase={key!} />}
			{variant === 2 && <Marker shot={shot} keyPhrase={key} />}
		</AbsoluteFill>
	);
};

const Slam: React.FC<{shot: Shot; keyPhrase?: string | null}> = ({shot, keyPhrase}) => {
	const {f, fps} = useLocal();
	const words = wordTimes(shot);
	const size = fitSize(shot.text, [[50, 120], [90, 96], [140, 80], [200, 68], [999, 58]]);
	return (
		<AbsoluteFill style={{justifyContent: 'center', padding: `0 ${SAFE.right}px 120px ${SAFE.left}px`}}>
			<div style={{fontFamily: display, fontWeight: 900, fontSize: size, lineHeight: 1.04, color: C.ink, letterSpacing: -2, textTransform: 'uppercase'}}>
				{words.map((w, i) => {
					const at = Math.round((w.t - 0.06) * fps);
					const p = spring({frame: f - at, fps, config: {damping: 13, stiffness: 260, mass: 0.45}});
					const key = isKey(w, keyPhrase, shot.text);
					return (
						<span
							key={i}
							style={{
								display: 'inline-block',
								marginRight: size * 0.26,
								opacity: Math.min(1, p * 1.6),
								transform: `scale(${1.5 - 0.5 * p})`,
								filter: p < 0.95 ? `blur(${(1 - p) * 10}px)` : undefined,
								color: key ? C.red : C.ink,
							}}
						>
							{w.word}
						</span>
					);
				})}
			</div>
		</AbsoluteFill>
	);
};

const Entity: React.FC<{shot: Shot; keyPhrase: string}> = ({shot, keyPhrase}) => {
	const {f, fps} = useLocal();
	const inP = spring({frame: f, fps, config: {damping: 200}});
	const fill = interpolate(f, [4, 26], [0, 100], {...clamp, easing: Easing.inOut(Easing.cubic)});
	const size = fitSize(keyPhrase, [[8, 230], [14, 180], [22, 136], [99, 104]]);
	return (
		<AbsoluteFill style={{justifyContent: 'center', padding: `0 ${SAFE.right}px 110px ${SAFE.left}px`}}>
			<div
				style={{
					fontFamily: display,
					fontWeight: 900,
					fontSize: size,
					lineHeight: 0.95,
					letterSpacing: -5,
					textTransform: 'uppercase',
					color: 'transparent',
					WebkitTextStroke: `3px ${C.ink}`,
					backgroundImage: `linear-gradient(90deg, ${C.ink} ${fill}%, transparent ${fill}%)`,
					WebkitBackgroundClip: 'text',
					backgroundClip: 'text',
					transform: `translateY(${(1 - inP) * 40}px)`,
				}}
			>
				{keyPhrase}
			</div>
			<div style={{height: 6, width: 220 * inP, background: C.red, margin: '36px 0 32px'}} />
			<div style={{maxWidth: 1450}}>
				<Karaoke shot={shot} size={fitSize(shot.text, [[90, 54], [160, 46], [999, 40]])} weight={600} keyPhrase={keyPhrase} />
			</div>
		</AbsoluteFill>
	);
};

const Marker: React.FC<{shot: Shot; keyPhrase?: string | null}> = ({shot, keyPhrase}) => {
	const {t} = useLocal();
	const words = wordTimes(shot);
	const size = fitSize(shot.text, [[70, 92], [120, 78], [180, 66], [999, 56]]);
	const keyAt = keyPhrase ? shot.text.indexOf(keyPhrase) : -1;
	const keyT = keyAt >= 0 ? timeOfChar(shot, keyAt) : 0;
	const sweep = interpolate(t, [keyT, keyT + 0.35], [0, 1], {...clamp, easing: Easing.out(Easing.cubic)});
	return (
		<AbsoluteFill style={{justifyContent: 'center', padding: `0 ${SAFE.right + 60}px 120px ${SAFE.left}px`}}>
			<div style={{fontFamily: body, fontWeight: 800, fontSize: size, lineHeight: 1.22, color: C.ink, letterSpacing: -1}}>
				{words.map((w, i) => {
					const lit = interpolate(t, [w.t - 0.05, w.t + 0.12], [0, 1], clamp);
					const key = isKey(w, keyPhrase, shot.text);
					return (
						<span key={i} style={{position: 'relative', display: 'inline-block', marginRight: size * 0.25, opacity: key ? 1 : 0.2 + 0.8 * lit, color: key ? C.bg : C.ink, zIndex: 1}}>
							{key && (
								<span style={{position: 'absolute', left: -8, right: -size * 0.25 - 2, top: '8%', bottom: '4%', background: C.red, transformOrigin: 'left', transform: `scaleX(${sweep})`, zIndex: -1, borderRadius: 4}} />
							)}
							<span style={{color: key ? (sweep > 0.5 ? C.bg : C.red) : C.ink}}>{w.word}</span>
						</span>
					);
				})}
			</div>
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- what a source says

export const Quote: React.FC<P> = ({shot, index}) => {
	const {f, fps} = useLocal();
	const p = spring({frame: f, fps, config: {damping: 200}});
	const mark = spring({frame: f - 2, fps, config: {damping: 11, mass: 0.8}});
	const right = index % 2 === 1;
	const source = shot.layout.source ?? '';
	return (
		<AbsoluteFill>
			<div style={{position: 'absolute', [right ? 'right' : 'left']: SAFE.left - 30, top: 190, fontFamily: display, fontWeight: 900, fontSize: 420, lineHeight: 1, color: C.red, opacity: 0.9, transform: `scale(${mark}) rotate(${(1 - mark) * -20}deg)`}}>
				{right ? '”' : '“'}
			</div>
			<div style={{position: 'absolute', left: right ? SAFE.left : 420, right: right ? 420 : SAFE.right, top: 0, bottom: 200, display: 'flex', flexDirection: 'column', justifyContent: 'center'}}>
				<div style={{display: 'flex', alignItems: 'center', gap: 18, marginBottom: 36, opacity: p, transform: `translateY(${(1 - p) * -20}px)`}}>
					<div style={{width: 64, height: 64, borderRadius: 32, background: C.red, color: C.bg, fontFamily: display, fontWeight: 900, fontSize: 30, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>
						{initials(source)}
					</div>
					<div style={{fontFamily: mono, fontWeight: 700, fontSize: 30, letterSpacing: 5, color: C.ink}}>{source.toUpperCase()}</div>
					<div style={{fontFamily: mono, fontSize: 22, letterSpacing: 4, color: C.mute}}>· {shot.part === 'how' ? 'HOW THEY SEE IT' : 'SAYS'}</div>
				</div>
				<div style={{borderLeft: `6px solid ${C.red}`, paddingLeft: 40}}>
					<Karaoke shot={shot} size={fitSize(shot.text, [[90, 66], [150, 56], [220, 48], [999, 42]])} weight={600} />
				</div>
			</div>
		</AbsoluteFill>
	);
};

const initials = (name: string) =>
	name
		.replace(/^The\s+/, '')
		.split(/\s+/)
		.map((w) => w[0])
		.join('')
		.slice(0, 2)
		.toUpperCase();

// ---------------------------------------------------------------- a list of names

export const Names: React.FC<P> = ({shot}) => {
	const {f, fps} = useLocal();
	const names = shot.layout.names ?? [];
	const cols = names.length > 4 ? 3 : 2;
	return (
		<AbsoluteFill style={{padding: `0 ${SAFE.right}px 230px ${SAFE.left}px`, justifyContent: 'center'}}>
			<div style={{display: 'grid', gridTemplateColumns: `repeat(${cols}, 1fr)`, gap: 28}}>
				{names.map((n, i) => {
					const at = Math.max(i * 0.12, timeOfChar(shot, Math.max(0, shot.text.indexOf(n))) - 0.15);
					const p = spring({frame: f - Math.round(at * fps), fps, config: {damping: 13, mass: 0.6}});
					return (
						<div key={i} style={{display: 'flex', alignItems: 'center', gap: 26, background: C.panel, border: '1px solid rgba(242,238,230,0.08)', borderRadius: 18, padding: '30px 34px', opacity: Math.min(1, p * 1.5), transform: `translateY(${(1 - p) * 70}px) scale(${0.9 + 0.1 * p})`}}>
							<div style={{width: 78, height: 78, flex: 'none', borderRadius: 39, background: i % 2 ? C.ink : C.red, color: C.bg, fontFamily: display, fontWeight: 900, fontSize: 34, display: 'flex', alignItems: 'center', justifyContent: 'center'}}>{initials(n)}</div>
							<div style={{fontFamily: body, fontWeight: 800, fontSize: 44, color: C.ink, lineHeight: 1.05}}>{n}</div>
						</div>
					);
				})}
			</div>
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- stamps: update, unconfirmed

export const Intro: React.FC<P> = ({shot}) => {
	const {f, fps} = useLocal();
	const word = /unconfirmed/i.test(shot.text) ? 'UNCONFIRMED' : /update/i.test(shot.text) ? 'UPDATE' : shot.text.toUpperCase();
	const slam = spring({frame: f, fps, config: {damping: 9, stiffness: 300, mass: 0.6}});
	const shake = f < 10 ? Math.sin(f * 3.1) * (10 - f) * 1.4 : 0;
	return (
		<AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', transform: `translate(${shake}px, ${-shake * 0.6}px)`}}>
			<div style={{fontFamily: display, fontWeight: 900, fontSize: 190, color: C.red, border: `14px solid ${C.red}`, borderRadius: 20, padding: '10px 60px', transform: `rotate(-6deg) scale(${2.6 - 1.6 * slam})`, opacity: Math.min(1, slam * 2), letterSpacing: 6}}>{word}</div>
			<div style={{fontFamily: mono, fontSize: 30, letterSpacing: 6, color: C.mute, marginTop: 70}}>{shot.text.replace(/\.$/, '').toUpperCase()}</div>
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- what to watch for

export const Watch: React.FC<P> = ({shot, index}) => {
	const {f, fps} = useLocal();
	const m = shot.text.match(/(January|February|March|April|May|June|July|August|September|October|November|December) (\d+)/);
	const flip = spring({frame: f - 4, fps, config: {damping: 14, mass: 0.8}});
	const first = shots.findIndex((s) => s.part === 'watch') === index;
	const head = first ? spring({frame: f, fps, config: {damping: 200}}) : 1;
	return (
		<AbsoluteFill style={{padding: `200px ${SAFE.right}px 0 ${SAFE.left}px`}}>
			<div style={{fontFamily: mono, fontSize: 26, letterSpacing: 8, color: C.red, opacity: head}}>ON THE RADAR</div>
			<div style={{display: 'flex', gap: 80, marginTop: 60, alignItems: 'center'}}>
				{m && (
					<div style={{width: 340, flex: 'none', borderRadius: 26, overflow: 'hidden', background: C.ink, transform: `perspective(900px) rotateX(${(1 - flip) * 90}deg)`, transformOrigin: 'top', boxShadow: '0 30px 80px rgba(0,0,0,0.6)'}}>
						<div style={{background: C.red, color: C.bg, fontFamily: mono, fontWeight: 700, fontSize: 32, letterSpacing: 8, textAlign: 'center', padding: '18px 0'}}>{m[1].slice(0, 3).toUpperCase()}</div>
						<div style={{fontFamily: display, fontWeight: 900, fontSize: 200, color: C.bg, textAlign: 'center', lineHeight: 1.1}}>{m[2]}</div>
					</div>
				)}
				<Karaoke shot={shot} size={60} weight={700} />
			</div>
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- the end

export const Closing: React.FC<P> = ({shot}) => (
	<AbsoluteFill style={{justifyContent: 'center', padding: `0 ${SAFE.right}px 100px ${SAFE.left}px`}}>
		<Slam shot={shot} keyPhrase="AI news" />
	</AbsoluteFill>
);

export const Credits: React.FC<P> = ({shot, dur}) => {
	const {f, fps} = useLocal();
	const credits = shots.filter((s) => s.part === 'credits');
	const n = credits.indexOf(shot);
	if (n === 0) {
		const list = shot.text.replace(/^.*?from\s+/i, '').replace(/\.$/, '').split(/,\s*|\s+and\s+/).filter(Boolean);
		const lines = Math.ceil(list.length / 3);
		const scroll = interpolate(f, [fps * 2, dur], [0, Math.max(0, lines * 92 - 520)], clamp);
		return (
			<AbsoluteFill style={{padding: `170px ${SAFE.right}px 0 ${SAFE.left}px`}}>
				<div style={{fontFamily: mono, fontSize: 26, letterSpacing: 8, color: C.red}}>TODAY'S SOURCES</div>
				<div style={{position: 'relative', height: 620, overflow: 'hidden', marginTop: 40, maskImage: 'linear-gradient(transparent, black 8%, black 85%, transparent)', WebkitMaskImage: 'linear-gradient(transparent, black 8%, black 85%, transparent)'}}>
					<div style={{display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', columnGap: 40, rowGap: 30, transform: `translateY(${-scroll + 30}px)`}}>
						{list.map((name, i) => {
							const at = timeOfChar(shot, Math.max(0, shot.text.indexOf(name)));
							const p = spring({frame: f - Math.round(at * fps), fps, config: {damping: 200}});
							return (
								<div key={i} style={{fontFamily: display, fontWeight: 800, fontSize: 52, color: C.ink, opacity: 0.15 + 0.85 * p, transform: `translateX(${(1 - p) * 30}px)`, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis'}}>
									<span style={{color: C.red, fontFamily: mono, fontSize: 24, marginRight: 16}}>{String(i + 1).padStart(2, '0')}</span>
									{name}
								</div>
							);
						})}
					</div>
				</div>
			</AbsoluteFill>
		);
	}
	if (n === 1) {
		return (
			<AbsoluteFill style={{justifyContent: 'center', padding: `0 ${SAFE.right}px 100px ${SAFE.left}px`}}>
				<Marker shot={shot} keyPhrase="show notes" />
			</AbsoluteFill>
		);
	}
	const logo = spring({frame: f, fps, config: {damping: 20, mass: 1}});
	const line = spring({frame: f - 14, fps, config: {damping: 200}});
	return (
		<AbsoluteFill style={{alignItems: 'center', justifyContent: 'center'}}>
			<div style={{position: 'relative', width: 1000, height: 430, overflow: 'hidden', transform: `scale(${0.9 + 0.1 * logo})`, opacity: logo, marginTop: -80}}>
				<Img src={staticFile('aidea-daily-logo-3000.png')} style={{position: 'absolute', width: 1000, top: -330, left: 0}} />
			</div>
			<div style={{fontFamily: display, fontWeight: 800, fontSize: 64, color: C.ink, opacity: line, transform: `translateY(${(1 - line) * 30}px)`}}>Thanks for watching.</div>
			<div style={{fontFamily: mono, fontSize: 26, letterSpacing: 8, color: C.mute, marginTop: 24, opacity: line}}>NEW EPISODE EVERY MORNING</div>
		</AbsoluteFill>
	);
};

// ---------------------------------------------------------------- choosing the shot

export const ShotView: React.FC<P> = (p) => {
	switch (p.shot.layout.kind) {
		case 'opening':
			return <Opening {...p} />;
		case 'headline':
			return <Headline {...p} />;
		case 'cue':
			return <Cue {...p} />;
		case 'title':
			return <Title {...p} />;
		case 'stat':
			return <Stat {...p} />;
		case 'photo':
			return <Photo {...p} />;
		case 'quote':
			return <Quote {...p} />;
		case 'names':
			return <Names {...p} />;
		case 'intro':
			return <Intro {...p} />;
		case 'watch':
			return <Watch {...p} />;
		case 'closing':
			return <Closing {...p} />;
		case 'credits':
			return <Credits {...p} />;
		default:
			return <Kinetic {...p} />;
	}
};
