// Variation E: Editorial Dense — D's serif/italic style, A's full column set, B's cleanliness
function VariantEditorialDense({ dark = false }) {
  const [selected, setSelected] = React.useState('Yordan Alvarez');
  const [pinned, setPinned] = React.useState(['Yordan Alvarez', 'James Wood']);
  const [hoverRow, setHoverRow] = React.useState(null);
  const [expanded, setExpanded] = React.useState(null);

  const colors = dark ? {
    bg: '#1a1815', panel: '#211e1a', stripe: '#1d1b17', border: '#34302a', text: '#f5f1ea',
    dim: '#8d8579', faint: '#3a352e', accent: '#d97757',
    pos: '#7fb069', neg: '#c1666b', warn: '#d4a945',
  } : {
    bg: '#f7f3ec', panel: '#fdfaf3', stripe: '#f3eee4', border: '#e3dccb', text: '#1a1815',
    dim: '#7a7261', faint: '#d4ccba', accent: '#a8421f',
    pos: '#56753f', neg: '#9d3540', warn: '#a8761f',
  };

  const sel = window.HITTERS.find(h => h.name === selected) || window.HITTERS[1];
  const mono = '"IBM Plex Mono", ui-monospace, monospace';
  const serif = '"Source Serif 4", "Source Serif Pro", "Iowan Old Style", Georgia, serif';

  // Editorial heatmap — uses warm rust tones rather than blue/orange
  const editorialHeat = (v, min, max) => {
    if (typeof v !== 'number') return 'transparent';
    const t = Math.max(0, Math.min(1, (v - min) / (max - min)));
    if (dark) {
      return t < 0.5
        ? `oklch(${0.22 + (1 - t * 2) * 0.02} 0 0 / 0)`
        : `oklch(0.55 ${0.04 + (t - 0.5) * 0.18} 35 / ${0.10 + (t - 0.5) * 0.40})`;
    }
    return t < 0.5
      ? `oklch(0.97 0 0 / 0)`
      : `oklch(0.65 ${0.04 + (t - 0.5) * 0.20} 35 / ${0.06 + (t - 0.5) * 0.30})`;
  };

  return (
    <div style={{
      '--bg': colors.bg, '--panel': colors.panel, '--border': colors.border,
      '--text': colors.text, '--dim': colors.dim, '--accent': colors.accent,
      '--pos': colors.pos, '--neg': colors.neg, '--hover': colors.stripe, '--selected': colors.panel,
      background: colors.bg, color: colors.text,
      fontFamily: serif, fontSize: 13, lineHeight: 1.5, height: '100%', overflow: 'auto',
    }}>
      {/* Masthead */}
      <div style={{ padding: '20px 32px 14px', borderBottom: `2px solid ${colors.text}`, display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 24 }}>
        <div>
          <div style={{ fontSize: 9, letterSpacing: 4, textTransform: 'uppercase', color: colors.dim, fontFamily: mono }}>Vol. II · No. 26 · Early Season · Build 76704</div>
          <h1 style={{ fontSize: 32, fontWeight: 400, margin: '2px 0 0', letterSpacing: -0.5, fontStyle: 'italic', whiteSpace: 'nowrap' }}>The Process Report</h1>
        </div>
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <div style={{ position: 'relative' }}>
            <input placeholder="search players..." style={{
              padding: '6px 10px 6px 26px', border: `1px solid ${colors.border}`, borderRadius: 2,
              background: colors.panel, color: colors.text, fontSize: 12, width: 180, outline: 'none',
              fontFamily: serif, fontStyle: 'italic',
            }} />
            <svg width="11" height="11" viewBox="0 0 11 11" fill="none" stroke={colors.dim} strokeWidth="1.5" style={{ position: 'absolute', left: 9, top: 9 }}>
              <circle cx="4.5" cy="4.5" r="3.5" /><path d="M7.5 7.5l2.5 2.5" strokeLinecap="round" />
            </svg>
          </div>
          <button style={editorialBtn(colors, mono)}>CSV</button>
          <button style={editorialBtn(colors, mono)}>COMPARE · {pinned.length}</button>
        </div>
      </div>

      {/* Section nav */}
      <div style={{ padding: '10px 32px', borderBottom: `1px solid ${colors.border}`, display: 'flex', gap: 24, fontSize: 10, letterSpacing: 2, textTransform: 'uppercase', fontFamily: mono, alignItems: 'center' }}>
        {[['Hitters', true], ['Pitchers'], ['Targets'], ['Trends'], ['Waiver'], ['My Team']].map(([t, active]) => (
          <span key={t} style={{ color: active ? colors.text : colors.dim, fontWeight: active ? 600 : 400, cursor: 'pointer', borderBottom: active ? `2px solid ${colors.accent}` : 'none', paddingBottom: 4, marginBottom: -11 }}>{t}</span>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ color: colors.dim }}>Presets:</span>
        {['My OF Targets', 'Catchers', 'Power+ &gt; 130', '+ New'].map((p, i) => (
          <span key={p} dangerouslySetInnerHTML={{__html: p}} style={{ color: i === 0 ? colors.accent : colors.dim, cursor: 'pointer', borderBottom: i === 0 ? `1px solid ${colors.accent}` : 'none', paddingBottom: 2 }} />
        ))}
      </div>

      {/* Hitter Spotlight lede + compact callouts */}
      <div style={{ padding: '20px 32px 18px', borderBottom: `1px solid ${colors.border}`, display: 'grid', gridTemplateColumns: '1.4fr 1fr', gap: 32 }}>
        <div>
          <div style={{ fontSize: 10, letterSpacing: 3, textTransform: 'uppercase', color: colors.accent, fontFamily: mono, marginBottom: 8 }}>Lede · Hitter Spotlight</div>
          <h2 style={{ fontSize: 26, fontWeight: 400, lineHeight: 1.15, margin: 0, letterSpacing: -0.5 }}>
            <span style={{ fontStyle: 'italic' }}>Dane Myers</span> tops the early-season leaderboard at <span style={{ color: colors.accent, fontVariantNumeric: 'tabular-nums' }}>147.3</span> Process+
          </h2>
          <p style={{ fontSize: 13, color: colors.dim, margin: '8px 0 0', fontStyle: 'italic', lineHeight: 1.5 }}>
            Sample size remains small (49 PA), but the underlying signal is strong: a 168.7 Power+ score and a top-decile Process+ both flag him as a buy candidate. Weight against the small sample.
          </p>
          <div style={{ display: 'flex', gap: 12, marginTop: 10, fontSize: 10, fontFamily: mono, color: colors.dim, textTransform: 'uppercase', letterSpacing: 1.2, alignItems: 'center', flexWrap: 'wrap' }}>
            <span>49 PA</span><span style={{ color: colors.faint }}>·</span><span>CF</span><span style={{ color: colors.faint }}>·</span><span>Power Flag</span><span style={{ color: colors.faint }}>·</span><span style={{ color: colors.accent, cursor: 'pointer' }}>Read full report →</span>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px 24px' }}>
        {[
          { lbl: 'Power+ Leader', name: 'D. Myers', v: '168.7', delta: '+8.1', spark: window.SPARKS['Dane Myers'], pos: true },
          { lbl: 'K-Avoidance', name: 'D. Dingler', v: '118.9', delta: '+3.2', spark: window.SPARKS['Dillon Dingler'], pos: true },
          { lbl: 'Hottest 7d', name: 'Y. Alvarez', v: '+14.6', delta: 'proc+', spark: window.SPARKS['Yordan Alvarez'], pos: true },
          { lbl: 'Stealth', name: 'D. Rushing', v: '142.4', delta: 'small N', spark: window.SPARKS['Dalton Rushing'], pos: false },
        ].map(c => (
          <div key={c.lbl} style={{ borderTop: `1px solid ${colors.faint}`, paddingTop: 6 }}>
            <div style={{ fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: colors.dim, fontFamily: mono }}>{c.lbl}</div>
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', marginTop: 4 }}>
              <div>
                <div style={{ fontSize: 20, fontFamily: serif, fontStyle: 'italic', color: colors.accent, letterSpacing: -0.5, lineHeight: 1 }}>{c.v}</div>
                <div style={{ fontSize: 11, marginTop: 4 }}>{c.name}</div>
                <div style={{ fontSize: 10, color: c.pos ? colors.pos : colors.warn, fontFamily: mono, letterSpacing: 0.5 }}>{c.delta}</div>
              </div>
              <Sparkline data={c.spark} width={40} height={20} color={colors.accent} fill strokeWidth={1.4} />
            </div>
          </div>
        ))}
        </div>
      </div>

      {/* Watchlist + filters bar */}
      <div style={{ padding: '12px 32px', borderBottom: `1px solid ${colors.border}`, display: 'flex', gap: 16, alignItems: 'center', flexWrap: 'wrap' }}>
        <span style={{ fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: colors.dim, fontFamily: mono }}>★ Following</span>
        {pinned.map(p => {
          const h = window.HITTERS.find(x => x.name === p);
          if (!h) return null;
          return (
            <span key={p} onClick={() => setSelected(p)} style={{
              display: 'inline-flex', gap: 8, alignItems: 'center', cursor: 'pointer',
              padding: '4px 10px', borderRadius: 2,
              background: selected === p ? colors.panel : 'transparent',
              border: `1px solid ${selected === p ? colors.accent : colors.border}`,
              whiteSpace: 'nowrap',
            }}>
              <span style={{ fontStyle: 'italic', fontSize: 13 }}>{p}</span>
              <span style={{ fontFamily: mono, fontSize: 10, color: colors.accent }}>{h.proc}</span>
              <span onClick={(e) => { e.stopPropagation(); setPinned(pinned.filter(x => x !== p)); }} style={{ color: colors.faint, fontSize: 12, lineHeight: 1 }}>×</span>
            </span>
          );
        })}
        <span style={{ padding: '4px 10px', border: `1px dashed ${colors.border}`, color: colors.dim, fontFamily: serif, fontStyle: 'italic', fontSize: 12, cursor: 'pointer', borderRadius: 2 }}>+ follow</span>
      </div>

      {/* Filters strip */}
      <div style={{ padding: '8px 32px', display: 'flex', gap: 20, alignItems: 'center', fontSize: 10, fontFamily: mono, textTransform: 'uppercase', letterSpacing: 1.5, borderBottom: `1px solid ${colors.border}`, background: colors.stripe }}>
        {[['Position', 'All'], ['Min PA', '40'], ['Min Proc+', '95'], ['Sort', 'Proc+ ↓'], ['Rows', '50']].map(([l, v]) => (
          <span key={l} style={{ color: colors.dim }}>{l} <span style={{ color: colors.accent, marginLeft: 4 }}>{v} ▾</span></span>
        ))}
        <div style={{ flex: 1 }} />
        <span style={{ color: colors.dim }}>50 / 2,040 hitters</span>
      </div>

      {/* Section heading */}
      <div style={{ padding: '20px 32px 10px', display: 'flex', alignItems: 'baseline', gap: 14 }}>
        <span style={{ fontSize: 10, letterSpacing: 3, textTransform: 'uppercase', color: colors.accent, fontFamily: mono, flexShrink: 0 }}>§ I</span>
        <h2 style={{ fontSize: 22, fontWeight: 400, margin: 0, fontStyle: 'italic', letterSpacing: -0.3, whiteSpace: 'nowrap', flexShrink: 0 }}>The Leaderboard</h2>
        <div style={{ flex: 1, borderBottom: `1px solid ${colors.border}`, marginBottom: 6, minWidth: 20 }} />
        <span style={{ fontSize: 10, color: colors.dim, fontFamily: mono, letterSpacing: 1, whiteSpace: 'nowrap', flexShrink: 0 }}>RANKED BY PROCESS+</span>
      </div>

      {/* Dense table — full A column set with editorial typography */}
      <div style={{ padding: '0 32px 24px' }}>
        <div style={{ overflow: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontVariantNumeric: 'tabular-nums' }}>
            <thead>
              <tr style={{ borderBottom: `2px solid ${colors.text}` }}>
                {[['Rk', 'l', 36], ['Player', 'l', 150], ['PA', 'r', 36], ['Pos', 'r', 36], ['FPos', 'r', 60],
                  ['Proc+', 'r', 56], ['12W', 'r', 64], ['ProcPos', 'r', 56], ['K-Avd+', 'r', 56], ['Power+', 'r', 56],
                  ['Swg%', 'r', 44], ['Chs%', 'r', 44], ['MC', 'r', 50], ['MCi', 'r', 50],
                  ['Blast', 'r', 44], ['EV', 'r', 40], ['Signal', 'r', 70], ['Risk', 'r', 90]].map(([h, a, w], i) => (
                  <th key={i} style={{
                    textAlign: a === 'l' ? 'left' : 'right', padding: '8px 8px',
                    fontSize: 9, color: colors.dim, fontWeight: 600, letterSpacing: 1.5, textTransform: 'uppercase',
                    fontFamily: mono, whiteSpace: 'nowrap', minWidth: w, width: i === 1 ? 150 : 'auto',
                    position: i === 1 ? 'sticky' : 'static', left: i === 1 ? 36 : 'auto',
                    background: colors.bg, zIndex: i === 1 ? 2 : 1,
                  }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {window.HITTERS.map((h, idx) => {
                const isSel = selected === h.name;
                const isHover = hoverRow === h.rank;
                const isExp = expanded === h.name;
                const rowBg = isSel ? colors.panel : isHover ? colors.stripe : 'transparent';
                return (
                  <React.Fragment key={h.rank}>
                  <tr
                    onClick={() => setSelected(h.name)}
                    onDoubleClick={() => setExpanded(isExp ? null : h.name)}
                    onMouseEnter={() => setHoverRow(h.rank)}
                    onMouseLeave={() => setHoverRow(null)}
                    style={{ borderBottom: `1px solid ${colors.faint}`, background: rowBg, cursor: 'pointer' }}>
                    <td style={{ padding: '7px 8px', fontSize: 16, fontFamily: serif, fontStyle: 'italic', color: idx < 3 ? colors.accent : colors.dim, width: 36, minWidth: 36 }}>{h.rank}</td>
                    <td style={{ padding: '7px 8px', position: 'sticky', left: 36, background: rowBg === 'transparent' ? colors.bg : rowBg, whiteSpace: 'nowrap', width: 150, minWidth: 150, maxWidth: 150, zIndex: 1 }}>
                      <span onClick={(e) => { e.stopPropagation(); setPinned(pinned.includes(h.name) ? pinned.filter(x => x !== h.name) : [...pinned, h.name]); }}
                        style={{ color: pinned.includes(h.name) ? colors.accent : colors.faint, marginRight: 6, cursor: 'pointer', fontSize: 11 }}>★</span>
                      <span style={{ fontSize: 14, fontWeight: 500 }}>{h.name}</span>
                    </td>
                    <td style={dataCell(colors, mono, h.pa < 100 ? colors.dim : colors.text)}>{h.pa}</td>
                    <td style={dataCell(colors, mono, colors.dim)}>{h.pos}</td>
                    <td style={{ ...dataCell(colors, mono, colors.dim), fontSize: 10 }}>{h.fpos}</td>
                    <td style={{ padding: '5px 8px', textAlign: 'right', background: editorialHeat(h.proc, 100, 150) }}>
                      <span style={{ fontSize: 18, fontFamily: serif, fontStyle: 'italic', color: colors.accent }}>{h.proc.toFixed(1)}</span>
                    </td>
                    <td style={{ padding: '5px 8px' }}>
                      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                        <Sparkline data={window.SPARKS[h.name]} width={56} height={16} color={colors.dim} strokeWidth={1.2} />
                      </div>
                    </td>
                    <td style={{ ...dataCell(colors, mono), background: editorialHeat(h.procPos, 100, 170) }}>{h.procPos.toFixed(1)}</td>
                    <td style={{ ...dataCell(colors, mono), background: editorialHeat(h.kavoid, 85, 130) }}>{h.kavoid.toFixed(1)}</td>
                    <td style={{ ...dataCell(colors, mono), background: editorialHeat(h.power, 120, 170) }}>{h.power.toFixed(1)}</td>
                    <td style={dataCell(colors, mono, colors.dim)}>{h.swing.toFixed(1)}</td>
                    <td style={dataCell(colors, mono, colors.dim)}>{h.chase.toFixed(1)}</td>
                    <td style={dataCell(colors, mono)}>{h.mc.toFixed(3)}</td>
                    <td style={dataCell(colors, mono)}>{h.mci.toFixed(3)}</td>
                    <td style={dataCell(colors, mono, typeof h.blast === 'number' && h.blast >= 17 ? colors.pos : colors.text)}>{fmt(h.blast)}</td>
                    <td style={dataCell(colors, mono)}>{fmt(h.ev)}</td>
                    <td style={{ padding: '7px 8px', textAlign: 'right' }}>
                      <span style={{ fontSize: 11, fontFamily: serif, fontStyle: 'italic', color: h.signal === 'Top Target' ? colors.pos : colors.dim }}>
                        {h.signal === 'Top Target' ? '“ buy ”' : `“ ${h.signal.toLowerCase()} ”`}
                      </span>
                    </td>
                    <td style={{ padding: '7px 8px', textAlign: 'right', fontSize: 10, fontFamily: mono, letterSpacing: 0.3 }}>
                      {h.flag !== '—' ? (
                        <span style={{ padding: '1px 6px', border: `1px solid ${colors.warn}`, color: colors.warn, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
                          ⚑ {h.flag.split(',')[0].trim()}
                        </span>
                      ) : <span style={{ color: colors.faint }}>—</span>}
                    </td>
                  </tr>
                  {isExp && (
                    <tr>
                      <td colSpan={18} style={{ padding: '14px 24px', background: colors.stripe, borderBottom: `1px solid ${colors.faint}` }}>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 24 }}>
                          <div>
                            <div style={{ fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: colors.dim, fontFamily: mono, marginBottom: 6 }}>12-week trajectory</div>
                            <Sparkline data={window.SPARKS[h.name]} width={240} height={48} color={colors.accent} fill strokeWidth={1.4} />
                          </div>
                          <div>
                            <div style={{ fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: colors.dim, fontFamily: mono, marginBottom: 6 }}>Process+ vs. league</div>
                            <Histogram bins={window.DISTRIBUTIONS.proc.bins} mean={window.DISTRIBUTIONS.proc.mean} label="" highlightPct={(h.proc - 70) / 100} width={220} height={48} color={colors.dim} />
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 8 }}>
                            <button style={{ ...editorialBtn(colors, mono), background: colors.accent, color: '#fff', borderColor: colors.accent }}>Full Player View →</button>
                            <button style={editorialBtn(colors, mono)}>Add to Compare</button>
                          </div>
                        </div>
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
        <div style={{ paddingTop: 10, fontSize: 10, color: colors.dim, fontFamily: mono, letterSpacing: 1, textAlign: 'right' }}>
          ↳ CLICK ROW TO SELECT · DOUBLE-CLICK TO EXPAND · ★ TO PIN
        </div>
      </div>

      {/* Distribution row — reacts to selection */}
      <div style={{ padding: '0 32px 32px' }}>
        <div style={{ padding: '0 0 10px', display: 'flex', alignItems: 'baseline', gap: 14 }}>
          <span style={{ fontSize: 10, letterSpacing: 3, textTransform: 'uppercase', color: colors.accent, fontFamily: mono, flexShrink: 0 }}>§ II</span>
          <h2 style={{ fontSize: 22, fontWeight: 400, margin: 0, fontStyle: 'italic', letterSpacing: -0.3, whiteSpace: 'nowrap', flexShrink: 0 }}>Where {sel.name.split(' ').pop()} stands</h2>
          <div style={{ flex: 1, borderBottom: `1px solid ${colors.border}`, marginBottom: 6, minWidth: 20 }} />
          <span style={{ fontSize: 10, color: colors.dim, fontFamily: mono, letterSpacing: 1, whiteSpace: 'nowrap', flexShrink: 0 }}>COMPONENT DISTRIBUTIONS</span>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
          {[
            { k: 'Process+', d: window.DISTRIBUTIONS.proc, v: sel.proc, range: [70, 170] },
            { k: 'K-Avoid+', d: window.DISTRIBUTIONS.kavoid, v: sel.kavoid, range: [60, 140] },
            { k: 'Power+', d: window.DISTRIBUTIONS.power, v: sel.power, range: [60, 170] },
            { k: 'Swing%', d: window.DISTRIBUTIONS.swing, v: sel.swing, range: [20, 60] },
          ].map(d => (
            <div key={d.k} style={{ borderTop: `1px solid ${colors.faint}`, paddingTop: 8 }}>
              <div style={{ fontSize: 9, letterSpacing: 2, textTransform: 'uppercase', color: colors.dim, fontFamily: mono }}>{d.k}</div>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 6, marginTop: 2 }}>
                <span style={{ fontSize: 18, fontFamily: serif, fontStyle: 'italic', color: colors.accent }}>{typeof d.v === 'number' ? d.v.toFixed(1) : '—'}</span>
                <span style={{ fontSize: 10, color: colors.dim, fontFamily: mono }}>μ = {d.d.mean}</span>
              </div>
              <div style={{ marginTop: 4 }}>
                <Histogram bins={d.d.bins} mean={d.d.mean} label="" highlightPct={(d.v - d.range[0]) / (d.range[1] - d.range[0])} width={220} height={40} color={colors.dim} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function dataCell(colors, mono, color) {
  return {
    padding: '7px 8px', textAlign: 'right',
    fontFamily: mono, fontSize: 11, fontVariantNumeric: 'tabular-nums',
    color: color || colors.text,
  };
}

function editorialBtn(colors, mono) {
  return {
    padding: '5px 10px', fontSize: 10, fontFamily: mono, letterSpacing: 1.2,
    background: colors.panel, color: colors.text,
    border: `1px solid ${colors.border}`, borderRadius: 2,
    cursor: 'pointer', textTransform: 'uppercase', fontWeight: 500,
  };
}

window.VariantEditorialDense = VariantEditorialDense;
