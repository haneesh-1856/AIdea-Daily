import {loadFont as loadArchivo} from '@remotion/google-fonts/Archivo';
import {loadFont as loadInterTight} from '@remotion/google-fonts/InterTight';
import {loadFont as loadMono} from '@remotion/google-fonts/JetBrainsMono';

// The brand: near-black, signal red and off-white, taken from branding/aidea-logo-3000.png.
export const C = {
	bg: '#0E0B0B',
	panel: '#171112',
	red: '#FF2B33',
	redDeep: '#B3121A',
	ink: '#F2EEE6',
	mute: '#8E8682',
	dim: 'rgba(242, 238, 230, 0.28)',
	line: 'rgba(242, 238, 230, 0.07)',
};

export const display = loadArchivo('normal', {weights: ['500', '800', '900'], subsets: ['latin', 'latin-ext']}).fontFamily;
export const body = loadInterTight('normal', {weights: ['500', '600', '700', '800'], subsets: ['latin', 'latin-ext']}).fontFamily;
export const mono = loadMono('normal', {weights: ['500', '700'], subsets: ['latin', 'latin-ext']}).fontFamily;

export const W = 1920;
export const H = 1080;
export const SAFE = {left: 150, right: 150, top: 150, bottom: 250};
