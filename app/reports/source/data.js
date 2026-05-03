// Sample hitter data — modeled after the screenshot
window.HITTERS = [
  { rank: 1, name: 'Dane Myers',      pa: 49,  pos: 'CF', fpos: 'OF',     proc: 147.3, procPos: 171.7, kavoid: 115.0, power: 168.7, swing: 33.0, chase: 70.7, mc: 0.617, mci: 0.760, blast: '—',  ev: '—',  signal: 'Too Small',  flag: 'Power Flag',          sample: 'Too Small' },
  { rank: 2, name: 'Yordan Alvarez',  pa: 115, pos: 'OF', fpos: 'OF, DH', proc: 145.1, procPos: 126.7, kavoid: 124.5, power: 148.2, swing: 42.4, chase: 28.8, mc: 0.580, mci: 0.117, blast: 18.9, ev: 75.3, signal: 'Top Target', flag: 'Power Flag',          sample: 'Small' },
  { rank: 3, name: 'Dalton Rushing',  pa: 40,  pos: 'C',  fpos: 'C, 1B',  proc: 142.4, procPos: 131.3, kavoid: 96.1, power: 154.7, swing: 45.7, chase: 73.7, mc: 0.616, mci: 0.713, blast: '—',  ev: '—',  signal: 'Top Target', flag: 'Power Flag',          sample: 'Small' },
  { rank: 4, name: 'Luke Raley',      pa: 83,  pos: 'OF', fpos: 'OF',     proc: 141.7, procPos: 120.0, kavoid: 92.5, power: 160.2, swing: 33.4, chase: 29.7, mc: 0.467, mci: 0.298, blast: 12.1, ev: 75.4, signal: 'Top Target', flag: 'Chase Risk, Power Flag', sample: 'Small' },
  { rank: 5, name: 'James Wood',      pa: 127, pos: 'OF', fpos: 'OF',     proc: 138.9, procPos: 137.8, kavoid: 97.4, power: 142.3, swing: 33.7, chase: 26.9, mc: 0.624, mci: 0.557, blast: 16.7, ev: 76.4, signal: 'Top Target', flag: 'Power Flag',          sample: 'Small' },
  { rank: 6, name: 'Ben Rice',        pa: 161, pos: '1B', fpos: '1B',     proc: 132.1, procPos: 110.9, kavoid: 99.3, power: 143.9, swing: 37.6, chase: 20.4, mc: 0.476, mci: 0.215, blast: 19.0, ev: 72.3, signal: 'Top Target', flag: 'Power Flag',          sample: 'Small' },
  { rank: 7, name: 'Jordan Walker',   pa: 188, pos: 'OF', fpos: 'OF',     proc: 130.0, procPos: 119.0, kavoid: 87.6, power: 143.5, swing: 50.7, chase: 31.3, mc: 0.624, mci: 0.713, blast: 15.0, ev: 71.3, signal: 'Top Target', flag: 'Power Flag',          sample: 'Small' },
  { rank: 8, name: 'Dillon Dingler',  pa: 94,  pos: 'C',  fpos: 'C',      proc: 128.8, procPos: 123.8, kavoid: 118.9, power: 131.5, swing: 48.9, chase: 32.9, mc: 0.455, mci: 0.152, blast: 15.7, ev: 71.3, signal: 'Top Target', flag: 'Power Flag',          sample: 'Small' },
  { rank: 9, name: 'Oneil Cruz',      pa: 111, pos: 'OF', fpos: 'OF',     proc: 127.4, procPos: 138.2, kavoid: 106.7, power: 138.0, swing: 44.7, chase: 29.9, mc: 0.443, mci: 0.115, blast: 19.0, ev: 73.0, signal: 'Top Target', flag: 'Power Flag',          sample: 'Small' },
  { rank: 10, name: 'Elly De La Cruz',pa: 122, pos: 'SS', fpos: 'SS',     proc: 125.2, procPos: 127.7, kavoid: 109.2, power: 133.0, swing: 40.5, chase: 28.3, mc: 0.487, mci: 0.160, blast: 13.0, ev: 72.0, signal: 'Top Target', flag: 'Power Flag',          sample: 'Small' },
  { rank: 11, name: 'Junior Caminero',pa: 142, pos: '3B', fpos: '3B',     proc: 124.1, procPos: 122.3, kavoid: 102.1, power: 140.6, swing: 51.2, chase: 33.4, mc: 0.512, mci: 0.180, blast: 17.2, ev: 74.1, signal: 'Top Target', flag: 'Power Flag',          sample: 'Mid' },
  { rank: 12, name: 'Riley Greene',   pa: 156, pos: 'OF', fpos: 'OF',     proc: 122.8, procPos: 119.4, kavoid: 95.8, power: 138.7, swing: 47.1, chase: 30.1, mc: 0.498, mci: 0.220, blast: 16.4, ev: 73.2, signal: 'Top Target', flag: 'Power Flag',          sample: 'Mid' },
  { rank: 13, name: 'Pete Crow-Armstrong', pa: 167, pos: 'CF', fpos: 'OF', proc: 121.5, procPos: 115.2, kavoid: 108.2, power: 128.4, swing: 42.8, chase: 26.7, mc: 0.521, mci: 0.245, blast: 14.8, ev: 71.8, signal: 'Top Target', flag: '—',                  sample: 'Mid' },
  { rank: 14, name: 'Jackson Chourio',pa: 148, pos: 'OF', fpos: 'OF',     proc: 119.7, procPos: 116.8, kavoid: 101.5, power: 125.9, swing: 45.3, chase: 32.6, mc: 0.504, mci: 0.198, blast: 13.9, ev: 72.4, signal: 'Watch',      flag: '—',                  sample: 'Mid' },
  { rank: 15, name: 'Wyatt Langford', pa: 134, pos: 'OF', fpos: 'OF',     proc: 117.9, procPos: 114.3, kavoid: 99.7, power: 122.1, swing: 41.5, chase: 28.9, mc: 0.476, mci: 0.187, blast: 14.2, ev: 71.5, signal: 'Watch',      flag: '—',                  sample: 'Mid' },
];

// Mini sparkline data (12 weeks of process+ for each player)
window.SPARKS = window.HITTERS.reduce((acc, h) => {
  const base = h.proc;
  const spark = [];
  let v = base * 0.85;
  for (let i = 0; i < 12; i++) {
    v += (Math.sin(i * 0.7 + h.rank) * 6) + (Math.random() - 0.5) * 4 + (i * 0.5);
    spark.push(Math.max(70, Math.min(170, v)));
  }
  acc[h.name] = spark;
  return acc;
}, {});

// Distribution data for component charts
window.DISTRIBUTIONS = {
  proc:   { mean: 89.9,  bins: [2,4,8,12,18,24,28,30,28,22,16,11,8,5,3,2,1] },
  kavoid: { mean: 106.2, bins: [1,2,4,8,14,20,26,30,28,22,16,10,6,3,2,1] },
  power:  { mean: 99.6,  bins: [2,5,10,16,22,28,30,28,24,18,12,7,4,2,1] },
  swing:  { mean: 0.5,   bins: [1,3,6,12,20,28,30,26,18,10,5,2,1] },
};
