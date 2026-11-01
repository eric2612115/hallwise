// Tokens from ios/Sources/Theme.swift and apps/replay/style.css. Paper is only what the owner sees (the badge, a
// notification, a subtitle card, the one-pager, the X-ray cards, the end card); the dark frame is the frozen
// footage and the space around the cards. The two never swap.
//
// Fonts come from Google through @remotion/google-fonts at render time (so a render needs the network). Vendoring
// the woff2 files into public/fonts and loading them with @remotion/fonts would make a render byte-reproducible;
// that download is a separate step. Noto Sans JP is loaded only by the Japanese subtitle card (loadJP), not here.
import {loadFont as loadNewsreader} from '@remotion/google-fonts/Newsreader';
import {loadFont as loadInstrument} from '@remotion/google-fonts/InstrumentSans';
import {loadFont as loadPlex} from '@remotion/google-fonts/IBMPlexMono';
import {loadFont as loadNotoJP} from '@remotion/google-fonts/NotoSansJP';

const newsreader = loadNewsreader('normal', {weights: ['400', '500', '600'], subsets: ['latin', 'latin-ext']});
loadNewsreader('italic', {weights: ['400', '500'], subsets: ['latin', 'latin-ext']});
const instrument = loadInstrument('normal', {weights: ['400', '500', '600', '700'], subsets: ['latin', 'latin-ext']});
const plex = loadPlex('normal', {weights: ['400', '500'], subsets: ['latin', 'latin-ext']});

let jp: string | null = null;
// The Japanese face, loaded the first time a Japanese line is drawn (its subset is large; most compositions never
// need it). loadFont is idempotent and holds the frame until the font is in.
export const loadJP = () => {
  if (!jp) jp = `"${loadNotoJP('normal', {weights: ['400', '500'], subsets: ['japanese', 'latin']}).fontFamily}", "Hiragino Sans", "Noto Sans JP", sans-serif`;
  return jp;
};

export const theme = {
  paper: '#EDE8DC',
  paperRaised: '#F4F0E7',
  paperDeep: '#E2DBC9',
  paperWhite: '#FAF6EE',
  ink: '#2A2622',
  inkStrong: '#1A1613',
  inkSoft: '#6E675E',
  rule: '#D3CBB9',
  accent: '#2F7F72',
  live: '#C8402F',
  pending: '#E0B45A',
  dark: '#1C1A17',
  darkRaised: '#26231F',
  darkInk: '#E8E2D6',
  darkInkSoft: '#A39B8F',
  darkRule: '#35312B',
  darkAccent: '#6FB9AB',
  darkLive: '#E2644F',
  people: ['#2F7F72', '#C8702F', '#7A4FA3', '#B8862B', '#3B63A8', '#5F8A3C', '#B8475F', '#5B6B78'],
  peopleDark: ['#6FB9AB', '#E89A5C', '#B08AD8', '#E0B45A', '#7FA3E0', '#9BC46A', '#E07A91', '#9FB0BE'],
  serif: `"${newsreader.fontFamily}", "New York", ui-serif, Georgia, serif`,
  sans: `"${instrument.fontFamily}", -apple-system, BlinkMacSystemFont, system-ui, sans-serif`,
  mono: `"${plex.fontFamily}", ui-monospace, "SF Mono", Menlo, monospace`,
  ease: 'cubic-bezier(0.22, 1, 0.36, 1)',
};

export const hexA = (hex: string, a: number) => {
  const n = parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
};
