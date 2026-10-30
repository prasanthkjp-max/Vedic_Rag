import React, { useState } from 'react';
import { ChartResponse } from '../types/astrology';

interface Props {
  chart: ChartResponse;
}

const PLANET_COLORS: Record<string, string> = {
  Sun: '#ea580c',
  Moon: '#0284c7',
  Mars: '#dc2626',
  Mercury: '#16a34a',
  Jupiter: '#d97706',
  Venus: '#db2777',
  Saturn: '#4f46e5',
  Rahu: '#475569',
  Ketu: '#78716c',
};

function isCurrentPeriod(start?: string, end?: string): boolean {
  if (!start || !end) return false;
  const today = new Date().toISOString().slice(0, 10);
  return start <= today && today < end;
}

export const AshtottariDasaPanel: React.FC<Props> = ({ chart }) => {
  const asht = chart.ashtottari_dasas;
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const [filterQuery, setFilterQuery] = useState('');

  if (!asht || !asht.dasas) {
    return <div className="vx-empty-state">Ashtottari Dasa data is not available for this chart.</div>;
  }

  const birthYear = parseInt((chart.metadata?.datetime || '1995').slice(0, 4), 10) || 1995;
  const currentYear = new Date().getFullYear();
  const currentAge = Math.max(0, Math.min(108, currentYear - birthYear));

  const qLower = filterQuery.trim().toLowerCase();
  const filteredDasas = asht.dasas.map((d, idx) => ({ d, idx })).filter(({ d }) => {
    if (!qLower) return true;
    if (d.dasa_lord.toLowerCase().includes(qLower)) return true;
    if (d.start_date.includes(qLower) || d.end_date.includes(qLower)) return true;
    const sYear = parseInt(d.start_date.slice(0, 4), 10);
    const eYear = parseInt(d.end_date.slice(0, 4), 10);
    const qYear = parseInt(qLower, 10);
    if (!isNaN(qYear) && qYear >= 1900 && qYear <= 2200 && sYear <= qYear && qYear <= eYear) {
      return true;
    }
    return (d.bhuktis || []).some(
      (b) => b.bhukti_lord.toLowerCase().includes(qLower) || b.start_date.includes(qLower)
    );
  });

  const jumpToRunningPeriod = () => {
    setFilterQuery('');
    const activeIdx = asht.dasas.findIndex((d) => isCurrentPeriod(d.start_date, d.end_date));
    if (activeIdx >= 0) {
      setOpenIdx(activeIdx);
      const el = document.getElementById(`ashtottari-card-${activeIdx}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

  return (
    <div className="vx-panel-section" id="react-ashtottari-panel">
      <div className="vx-panel-header">
        <div>
          <h4>
            <i className="fa-solid fa-clock-rotate-left" /> 108-Year Ashtottari (Astottari) Dasa System (BPHS Ch. 46)
          </h4>
          <p>
            <strong>Scriptural Applicability:</strong>{' '}
            <span className={asht.applicable ? 'vx-badge-ok' : 'vx-badge-note'}>
              {asht.applicable ? 'Conditional Applicable' : 'Universal / Secondary Reference'}
            </span>{' '}
            — {asht.applicability_reason}
          </p>
        </div>
        <div className="vx-dasa-explorer-controls">
          <input
            type="text"
            className="vx-dasa-search-input"
            placeholder="Search planet or year (e.g. Jupiter, 2026)..."
            value={filterQuery}
            onChange={(e) => setFilterQuery(e.target.value)}
          />
          <button
            type="button"
            className="vx-jump-today-btn"
            onClick={jumpToRunningPeriod}
            title="Expand and scroll to today's running Mahadasa & Bhukti"
          >
            <i className="fa-solid fa-crosshairs" /> Jump to Today
          </button>
        </div>
      </div>

      {/* Visual Life Age Timeline Ribbon (0 to 108 Years) */}
      <div className="vx-life-ribbon-box">
        <div className="vx-life-ribbon-head">
          <span>
            <i className="fa-solid fa-Hourglass-start" /> Life Age Timeline Ribbon (0 → 108 Years)
          </span>
          <span className="vx-tabular">Current Age: ~{currentAge} yrs ({currentYear})</span>
        </div>
        <div className="vx-life-ribbon-track">
          {asht.dasas.map((d, idx) => {
            const widthPct = Math.max(4, (d.duration_years / 108) * 100);
            const active = isCurrentPeriod(d.start_date, d.end_date);
            return (
              <div
                key={`${d.dasa_lord}-seg-${idx}`}
                className={`vx-life-ribbon-seg ${active ? 'active' : ''}`}
                style={{
                  width: `${widthPct}%`,
                  background: PLANET_COLORS[d.dasa_lord] || '#d97706',
                }}
                title={`${d.dasa_lord} (${d.duration_years}Y): ${d.start_date} → ${d.end_date}`}
                onClick={() => setOpenIdx(idx)}
              >
                <span>{d.dasa_lord.slice(0, 2)}</span>
              </div>
            );
          })}
          <div
            className="vx-life-ribbon-now"
            style={{ left: `${Math.min(98, Math.max(2, (currentAge / 108) * 100))}%` }}
            title={`Today (~Age ${currentAge})`}
          />
        </div>
        <div className="vx-life-ribbon-ticks vx-tabular">
          <span>Age 0 ({birthYear})</span>
          <span>25Y</span>
          <span>50Y</span>
          <span>75Y</span>
          <span>108Y ({birthYear + 108})</span>
        </div>
      </div>

      <div className="vx-chara-dasa-grid" id="ashtottari-dasa-grid">
        {filteredDasas.map(({ d, idx }) => {
          const active = isCurrentPeriod(d.start_date, d.end_date);
          const isOpen = openIdx === idx || (openIdx === null && active) || !!qLower;
          return (
            <div
              key={`${d.dasa_lord}-${idx}`}
              id={`ashtottari-card-${idx}`}
              className={`vx-dasa-card ${active ? 'active' : ''}`}
            >
              <div className="vx-dasa-card-head" onClick={() => setOpenIdx(isOpen ? -1 : idx)}>
                <div>
                  <strong>{d.dasa_lord}</strong>
                  {active && <span className="vx-now-badge">ACTIVE NOW</span>}
                </div>
                <span className="vx-dur-pill vx-tabular">{d.duration_years}Y</span>
              </div>
              <div className="vx-dasa-card-dates vx-tabular">
                {d.start_date} → {d.end_date}
              </div>
              {isOpen && (
                <div className="vx-dasa-card-bhuktis">
                  {(d.bhuktis || []).map((b, bIdx) => {
                    const bActive = isCurrentPeriod(b.start_date, b.end_date);
                    return (
                      <div key={bIdx} className={`vx-bhukti-row ${bActive ? 'active' : ''}`}>
                        <span>
                          {b.bhukti_lord} {bActive && <strong>• NOW</strong>}
                        </span>
                        <span className="vx-tabular">{b.start_date}</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
