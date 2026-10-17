import data from './timeline.json';

export type Figure = {prefix: string; value: number; text: string; unit: string; at: number};
export type Picture = {file: string; credit: string};
export type Layout = {
	kind: string;
	variant?: number;
	key?: string | null;
	source?: string;
	names?: string[];
	figures?: Figure[];
	image?: Picture;
};
export type Shot = {
	part: string;
	story: number | null;
	text: string;
	start: number; // seconds into the episode when the sentence starts
	end: number; // when the voice stops
	next: number; // when the next shot starts
	words?: number[]; // when each word is said, in seconds from the start, as Whisper heard it
	layout: Layout;
};
export type Chapter = {
	story: number;
	number: number;
	title: string;
	start: number;
	segment?: string;
	label?: string;
	sources?: string[];
};

export const timeline = data as unknown as {
	date: string;
	fps: number;
	duration: number;
	shots: Shot[];
	chapters: Chapter[];
	level: number[];
};

export const shots = timeline.shots;
export const chapters = timeline.chapters;

export const chapterOf = (story: number | null) => chapters.find((c) => c.story === story);

export const shotAt = (seconds: number): {shot: Shot; index: number} => {
	let lo = 0;
	let hi = shots.length - 1;
	while (lo < hi) {
		const mid = Math.ceil((lo + hi) / 2);
		if (shots[mid].start <= seconds) lo = mid;
		else hi = mid - 1;
	}
	return {shot: shots[lo], index: lo};
};

export const levelAt = (frame: number) => timeline.level[Math.max(0, Math.min(timeline.level.length - 1, frame))] ?? 0;

export type TimedWord = {word: string; t: number; charAt: number};

const timed = new Map<Shot, TimedWord[]>();

/**
 * When each word is said, in seconds from the start of the shot: Whisper's times from build_timeline.py. Without
 * them, the speech time is shared out by the length of each word, which is close for one sentence.
 */
export const wordTimes = (shot: Shot): TimedWord[] => {
	const known = timed.get(shot);
	if (known) return known;
	const speech = Math.max(0.3, shot.end - shot.start);
	const parts = shot.text.split(/(\s+)/);
	const total = shot.text.length || 1;
	const out: TimedWord[] = [];
	let at = 0;
	for (const p of parts) {
		if (p.trim()) out.push({word: p, t: (at / total) * speech, charAt: at});
		at += p.length;
	}
	if (shot.words && shot.words.length === out.length) out.forEach((w, i) => (w.t = shot.words![i]));
	timed.set(shot, out);
	return out;
};

/** The moment, in seconds from the start of the shot, when the character at `charAt` is said. */
export const timeOfChar = (shot: Shot, charAt: number) => {
	const words = wordTimes(shot);
	let t = 0;
	for (const w of words) if (w.charAt <= charAt) t = w.t;
	return t;
};

/**
 * How loud the music bed is at each frame: about 20 dB under the voice while it speaks, about 12 dB under on the
 * stingers between stories, up after the last word, faded in and out, and eased so it never jumps.
 * Measured on 2026-10-16: the voice is -27 dB RMS and the bed -11 dB, so 0.018 puts the bed 20 dB down.
 */
export const musicVolume = (() => {
	const fps = timeline.fps;
	const frames = Math.ceil(timeline.duration * fps);
	const target = new Float32Array(frames).fill(0.018);
	for (const s of shots) {
		if (s.part !== 'cue' && s.part !== 'opening' && s.part !== 'credits') continue;
		const lift = s.part === 'cue' ? 0.07 : 0.035;
		for (let f = Math.round(s.start * fps); f < Math.min(frames, Math.round(s.next * fps)); f++) target[f] = lift;
	}
	const lastWord = shots[shots.length - 1].end;
	for (let f = Math.round(lastWord * fps); f < frames; f++) target[f] = 0.12;
	const out = new Float32Array(frames);
	let v = 0;
	for (let f = 0; f < frames; f++) {
		v += (target[f] - v) * (target[f] > v ? 0.06 : 0.04);
		out[f] = v;
	}
	const fadeIn = fps * 1.5;
	const fadeOut = fps * 2.5;
	for (let f = 0; f < frames; f++) out[f] *= Math.min(1, f / fadeIn, (frames - f) / fadeOut);
	return (frame: number) => out[Math.max(0, Math.min(frames - 1, frame))];
})();

export const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

export const formatDate = (iso: string) => {
	const d = new Date(iso + 'T12:00:00Z');
	const day = d.toLocaleDateString('en-GB', {weekday: 'long', timeZone: 'UTC'});
	return {weekday: day, day: d.getUTCDate(), month: MONTHS[d.getUTCMonth()], year: d.getUTCFullYear()};
};
