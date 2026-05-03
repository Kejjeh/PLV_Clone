# Full Build Prompt — Process Report: Complete Interactive Dashboard
# Replace the contents of ONE_SHOT_PROMPT.md with this for the full version.

Paste this entire prompt into VS Code / Cursor to rebuild both files with full interactivity and all six tabs.

---

## What to build

Two files, replacing the current versions:

1. **`app/reports/process_report_template.html`** — a fully interactive single-page React + Babel dashboard. All six navigation tabs work. Sorting, filtering, search, presets, CSV export, compare panel, trends charts — everything is live. Works from `file://` in Chrome with zero server.

2. **`scripts/generate_report.py`** — expands the existing script to inject all data globals needed by all six tabs.

---

## Reference files — read all of these first

```
app/reports/source/variant-editorial-dense.jsx   ← visual spec (Variation E)
app/reports/source/shared.jsx                    ← Sparkline + Histogram components
app/reports/source/data.js                       ← data contract / field names
app/reports/process_report_template.html         ← current template (starting point)
scripts/generate_report.py                       ← current generator (starting point)
```

---

## Data globals — what the generator injects, what the app reads

```js
window.REPORT_META   // string: "Vol. II · No. 26 · Early Season · Build {sha}"
window.HITTERS       // array of hitter objects (top 50 by proc+, pa>=40, proc+>=95)
window.SPARKS        // { "Player Name": [float×12] }  12-week trajectories
window.DISTRIBUTIONS // { proc, kavoid, power, swing } histogram data
window.PITCHERS      // array of pitcher objects (all qualified, sorted by plv desc)
window.TARGETS       // { buy: [], preBreakout: [], breakout: [] }
window.ROLLING       // { "Player Name": [{date, score}, ...] }  daily rolling for Trends
window.WAIVER        // array — subset of HITTERS where signal=="Watch" or sample in ["Too Small","Small"]
```

---

## App structure

```jsx
function App() {
  const [dark, setDark] = React.useState(false);
  const [tab, setTab] = React.useState('hitters');
  const [pinned, setPinned] = React.useState(
    window.HITTERS.slice(0,2).map(h => h.name)
  );

  return (
    <div style={{ position: 'relative', minHeight: '100vh' }}>
      <ThemeToggle dark={dark} setDark={setDark} />
      <VariantEditorialDense
        dark={dark}
        activeTab={tab}
        setActiveTab={setTab}
        pinned={pinned}
        setPinned={setPinned}
      />
    </div>
  );
}
```

The `VariantEditorialDense` component owns all tab routing. The masthead, section nav, and watchlist strip are always visible. Only the main content area below the filters strip changes per tab.

---

## Section nav — all tabs wired

```jsx
const TABS = ['hitters','pitchers','targets','trends','waiver','my-team'];
const TAB_LABELS = { hitters:'Hitters', pitchers:'Pitchers', targets:'Targets',
                     trends:'Trends', waiver:'Waiver', 'my-team':'My Team' };

// In the section nav <div>:
{TABS.map(t => (
  <span key={t}
    onClick={() => setActiveTab(t)}
    style={{
      color: activeTab === t ? colors.text : colors.dim,
      fontWeight: activeTab === t ? 600 : 400,
      cursor: 'pointer',
      borderBottom: activeTab === t ? `2px solid ${colors.accent}` : 'none',
      paddingBottom: 4, marginBottom: -11,
    }}>
    {TAB_LABELS[t]}
  </span>
))}
```

---

## Presets — wired to filter state

Presets live in the section nav right side. Each preset is a named filter combination. Clicking a preset sets all filter state atoms at once and switches to the correct tab.

```js
const PRESETS = [
  {
    label: 'My OF Targets',
    apply: () => { setActiveTab('hitters'); setPosFlt(['OF']); setMinProc(110); setMinPa(40); setSearch(''); }
  },
  {
    label: 'Catchers',
    apply: () => { setActiveTab('hitters'); setPosFlt(['C']); setMinProc(95); setMinPa(40); setSearch(''); }
  },
  {
    label: 'Power+ > 130',
    apply: () => { setActiveTab('hitters'); setPosFlt([]); setMinProc(95); setMinPa(40); setPowerFlt(130); setSearch(''); }
  },
];

// Render:
{PRESETS.map((p, i) => (
  <span key={p.label}
    onClick={p.apply}
    style={{
      color: i === 0 ? colors.accent : colors.dim, cursor: 'pointer',
      borderBottom: i === 0 ? `1px solid ${colors.accent}` : 'none', paddingBottom: 2,
    }}>
    {p.label}
  </span>
))}
<span style={{ color: colors.dim, cursor: 'pointer' }}>+ New</span>
```

---

## HITTERS TAB — full interactivity

### Filter state (all inside VariantEditorialDense)

```js
const [search, setSearch]     = React.useState('');
const [posFlt, setPosFlt]     = React.useState([]);      // [] = All
const [minPa, setMinPa]       = React.useState(40);
const [minProc, setMinProc]   = React.useState(95);
const [powerFlt, setPowerFlt] = React.useState(0);       // 0 = no filter
const [sortCol, setSortCol]   = React.useState('proc');
const [sortDir, setSortDir]   = React.useState('desc');  // 'asc' | 'desc'
const [rowLimit, setRowLimit] = React.useState(50);
const [selected, setSelected] = React.useState(window.HITTERS[0]?.name || '');
const [expanded, setExpanded] = React.useState(null);
const [compareOpen, setCompareOpen] = React.useState(false);
```

### Derived filtered + sorted rows

```js
const filteredHitters = React.useMemo(() => {
  let rows = window.HITTERS.filter(h => {
    if (search && !h.name.toLowerCase().includes(search.toLowerCase())) return false;
    if (h.pa < minPa) return false;
    if (h.proc < minProc) return false;
    if (powerFlt > 0 && h.power < powerFlt) return false;
    if (posFlt.length > 0) {
      // match primary pos OR any fpos token
      const fposTokens = (h.fpos || '').split(/[,\s]+/).map(t => t.trim()).filter(Boolean);
      const allPos = [h.pos, ...fposTokens];
      if (!posFlt.some(p => allPos.includes(p))) return false;
    }
    return true;
  });

  rows = [...rows].sort((a, b) => {
    const av = a[sortCol] ?? -Infinity;
    const bv = b[sortCol] ?? -Infinity;
    if (typeof av === 'string') return sortDir === 'asc' ? av.localeCompare(bv) : bv.localeCompare(av);
    return sortDir === 'asc' ? av - bv : bv - av;
  });

  return rows.slice(0, rowLimit);
}, [search, posFlt, minPa, minProc, powerFlt, sortCol, sortDir, rowLimit]);
```

### Sortable column headers

```jsx
function SortTh({ col, label, align = 'r', width, sortCol, sortDir, onSort }) {
  const active = sortCol === col;
  return (
    <th onClick={() => onSort(col)}
      style={{
        textAlign: align === 'l' ? 'left' : 'right',
        padding: '8px 8px', fontSize: 9, fontWeight: 600,
        letterSpacing: 1.5, textTransform: 'uppercase',
        fontFamily: mono, whiteSpace: 'nowrap', minWidth: width,
        cursor: 'pointer',
        color: active ? colors.accent : colors.dim,
        userSelect: 'none',
      }}>
      {label}{active ? (sortDir === 'desc' ? ' ↓' : ' ↑') : ''}
    </th>
  );
}

function handleSort(col) {
  if (sortCol === col) setSortDir(d => d === 'desc' ? 'asc' : 'desc');
  else { setSortCol(col); setSortDir('desc'); }
}
```

Apply `onSort={handleSort}` and pass `sortCol`/`sortDir` to every `SortTh`. Use `col` values matching the `window.HITTERS` field names: `proc`, `procPos`, `kavoid`, `power`, `swing`, `chase`, `mc`, `mci`, `blast`, `ev`, `pa`, `name`.

### Filters strip — live controls

Replace the static spans with real inputs styled to match the editorial look:

```jsx
// Position filter — pill chips
const POS_OPTIONS = ['C','1B','2B','3B','SS','OF','DH'];

<div style={{ display:'flex', gap:4 }}>
  {['All', ...POS_OPTIONS].map(p => {
    const active = p === 'All' ? posFlt.length === 0 : posFlt.includes(p);
    return (
      <span key={p} onClick={() => {
        if (p === 'All') setPosFlt([]);
        else setPosFlt(prev => prev.includes(p) ? prev.filter(x=>x!==p) : [...prev,p]);
      }} style={{
        padding: '2px 7px', borderRadius: 2, cursor: 'pointer', fontSize: 10,
        fontFamily: mono, letterSpacing: 1, textTransform: 'uppercase',
        border: `1px solid ${active ? colors.accent : colors.border}`,
        color: active ? colors.accent : colors.dim,
        background: active ? `${colors.accent}18` : 'transparent',
      }}>{p}</span>
    );
  })}
</div>

// Min PA
<label style={{ color:colors.dim, fontFamily:mono, fontSize:10, letterSpacing:1.5, textTransform:'uppercase', display:'flex', alignItems:'center', gap:6 }}>
  Min PA
  <input type="number" value={minPa} onChange={e=>setMinPa(+e.target.value||0)}
    style={{ width:48, padding:'2px 6px', border:`1px solid ${colors.border}`, borderRadius:2,
             background:colors.panel, color:colors.accent, fontFamily:mono, fontSize:11, textAlign:'right' }} />
</label>

// Min Proc+  (same pattern, uses minProc / setMinProc)

// Power+ min  (uses powerFlt / setPowerFlt, label "Min Pwr+")

// Rows
<label style={{ color:colors.dim, fontFamily:mono, fontSize:10, letterSpacing:1.5, textTransform:'uppercase', display:'flex', alignItems:'center', gap:6 }}>
  Rows
  <select value={rowLimit} onChange={e=>setRowLimit(+e.target.value)}
    style={{ padding:'2px 4px', border:`1px solid ${colors.border}`, borderRadius:2,
             background:colors.panel, color:colors.accent, fontFamily:mono, fontSize:11 }}>
    {[25,50,100,999].map(n=><option key={n} value={n}>{n===999?'All':n}</option>)}
  </select>
</label>

// Live count (right side)
<span style={{ color:colors.dim }}>{filteredHitters.length} / {window.HITTERS.length} hitters</span>
```

### Search — wire to masthead input

```jsx
<input
  placeholder="search players..."
  value={search}
  onChange={e => setSearch(e.target.value)}
  style={{ ... /* existing masthead input styles */ }}
/>
```

### CSV export button

```jsx
function exportCSV(rows) {
  const cols = ['rank','name','pa','pos','fpos','proc','procPos','kavoid','power',
                'swing','chase','mc','mci','blast','ev','signal','flag','sample'];
  const header = cols.join(',');
  const body = rows.map(r => cols.map(c => {
    const v = r[c];
    if (v == null || v === '—') return '';
    if (typeof v === 'string' && v.includes(',')) return `"${v}"`;
    return v;
  }).join(',')).join('\n');
  const blob = new Blob([header + '\n' + body], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = 'process_report.csv'; a.click();
  URL.revokeObjectURL(url);
}

// CSV button in masthead:
<button onClick={() => exportCSV(filteredHitters)} style={editorialBtn(colors, mono)}>CSV</button>
```

### Compare panel

The COMPARE button shows the count of pinned players. Clicking it opens a panel below the masthead (not a modal — inline, full-width) showing pinned players side by side.

```jsx
{compareOpen && pinned.length > 0 && (
  <div style={{ padding:'16px 32px', background:colors.stripe, borderBottom:`1px solid ${colors.border}` }}>
    <div style={{ display:'grid', gridTemplateColumns:`repeat(${pinned.length}, 1fr)`, gap:24 }}>
      {pinned.map(name => {
        const h = window.HITTERS.find(x => x.name === name);
        if (!h) return null;
        return (
          <div key={name} style={{ borderTop:`2px solid ${colors.accent}`, paddingTop:10 }}>
            <div style={{ fontStyle:'italic', fontFamily:serif, fontSize:18, color:colors.text }}>{h.name}</div>
            <div style={{ fontFamily:mono, fontSize:10, color:colors.dim, marginTop:4 }}>{h.pos} · {h.pa} PA · {h.sample}</div>
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:'6px 16px', marginTop:12 }}>
              {[['Proc+',h.proc],['ProcPos',h.procPos],['K-Avd+',h.kavoid],['Power+',h.power],
                ['Swing%',h.swing],['Chase%',h.chase],['Blast',h.blast],['EV',h.ev]].map(([lbl,val])=>(
                <div key={lbl}>
                  <div style={{ fontSize:9, letterSpacing:2, color:colors.dim, fontFamily:mono, textTransform:'uppercase' }}>{lbl}</div>
                  <div style={{ fontSize:16, fontStyle:'italic', fontFamily:serif, color:colors.accent }}>
                    {typeof val==='number' ? val.toFixed(1) : (val||'—')}
                  </div>
                </div>
              ))}
            </div>
            <div style={{ marginTop:8 }}>
              <Sparkline data={window.SPARKS[h.name]} width={200} height={32} color={colors.accent} fill strokeWidth={1.4} />
            </div>
          </div>
        );
      })}
    </div>
  </div>
)}
```

COMPARE button:
```jsx
<button onClick={() => setCompareOpen(o => !o)} style={editorialBtn(colors, mono)}>
  COMPARE · {pinned.length}
</button>
```

---

## PITCHERS TAB

Data: `window.PITCHERS` — array of objects with these fields (mapped by generator):
```js
{ rank, name, pitches, plv, plvStd, swing, whiff, cs, xwoba, contact, pctile }
```

Render a sortable table with the same editorial style as the Hitters table. Columns:
`Rk | Player | Pitches | PLV | Std | Swing% | Whiff% | CS% | xwOBA | Contact% | Pctile`

- PLV column: large italic serif, accented, heatmap tinted (range 4.5–6.0 = editorialHeat)
- Pctile: shown as e.g. `99.8` with rust tinting (range 0–100)
- Same click-to-select, double-click expand (expand shows: PLV vs league histogram, whiff vs swing scatter note, "Top pitches" placeholder)
- Same sort/filter strip: Min Pitches (default 100), Search, Sort, Rows

Section heading: `§ I  The Pitching Leaderboard` / `RANKED BY PLV`

No separate lede for pitchers — just the § I heading + table.

---

## TARGETS TAB

Data: `window.TARGETS = { buy: [], preBreakout: [], breakout: [] }`

Each array contains objects: `{ name, pa, pos, fposDisplay, proc, power, kavoid, confidence, rollingTrend, tag }`

Render three stacked boards. Each board has:
- § heading: `§ I  Buy Targets` / `§ II  Pre-Breakout` / `§ III  Breakout Flags`
- A card grid (3 columns) where each card has `borderTop: 1px solid colors.faint` (same callout box style as the lede):
  - Player name (italic serif, 20px, accent color)
  - Pos · PA · Confidence chip
  - Proc+ (large), Power+, K-Avd+ (smaller mono)
  - Rolling trend badge: `hot` = pos color, `warm` = warn color, `cold` = neg color
  - Tag line (italic, dim, 11px, capped at 120 chars)

```jsx
function TargetCard({ h, colors, serif, mono }) {
  const trendColor = h.rollingTrend === 'hot' ? colors.pos : h.rollingTrend === 'warm' ? colors.warn : colors.dim;
  return (
    <div style={{ borderTop:`1px solid ${colors.faint}`, paddingTop:10 }}>
      <div style={{ display:'flex', justifyContent:'space-between', alignItems:'flex-start' }}>
        <div style={{ fontStyle:'italic', fontFamily:serif, fontSize:20, color:colors.accent, lineHeight:1.1 }}>{h.name}</div>
        <span style={{ fontFamily:mono, fontSize:9, color:trendColor, textTransform:'uppercase', letterSpacing:1, paddingTop:4 }}>
          ● {h.rollingTrend || '—'}
        </span>
      </div>
      <div style={{ fontFamily:mono, fontSize:10, color:colors.dim, marginTop:3 }}>
        {h.pos} · {h.pa} PA · <span style={{ color: h.confidence==='Signal' ? colors.pos : colors.warn }}>{h.confidence}</span>
      </div>
      <div style={{ display:'flex', gap:16, marginTop:8 }}>
        {[['Proc+', h.proc], ['Power+', h.power], ['K-Avd+', h.kavoid]].map(([l,v]) => (
          <div key={l}>
            <div style={{ fontSize:8, letterSpacing:2, color:colors.dim, fontFamily:mono, textTransform:'uppercase' }}>{l}</div>
            <div style={{ fontSize:18, fontStyle:'italic', fontFamily:serif, color:colors.text }}>{typeof v==='number'?v.toFixed(1):'—'}</div>
          </div>
        ))}
      </div>
      {h.tag && <div style={{ fontSize:11, fontStyle:'italic', color:colors.dim, marginTop:8, lineHeight:1.4 }}>
        {h.tag.substring(0, 120)}{h.tag.length > 120 ? '…' : ''}
      </div>}
    </div>
  );
}
```

---

## TRENDS TAB

Data: `window.ROLLING = { "Player Name": [{date:"2026-03-22", score:142.1}, ...] }`

The Trends tab lets you view rolling Process+ trajectory for one or more players.

### State
```js
const [trendPlayers, setTrendPlayers] = React.useState(
  window.HITTERS.slice(0,3).map(h=>h.name)
);
const [trendSearch, setTrendSearch] = React.useState('');
```

### Layout
- Left column (280px): player selector — search input + list of all HITTERS names; clicking adds/removes from `trendPlayers` (max 5). Active players shown with accent bullet.
- Right column (flex 1): SVG line chart showing rolling score over time for all selected players.

### SVG line chart (build this inline — no Chart.js needed)

```jsx
function TrendChart({ players, colors, serif, mono }) {
  const W = 680, H = 220, PAD = { top:16, right:16, bottom:36, left:44 };
  const cw = W - PAD.left - PAD.right;
  const ch = H - PAD.top - PAD.bottom;

  // Gather all dates across selected players
  const allDates = [...new Set(
    players.flatMap(name => (window.ROLLING[name] || []).map(r => r.date))
  )].sort();

  if (allDates.length === 0) return <div style={{color:colors.dim,fontFamily:mono,fontSize:11}}>No rolling data</div>;

  const xScale = i => PAD.left + (i / (allDates.length - 1)) * cw;
  const yMin = 70, yMax = 170;
  const yScale = v => PAD.top + ch - ((v - yMin) / (yMax - yMin)) * ch;

  const LINE_COLORS = [colors.accent, colors.pos, '#6b9fd4', '#c17b3f', '#9b6bbf'];

  return (
    <svg width={W} height={H} viewBox={`0 0 ${W} ${H}`} style={{ display:'block' }}>
      {/* Y axis gridlines at 80, 100, 120, 140, 160 */}
      {[80,100,120,140,160].map(v => (
        <g key={v}>
          <line x1={PAD.left} x2={W-PAD.right} y1={yScale(v)} y2={yScale(v)}
            stroke={colors.faint} strokeWidth={1} />
          <text x={PAD.left-6} y={yScale(v)+4} textAnchor="end" fontSize={9}
            fill={colors.dim} fontFamily={mono}>{v}</text>
        </g>
      ))}
      {/* Reference line at 100 */}
      <line x1={PAD.left} x2={W-PAD.right} y1={yScale(100)} y2={yScale(100)}
        stroke={colors.dim} strokeWidth={1} strokeDasharray="3 3" />

      {/* Player lines */}
      {players.map((name, pi) => {
        const data = (window.ROLLING[name] || []).sort((a,b)=>a.date.localeCompare(b.date));
        if (!data.length) return null;
        const pts = data.map(r => {
          const xi = allDates.indexOf(r.date);
          return `${xScale(xi)},${yScale(Math.max(yMin, Math.min(yMax, r.score)))}`;
        }).join(' ');
        const lc = LINE_COLORS[pi % LINE_COLORS.length];
        const last = data[data.length-1];
        const lxi = allDates.indexOf(last.date);
        return (
          <g key={name}>
            <polyline points={pts} fill="none" stroke={lc} strokeWidth={1.8}
              strokeLinejoin="round" strokeLinecap="round" />
            <circle cx={xScale(lxi)} cy={yScale(Math.max(yMin,Math.min(yMax,last.score)))} r={3} fill={lc} />
            <text x={xScale(lxi)+6} y={yScale(Math.max(yMin,Math.min(yMax,last.score)))+4}
              fontSize={9} fill={lc} fontFamily={mono}>{name.split(' ').pop()}</text>
          </g>
        );
      })}

      {/* X axis — show first date of each week */}
      {allDates.filter((_,i) => i % 7 === 0).map(d => {
        const i = allDates.indexOf(d);
        return (
          <text key={d} x={xScale(i)} y={H-PAD.bottom+14} textAnchor="middle"
            fontSize={8} fill={colors.dim} fontFamily={mono}>
            {d.slice(5)}
          </text>
        );
      })}
    </svg>
  );
}
```

Section heading: `§ I  Rolling Trajectories` / `30-DAY PROCESS+ TREND`

---

## WAIVER TAB

Data: `window.WAIVER` (subset of HITTERS, pre-filtered by generator: signal in ["Watch","Too Small"] OR sample in ["Too Small","Small"])

Render the same table as the Hitters tab but with:
- No min proc+ filter (show lower-threshold players)
- A "Waiver Angle" column replacing Risk: show `sample` value in warn color if "Too Small", pos color if proc > 115
- Section heading: `§ I  Waiver Wire` / `RANKED BY PROCESS+`
- Brief lede note (static): *"Players with strong underlying process not yet reflected in results or ownership. Weight by sample tier."*

Reuse the same table component — just pass `window.WAIVER` instead of `filteredHitters` and swap the last column header/content.

---

## MY TEAM TAB

Shows the watchlist (pinned players) in a full stat table, same as Hitters.

```jsx
const myTeamRows = pinned
  .map(name => window.HITTERS.find(h => h.name === name))
  .filter(Boolean);
```

- If `myTeamRows.length === 0`: show a centered placeholder: *"Pin players using ★ in the Hitters tab to build your team view."*
- Otherwise: same table as Hitters, no filter strip, no presets.
- Section heading: `§ I  My Team` / `WATCHLIST`
- Add a "+ Add Players" link below the table that switches to the Hitters tab.

---

## Generator script additions (`scripts/generate_report.py`)

### Add `window.PITCHERS`

Source: `data/outputs/master_pitcher_{year}.csv`

```python
def build_pitchers(df: pd.DataFrame) -> list[dict]:
    # Filter: pitches >= 100
    qualified = df[df['pitches'] >= 100].copy()
    qualified = qualified.sort_values('plv', ascending=False).reset_index(drop=True)
    result = []
    for i, row in qualified.iterrows():
        result.append({
            'rank': len(result) + 1,
            'name': row['player_name'],
            'pitches': int(row['pitches']),
            'plv': round(float(row['plv']), 3),
            'plvStd': round(float(row['plv_std']), 3) if pd.notna(row.get('plv_std')) else '—',
            'swing': round(float(row['swing_pct']) * 100, 1) if pd.notna(row.get('swing_pct')) else '—',
            'whiff': round(float(row['whiff_pct']) * 100, 1) if pd.notna(row.get('whiff_pct')) else '—',
            'cs': round(float(row['cs_pct']) * 100, 1) if pd.notna(row.get('cs_pct')) else '—',
            'xwoba': round(float(row['xwoba_model']), 3) if pd.notna(row.get('xwoba_model')) else '—',
            'contact': round(float(row['contact_pct']) * 100, 1) if pd.notna(row.get('contact_pct')) else '—',
            'pctile': round(float(row['plv_pctile']), 1) if pd.notna(row.get('plv_pctile')) else '—',
        })
    return result
```

### Add `window.TARGETS`

Source: `hitter_buy_targets_{year}.csv`, `hitter_pre_breakout_{year}.csv`, `hitter_breakout_flags_{year}.csv`

```python
def build_targets(year: int) -> dict:
    def load_target_csv(path: str) -> list[dict]:
        if not os.path.exists(path):
            return []
        df = pd.read_csv(path)
        result = []
        for _, row in df.iterrows():
            result.append({
                'name': row['batter_name'],
                'pa': int(row['pa']) if pd.notna(row.get('pa')) else 0,
                'pos': row.get('primary_position', '—'),
                'fposDisplay': row.get('fantasy_positions_display') or '—',
                'proc': round(float(row['process_plus']), 1) if pd.notna(row.get('process_plus')) else '—',
                'power': round(float(row['power_plus']), 1) if pd.notna(row.get('power_plus')) else '—',
                'kavoid': round(float(row['decision_plus']), 1) if pd.notna(row.get('decision_plus')) else '—',
                'confidence': row.get('confidence', '—'),
                'rollingTrend': row.get('rolling_trend', '—'),
                'tag': str(row.get('tag', '') or '').strip(),
            })
        return result

    base = f'data/outputs'
    return {
        'buy': load_target_csv(f'{base}/hitter_buy_targets_{year}.csv'),
        'preBreakout': load_target_csv(f'{base}/hitter_pre_breakout_{year}.csv'),
        'breakout': load_target_csv(f'{base}/hitter_breakout_flags_{year}.csv'),
    }
```

### Add `window.ROLLING`

Source: `process_plus_rolling_{year}.csv`

```python
def build_rolling(rolling_df: pd.DataFrame, hitters: list[dict]) -> dict:
    """
    Per player in hitters list: sort rolling data by date, compute
    weekly_score = contact_value_mean + power_value_mean, normalize to
    approximate Process+ scale, return list of {date, score} dicts.
    """
    result = {}
    for h in hitters:
        name = h['name']
        player_rows = rolling_df[rolling_df['batter_name'] == name].copy()
        if player_rows.empty:
            continue
        player_rows = player_rows.sort_values('date')
        # compute raw score
        player_rows['raw'] = player_rows['contact_value_mean'] + player_rows['power_value_mean']
        raw = player_rows['raw'].values
        dates = player_rows['date'].values
        # normalize to Process+ scale using z-score
        mu, sigma = raw.mean(), raw.std()
        if sigma > 0:
            scaled = ((raw - mu) / sigma) * 15 + h['proc']
        else:
            scaled = [h['proc']] * len(raw)
        clipped = [max(70.0, min(170.0, float(v))) for v in scaled]
        result[name] = [{'date': str(d), 'score': round(s, 1)} for d, s in zip(dates, clipped)]
    return result
```

### Add `window.WAIVER`

```python
def build_waiver(hitters: list[dict]) -> list[dict]:
    return [h for h in hitters
            if h.get('signal') in ('Watch', 'Too Small')
            or h.get('sample') in ('Too Small', 'Small')]
```

### Updated injection block

Replace the single data script injection with:

```python
data_script = f"""<script>
window.REPORT_META = {json.dumps(report_meta)};
window.HITTERS = {json.dumps(hitters, indent=2)};
window.SPARKS = {json.dumps(sparks, indent=2)};
window.DISTRIBUTIONS = {json.dumps(distributions, indent=2)};
window.PITCHERS = {json.dumps(pitchers, indent=2)};
window.TARGETS = {json.dumps(targets, indent=2)};
window.ROLLING = {json.dumps(rolling, indent=2)};
window.WAIVER = {json.dumps(waiver, indent=2)};
</script>"""
```

Build `report_meta`:
```python
import subprocess, datetime
try:
    sha = subprocess.check_output(['git','rev-parse','--short','HEAD'],
                                   cwd='.').decode().strip()
except Exception:
    sha = 'local'
today = datetime.date.today()
week_num = today.isocalendar()[1]
report_meta = f"Vol. II · No. {week_num} · Early Season · Build {sha}"
```

---

## Quality checklist

Before finishing, verify:

**Hitters tab**
- [ ] Column header click sorts; second click reverses; active column shows ↓ / ↑ in accent color
- [ ] Search input live-filters by name as you type
- [ ] Position pill chips filter correctly (multi-select; OF matches both fpos OF and pos OF)
- [ ] Min PA and Min Proc+ inputs update filter on change
- [ ] Power+ > 130 preset applies correctly — clears pos filter, shows power≥130 players only
- [ ] Catchers preset filters to pos=C
- [ ] My OF Targets preset switches tab + applies OF + proc≥110
- [ ] CSV button downloads a real .csv file of the current filtered rows
- [ ] COMPARE button opens/closes inline compare panel showing pinned players side by side
- [ ] Row count in filter strip shows filtered/total live
- [ ] Double-click expand shows sparkline + histogram + buttons
- [ ] ★ pin/unpin works; watchlist strip updates immediately

**Pitchers tab**
- [ ] Renders PLV leaderboard from window.PITCHERS
- [ ] Column sort works
- [ ] Min Pitches filter works
- [ ] PLV column shows heatmap tinting

**Targets tab**
- [ ] Three boards render with card grid
- [ ] hot/warm/cold trend badges colored correctly
- [ ] Tags truncated at 120 chars with ellipsis

**Trends tab**
- [ ] SVG line chart renders for default 3 players
- [ ] Clicking player in left list adds/removes them from chart
- [ ] Chart updates immediately on player selection change
- [ ] X-axis shows dates, Y-axis shows 70–170 range with gridlines at 80/100/120/140/160

**Waiver tab**
- [ ] Shows only Watch/small-sample players
- [ ] Table renders with same styling as Hitters

**My Team tab**
- [ ] Shows pinned players from watchlist
- [ ] Empty state message when no players pinned
- [ ] "+ Add Players" link switches to Hitters tab

**Global**
- [ ] Dark/Light toggle works on all tabs
- [ ] No JS errors in Chrome console when opened via file://
- [ ] All tabs accessible from section nav, active tab highlighted with accent underline
- [ ] All presets trigger correct tab switch + filter state

---

## What NOT to do

- No build system, no npm, no webpack. Single HTML file, Babel standalone, `file://` compatible.
- No localStorage. All state lives in React useState.
- No Chart.js or external charting library. Use the inline SVG TrendChart component specified above.
- Do not split into multiple files.
- Do not hardcode player names anywhere — always derive from window.HITTERS.
- Do not add a "My Team" backend — it is purely a filtered view of pinned players.
