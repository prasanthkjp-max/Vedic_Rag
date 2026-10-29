import React, { useState } from 'react';
import { ChartResponse } from '../types/astrology';

interface Props {
  chart: ChartResponse;
}

const KARAKA_ORDER = ['AK', 'AmK', 'BK', 'MK', 'PK', 'GK', 'DK'];

function isCurrentPeriod(start?: string, end?: string): boolean {
  if (!start || !end) return false;
  const today = new Date().toISOString().slice(0, 10);
  return start <= today && today < end;
}

export const JaiminiSystemPanel: React.FC<Props> = ({ chart }) => {
  const jaimini = chart.jaimini;
  const [openMahaIdx, setOpenMahaIdx] = useState<number | null>(null);

  if (!jaimini) {
    return <div className="vx-empty-state">Jaimini Sutra data is not available for this chart.</div>;
  }

  return (
    <div className="vx-panel-section" id="react-jaimini-panel">
      <div className="vx-panel-header">
        <div>
          <h4>
            <i className="fa-solid fa-crown" /> Jaimini Maharshi Sutras — 7 Chara Karakas, Karakamsa & Chara Dasa
          </h4>
          <p>
            Computed strictly per <strong>Brihat Parasara Hora Sastra (Ch. 32–33)</strong> & Jaimini Upadesa Sutras.{' '}
            <strong>Karakamsa Lagna:</strong> {jaimini.karakamsa_rasi_name} (Lord: {jaimini.karakamsa_lord},{' '}
            {jaimini.swamsa_house_from_d9_lagna}th from D9 Lagna).
          </p>
        </div>
      </div>

      {/* 7 Chara Karakas Grid */}
      <div className="vx-karaka-grid" id="jaimini-karakas-grid">
        {KARAKA_ORDER.map((code) => {
          const k = jaimini.karakas?.[code];
          if (!k) return null;
          const isKey = code === 'AK' || code === 'AmK' || code === 'DK';
          return (
            <div key={code} className={`vx-karaka-card ${isKey ? 'highlight' : ''}`}>
              <div className="vx-karaka-top">
                <span className="vx-karaka-code">{k.code}</span>
                <span className="vx-karaka-planet">{k.planet}</span>
              </div>
              <div className="vx-karaka-name">{k.name}</div>
              <div className="vx-karaka-meaning">{k.meaning}</div>
              <div className="vx-karaka-meta">
                <span>D1: {k.rasi_name.split(' ')[0]} ({k.degree_in_sign.toFixed(2)}°)</span>
                <span>D9: {k.navamsha_rasi_name.split(' ')[0]}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Argala & Rasi Drishti Summary */}
      <div className="vx-two-col" style={{ marginTop: '14px' }}>
        <div className="vx-mini-box">
          <h5>
            <i className="fa-solid fa-shield-halved" /> Argala (Planetary Intervention) on Lagna
          </h5>
          <ul className="vx-compact-list">
            {Object.entries(jaimini.argala_on_lagna || {}).map(([label, item]) => (
              <li key={label}>
                <strong>{label.replace(/_/g, ' ')} ({item.rasi_short}):</strong>{' '}
                {item.planets.length ? item.planets.join(', ') : 'None (Unobstructed)'}
              </li>
            ))}
          </ul>
        </div>
        <div className="vx-mini-box">
          <h5>
            <i className="fa-solid fa-eye" /> Argala on Atmakaraka ({jaimini.atmakaraka?.planet})
          </h5>
          <ul className="vx-compact-list">
            {Object.entries(jaimini.argala_on_atmakaraka || {}).map(([label, item]) => (
              <li key={label}>
                <strong>{label.replace(/_/g, ' ')} ({item.rasi_short}):</strong>{' '}
                {item.planets.length ? item.planets.join(', ') : 'None'}
              </li>
            ))}
          </ul>
        </div>
      </div>

      {/* 12-Rasi Jaimini Chara Dasa */}
      <div style={{ marginTop: '18px' }}>
        <h5 className="vx-sub-heading">
          <i className="fa-solid fa-timeline" /> Jaimini Chara Dasa (Sign-Based Mahadasa & Antardasa)
        </h5>
        <div className="vx-chara-dasa-grid" id="jaimini-chara-dasa-grid">
          {(jaimini.chara_dasas || []).map((cd, idx) => {
            const active = isCurrentPeriod(cd.start_date, cd.end_date);
            const isOpen = openMahaIdx === idx || (openMahaIdx === null && active);
            return (
              <div key={`${cd.rasi_short}-${idx}`} className={`vx-dasa-card ${active ? 'active' : ''}`}>
                <div
                  className="vx-dasa-card-head"
                  onClick={() => setOpenMahaIdx(isOpen ? -1 : idx)}
                >
                  <div>
                    <strong>{cd.rasi_short}</strong>{' '}
                    <span className="vx-subtext">({cd.lord})</span>
                    {active && <span className="vx-now-badge">ACTIVE NOW</span>}
                  </div>
                  <span className="vx-dur-pill">{cd.duration_years}Y</span>
                </div>
                <div className="vx-dasa-card-dates">
                  {cd.start_date} → {cd.end_date}
                </div>
                {isOpen && (
                  <div className="vx-dasa-card-bhuktis">
                    {(cd.bhuktis || []).map((b, bIdx) => {
                      const bActive = isCurrentPeriod(b.start_date, b.end_date);
                      return (
                        <div key={bIdx} className={`vx-bhukti-row ${bActive ? 'active' : ''}`}>
                          <span>
                            {b.rasi_short} {bActive && <strong>• NOW</strong>}
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
    </div>
  );
};
