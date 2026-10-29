import React, { useState } from 'react';
import { ChartResponse } from '../types/astrology';

interface Props {
  chart: ChartResponse;
}

function isCurrentPeriod(start?: string, end?: string): boolean {
  if (!start || !end) return false;
  const today = new Date().toISOString().slice(0, 10);
  return start <= today && today < end;
}

export const AshtottariDasaPanel: React.FC<Props> = ({ chart }) => {
  const asht = chart.ashtottari_dasas;
  const [openIdx, setOpenIdx] = useState<number | null>(null);

  if (!asht || !asht.dasas) {
    return <div className="vx-empty-state">Ashtottari Dasa data is not available for this chart.</div>;
  }

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
      </div>

      <div className="vx-chara-dasa-grid" id="ashtottari-dasa-grid">
        {asht.dasas.map((d, idx) => {
          const active = isCurrentPeriod(d.start_date, d.end_date);
          const isOpen = openIdx === idx || (openIdx === null && active);
          return (
            <div key={`${d.dasa_lord}-${idx}`} className={`vx-dasa-card ${active ? 'active' : ''}`}>
              <div className="vx-dasa-card-head" onClick={() => setOpenIdx(isOpen ? -1 : idx)}>
                <div>
                  <strong>{d.dasa_lord}</strong>
                  {active && <span className="vx-now-badge">ACTIVE NOW</span>}
                </div>
                <span className="vx-dur-pill">{d.duration_years}Y</span>
              </div>
              <div className="vx-dasa-card-dates">
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
                        <span>{b.start_date}</span>
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
