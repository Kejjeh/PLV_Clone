// Shared utilities used across all variations
const fmt = (n, d = 1) => {
  if (n === '—' || n == null) return '—';
  if (typeof n !== 'number') return n;
  return n.toFixed(d);
};

const pct = (n) => typeof n === 'number' ? `${n.toFixed(1)}%` : n;

// Map a value within [min,max] to a heatmap color (cool→warm)
const heat = (v, min, max, dark = false) => {
  if (typeof v !== 'number') return 'transparent';
  const t = Math.max(0, Math.min(1, (v - min) / (max - min)));
  // Diverging blue → neutral → orange
  if (t < 0.5) {
    const k = t * 2; // 0..1
    return dark
      ? `oklch(${0.30 + k * 0.05} ${0.06 - k * 0.05} 240)`
      : `oklch(${0.95 - k * 0.05} ${0.06 - k * 0.05} 240)`;
  } else {
    const k = (t - 0.5) * 2;
    return dark
      ? `oklch(${0.32 + k * 0.10} ${0.04 + k * 0.12} 50)`
      : `oklch(${0.92 - k * 0.10} ${0.04 + k * 0.12} 50)`;
  }
};

// Inline sparkline
function Sparkline({ data, width = 60, height = 20, color = 'currentColor', strokeWidth = 1.2, fill = false }) {
  if (!data || data.length === 0) return null;
  const min = Math.min(...data);
  const max = Math.max(...data);
  const range = max - min || 1;
  const step = width / (data.length - 1);
  const pts = data.map((v, i) => `${i * step},${height - ((v - min) / range) * height}`).join(' ');
  const last = data[data.length - 1];
  const lastY = height - ((last - min) / range) * height;
  const trend = data[data.length - 1] - data[Math.max(0, data.length - 4)];
  const lineColor = trend > 2 ? 'var(--pos)' : trend < -2 ? 'var(--neg)' : color;
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} style={{ display: 'block', overflow: 'visible' }}>
      {fill && (
        <polygon
          points={`0,${height} ${pts} ${width},${height}`}
          fill={lineColor}
          opacity={0.15}
        />
      )}
      <polyline points={pts} fill="none" stroke={lineColor} strokeWidth={strokeWidth} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={width} cy={lastY} r={1.6} fill={lineColor} />
    </svg>
  );
}

// Histogram for component distributions (with optional highlighted player)
function Histogram({ bins, mean, label, highlightPct, color = 'currentColor', height = 60, width = 200 }) {
  const max = Math.max(...bins);
  const bw = width / bins.length;
  return (
    <svg width={width} height={height + 24} viewBox={`0 0 ${width} ${height + 24}`} style={{ display: 'block' }}>
      <text x={width / 2} y={11} textAnchor="middle" fontSize="9" fill="currentColor" opacity="0.65" style={{ fontFamily: 'inherit' }}>
        {label} · μ={mean}
      </text>
      {bins.map((v, i) => {
        const h = (v / max) * height;
        const isHighlight = highlightPct != null && Math.abs((i / bins.length) - highlightPct) < (1 / bins.length / 1.5);
        return (
          <rect
            key={i}
            x={i * bw + 0.5}
            y={height - h + 16}
            width={bw - 1}
            height={h}
            fill={isHighlight ? 'var(--accent)' : color}
            opacity={isHighlight ? 1 : 0.55}
          />
        );
      })}
    </svg>
  );
}

Object.assign(window, { fmt, pct, heat, Sparkline, Histogram });
