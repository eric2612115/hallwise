// Oblique (cabinet) projection of the apartment: x east, y south, z up.
// South on the floor goes down and slightly right on screen, so north walls sit behind the furniture.
export const S = 84; // px per metre
export const KX = 0.33;
export const KY = 0.84;
export const KZ = 0.75;
export const X0 = 40;
export const Y0 = 240;

export const P = (x: number, y: number, z = 0) => ({sx: X0 + S * (x + y * KX), sy: Y0 + S * (y * KY - z * KZ)});

export const pt = (x: number, y: number, z = 0) => {
  const p = P(x, y, z);
  return `${p.sx.toFixed(1)},${p.sy.toFixed(1)}`;
};

// SVG transform that maps floor metres (around a centre) to screen; use for circles on the floor.
export const floorTransform = (x: number, y: number, z = 0) => {
  const o = P(x, y, z);
  return `matrix(${S} 0 ${S * KX} ${S * KY} ${o.sx} ${o.sy})`;
};

export const theme = {
  paper: '#F3EFE6',
  paperDeep: '#E6E0D2',
  panel: '#FBF9F4',
  ink: '#2A2622',
  inkSoft: '#6E675E',
  inkFaint: '#A39C90',
  rule: '#D3CBB9',
  eric: '#C8861B',
  friend: '#2F7F72',
  camera: '#7A4FA3',
  sound: '#2F6FD0',
  hot: '#C8402F',
  cold: '#3B63A8',
  sans: '-apple-system, "Helvetica Neue", Helvetica, Arial, sans-serif',
  mono: 'Menlo, "SF Mono", ui-monospace, monospace',
};
