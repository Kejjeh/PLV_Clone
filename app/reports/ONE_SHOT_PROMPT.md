# One-Shot Build Prompt — Process Report HTML + Generator

Paste this entire prompt into VS Code / Claude / Cursor to build both files in one pass.

---

## What to build

Two files:

1. **`app/reports/process_report_template.html`** — a self-contained React + Babel HTML file that renders the "Editorial Dense" (Variation E) dashboard exactly matching the Claude Design prototype. It reads data from `window.HITTERS`, `window.SPARKS`, and `window.DISTRIBUTIONS` which are injected by the generator script. It must work when opened via `file://` in Chrome with no server.

2. **`scripts/generate_report.py`** — reads the two CSV files below and outputs `data/outputs/process_report_{year}.html` (a copy of the template with the real data injected).

---

## Reference files — read all of these before writing anything

```
app/reports/source/variant-editorial-dense.jsx   ← the exact Variation E component to replicate
app/reports/source/shared.jsx                    ← Sparkline + Histogram SVG components to include inline
app/reports/source/data.js                       ← exact data contract / field names
```

**Read those three files in full. The HTML you produce must match `variant-editorial-dense.jsx` pixel-for-pixel.**

---

## Template HTML spec (`app/reports/process_report_template.html`)

### Head / CDN

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8" />
<title>The Process Report</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Source+Serif+4:ital,wght@0,400;0,500;0,600;1,400;1,500&display=swap" rel="stylesheet" />
<style>html,body{margin:0;padding:0;}*{box-sizing:border-box;}</style>
<!-- DATA INJECTION POINT — generator replaces this comment -->
<script>
// Placeholder — overwritten by generate_report.py
window.HITTERS = [];
window.SPARKS = {};
window.DISTRIBUTIONS = { proc:{mean:90,bins:[]}, kavoid:{mean:106,bins:[]}, power:{mean:100,bins:[]}, swing:{mean:42,bins:[]} };
</script>
<script src="https://unpkg.com/react@18.3.1/umd/react.development.js" crossorigin></script>
<script src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.development.js" crossorigin></script>
<script src="https://unpkg.com/@babel/standalone@7.29.0/babel.min.js" crossorigin></script>
</head>
<body>
<div id="root"></div>
<!-- ALL REACT CODE GOES IN ONE <script type="text/babel"> TAG BELOW -->
</body>
</html>
```

### React app structure (all inline in one `<script type="text/babel">` tag)

Combine the following in order into a single babel script tag:

1. **Shared utilities** — copy verbatim from `app/reports/source/shared.jsx`:
   - `fmt()`, `pct()`, `heat()` functions
   - `Sparkline` component
   - `Histogram` component

2. **`dataCell()` and `editorialBtn()` helper functions** — copy verbatim from `variant-editorial-dense.jsx` (bottom of file)

3. **`VariantEditorialDense` component** — copy verbatim from `variant-editorial-dense.jsx`. Keep EVERY detail:
   - Light/dark color tokens (`colors` object)
   - `editorialHeat()` function using oklch
   - Masthead with italic serif "The Process Report" + mono vol/issue line + search + CSV + COMPARE buttons
   - Section nav with preset links
   - Lede section: 2-col grid, spotlight text + 4 callout boxes with borderTop style (NOT box cards)
   - Watchlist (★ Following) + Filters strip
   - § I Leaderboard section heading with horizontal rule
   - Dense table: all 18 columns (Rk, Player, PA, Pos, FPos, Proc+, 12W sparkline, ProcPos, K-Avd+, Power+, Swg%, Chs%, MC, MCi, Blast, EV, Signal, Risk)
   - Click to select row, double-click to expand inline panel (12W trajectory + Process+ histogram + buttons)
   - § II "Where {lastName} stands" distribution section with 4 histograms
   - Font stacks: `"IBM Plex Mono"` for mono, `"Source Serif 4"` for serif

4. **Dark mode toggle** — above the masthead (not in sidebar). Add this ThemeToggle wrapper:

```jsx
function ThemeToggle({ dark, setDark }) {
  return (
    <div style={{
      position: 'fixed', top: 10, right: 14, zIndex: 100,
      display: 'flex', gap: 4, padding: 3, borderRadius: 6,
      background: 'rgba(255,255,255,0.85)', border: '1px solid rgba(0,0,0,.1)',
      fontFamily: 'monospace', fontSize: 11,
    }}>
      {['Light', 'Dark'].map((m, i) => {
        const active = dark === (i === 1);
        return (
          <button key={m} onClick={() => setDark(i === 1)} style={{
            padding: '3px 10px', borderRadius: 4, border: 'none', cursor: 'pointer',
            background: active ? '#1a1a1a' : 'transparent',
            color: active ? '#fff' : '#555', fontWeight: 500, fontSize: 11,
          }}>{m}</button>
        );
      })}
    </div>
  );
}

function App() {
  const [dark, setDark] = React.useState(false);
  return (
    <div style={{ position: 'relative', minHeight: '100vh' }}>
      <ThemeToggle dark={dark} setDark={setDark} />
      <VariantEditorialDense dark={dark} />
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(<App />);
```

### Dynamic lede (replace hardcoded "Dane Myers" text)

The lede headline and callouts should be driven by `window.HITTERS` data, not hardcoded. Use:

```js
// At top of VariantEditorialDense, after const sel = ...:
const leader = window.HITTERS[0] || {};          // rank 1 — Proc+ leader
const powerLeader = [...window.HITTERS].sort((a,b)=>b.power-a.power)[0] || {};
const kavoidLeader = [...window.HITTERS].sort((a,b)=>b.kavoid-a.kavoid)[0] || {};
// Hottest 7d: highest (last spark value - spark[8]) delta
const hottestPlayer = window.HITTERS.reduce((best, h) => {
  const spark = window.SPARKS[h.name] || [];
  if (spark.length < 2) return best;
  const delta = spark[spark.length-1] - spark[Math.max(0, spark.length-4)];
  return (!best || delta > best.delta) ? { ...h, delta } : best;
}, null) || {};
// Stealth: highest proc among sample === 'Too Small' or 'Small', procPos > proc
const stealth = window.HITTERS.find(h =>
  (h.sample === 'Too Small' || h.sample === 'Small') && h.procPos > h.proc
) || {};
```

Replace the lede `<h2>` content with:
```jsx
<h2 ...>
  <span style={{fontStyle:'italic'}}>{leader.name}</span> tops the early-season leaderboard at{' '}
  <span style={{color:colors.accent, fontVariantNumeric:'tabular-nums'}}>
    {typeof leader.proc === 'number' ? leader.proc.toFixed(1) : '—'}
  </span> Process+
</h2>
<p ...>
  Sample size remains {leader.sample === 'Too Small' ? 'very small' : 'small'} ({leader.pa} PA),
  but the underlying signal is strong: a {typeof leader.power === 'number' ? leader.power.toFixed(1) : '—'} Power+
  and a top-decile Process+ both flag{' '}
  {leader.name ? leader.name.split(' ').pop() : '—'} as a buy candidate.
  {leader.sample === 'Too Small' ? ' Weight against the small sample.' : ''}
</p>
```

Replace the 4 callout boxes array with:
```js
[
  { lbl: 'Power+ Leader', name: powerLeader.name ? powerLeader.name.split(' ').map(w=>w[0]+'.').join(' ') : '—', v: typeof powerLeader.power==='number' ? powerLeader.power.toFixed(1) : '—', delta: '+leader', spark: window.SPARKS[powerLeader.name], pos: true },
  { lbl: 'K-Avoidance', name: kavoidLeader.name ? kavoidLeader.name.split(' ').map(w=>w[0]+'.').join(' ') : '—', v: typeof kavoidLeader.kavoid==='number' ? kavoidLeader.kavoid.toFixed(1) : '—', delta: '+leader', spark: window.SPARKS[kavoidLeader.name], pos: true },
  { lbl: 'Hottest 7d', name: hottestPlayer.name ? hottestPlayer.name.split(' ').map(w=>w[0]+'.').join(' ') : '—', v: typeof hottestPlayer.delta==='number' ? `+${hottestPlayer.delta.toFixed(1)}` : '—', delta: 'proc+', spark: window.SPARKS[hottestPlayer.name], pos: true },
  { lbl: 'Stealth', name: stealth.name ? stealth.name.split(' ').map(w=>w[0]+'.').join(' ') : '—', v: typeof stealth.proc==='number' ? stealth.proc.toFixed(1) : '—', delta: stealth.sample || 'small N', spark: window.SPARKS[stealth.name], pos: false },
]
```

Replace the filters strip hardcoded counts with `{window.HITTERS.length} / —` for the row count display.

---

## Generator script spec (`scripts/generate_report.py`)

```python
#!/usr/bin/env python3
"""
Generate a standalone Process Report HTML file with real data injected.

Usage:
  python scripts/generate_report.py [--year 2026]

Output:
  data/outputs/process_report_{year}.html
"""
```

### CSV inputs

| File | Description |
|------|-------------|
| `data/outputs/master_hitter_{year}.csv` | One row per hitter, all metrics |
| `data/outputs/process_plus_rolling_{year}.csv` | Weekly rolling data per player |

### Column mappings: CSV → `window.HITTERS` field

| CSV column | JS field | Transform |
|------------|----------|-----------|
| `batter_name` | `name` | as-is |
| `pa` | `pa` | int |
| `primary_position` | `pos` | as-is |
| `fantasy_positions_display` | `fpos` | `"—"` if null/empty |
| `process_plus` | `proc` | float, 1 decimal |
| `proc_plus_positional` | `procPos` | float, 1 decimal |
| `k_avoidance_plus` | `kavoid` | float, 1 decimal |
| `power_plus` | `power` | float, 1 decimal |
| `swing_pct` | `swing` | `float * 100`, 1 decimal |
| `chase_pct` | `chase` | `float * 100`, 1 decimal |
| `xwoba_on_contact` | `mc` | float, 3 decimal; `"—"` if null |
| `xwoba_vs_expected` | `mci` | float, 3 decimal; `"—"` if null |
| `blast_rate` | `blast` | `float * 100`, 1 decimal; `"—"` if null |
| `avg_swing_speed` | `ev` | float, 1 decimal; `"—"` if null |
| `signal` | `signal` | as-is |
| `risk_flag` | `flag` | as-is; `"—"` if null/empty |
| `sample_tier` | `sample` | as-is |
| *(row index + 1)* | `rank` | int |

**Filtering:** include only rows where `pa >= 40` and `process_plus >= 95`. Sort by `process_plus` descending. Assign `rank` after sorting (1 = highest proc+). Take top 50.

### `window.SPARKS` — rolling 12-week trajectory

```python
# For each player in HITTERS:
# 1. Filter rolling CSV to that batter (match on batter_name)
# 2. Sort by date ascending
# 3. Compute weekly_score = contact_value_mean + power_value_mean  (raw proxy for proc trend)
# 4. Take last 12 rows; if fewer than 12, pad left with first available value
# 5. Normalize to approximate Process+ scale:
#    - Compute mean and std of weekly_score across all weeks for this player
#    - If std > 0: scaled = [(v - mean) / std * 15 + player_proc for v in weekly_score]
#    - Else: scaled = [player_proc] * 12
#    - Clip each value to [70, 170]
# Result: list of 12 floats

# Players with no rolling data: generate a flat line at their proc value
```

### `window.DISTRIBUTIONS` — league histograms

```python
# Use all players in master CSV with pa >= 40 (no proc+ filter for distributions)
# For each metric, compute a 17-bin histogram:
#   proc:   range 70–170  (bins of ~5.9 pts)
#   kavoid: range 60–140
#   power:  range 60–170
#   swing:  range 20–60   (in % units, i.e. swing_pct*100)
# bins: list of 17 ints (counts per bin)
# mean: float (league mean for qualified hitters, 1 decimal)

import numpy as np
def make_hist(values, lo, hi, n_bins=17):
    counts, _ = np.histogram(values, bins=n_bins, range=(lo, hi))
    return counts.tolist()
```

### Injection

```python
# Read template
with open('app/reports/process_report_template.html', 'r') as f:
    html = f.read()

# Build injection block
data_script = f"""<script>
window.HITTERS = {json.dumps(hitters, indent=2)};
window.SPARKS = {json.dumps(sparks, indent=2)};
window.DISTRIBUTIONS = {json.dumps(distributions, indent=2)};
</script>"""

# Replace the placeholder comment + placeholder script block
# The template has exactly this text to replace:
#   <!-- DATA INJECTION POINT — generator replaces this comment -->
#   <script>
#   // Placeholder — overwritten by generate_report.py
#   ...
#   </script>
import re
html = re.sub(
    r'<!-- DATA INJECTION POINT.*?</script>',
    data_script,
    html,
    flags=re.DOTALL
)

# Write output
out_path = f'data/outputs/process_report_{year}.html'
with open(out_path, 'w') as f:
    f.write(html)
print(f"Written: {out_path}")
```

---

## Quality checklist

Before finishing, verify:
- [ ] Opening `data/outputs/process_report_2026.html` in Chrome (`file://`) renders without JS errors
- [ ] Light/Dark toggle works (fixed top-right)
- [ ] All 18 table columns visible, no layout breaks
- [ ] Proc+ / ProcPos / K-Avd+ / Power+ cells show rust heatmap tinting (oklch)
- [ ] 12W sparkline column shows inline SVG polylines
- [ ] Double-clicking any row shows the expand panel with large sparkline + histogram
- [ ] § II histogram section updates when a row is clicked
- [ ] Signal column shows italic serif `" buy "` / `" watch "` etc.
- [ ] Risk column shows `⚑ Power Flag` chip with warn-color border (or `—`)
- [ ] Lede headline and 4 callout boxes are driven by real data (no hardcoded "Dane Myers")

---

## What NOT to do

- Do NOT use a build system, webpack, vite, or npm. The template must run from `file://` via Babel standalone only.
- Do NOT split into multiple files. The entire React app is one `<script type="text/babel">` block.
- Do NOT copy the design-canvas or multi-variant wrapper from `PLV Dashboard.html`. Build only Variation E.
- Do NOT use localStorage.
- Do NOT hardcode player names in the lede or callouts.
