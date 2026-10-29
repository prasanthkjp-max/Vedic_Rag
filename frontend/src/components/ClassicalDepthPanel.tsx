import React from 'react';
import { ChartResponse } from '../types/astrology';

interface Props {
  chart: ChartResponse;
}

const GRAHAS = ['Sun', 'Moon', 'Mars', 'Mercury', 'Jupiter', 'Venus', 'Saturn', 'Rahu', 'Ketu'];

export const ClassicalDepthPanel: React.FC<Props> = ({ chart }) => {
  const arudha = chart.arudha_padas;
  const avasthas = chart.avasthas || {};
  const vimsopaka = chart.vimsopaka_bala || {};
  const khara = chart.khara_drekkana;
  const nadi = chart.nadi;

  return (
    <div className="vx-panel-section" id="react-classical-depth-panel">
      {/* 1. Arudha Padas (AL, UL, A2..A11) & 22nd Drekkana */}
      <div className="vx-two-col">
        {arudha && (
          <div className="vx-mini-box" id="arudha-padas-box">
            <h5>
              <i className="fa-solid fa-landmark-dome" /> Arudha Padas (BPHS Ch. 29 — Maya & Manifestation)
            </h5>
            <div className="vx-highlight-strip">
              <span>
                <strong>AL (Arudha Lagna):</strong> {arudha.arudha_lagna?.pada_rasi_short} (H
                {arudha.arudha_lagna?.house_from_lagna})
              </span>
              <span>
                <strong>UL (Upapada Lagna):</strong> {arudha.upapada_lagna?.pada_rasi_short} (H
                {arudha.upapada_lagna?.house_from_lagna})
              </span>
            </div>
            <div className="vx-pada-chips">
              {Object.values(arudha.padas || {}).map((p) => (
                <div
                  key={p.code}
                  className={`vx-pada-chip ${p.house === 1 || p.house === 12 ? 'key' : ''}`}
                  title={`House ${p.house} (${p.bhava_rasi_name}, Lord ${p.bhava_lord})`}
                >
                  <strong>{p.code}:</strong> {p.pada_rasi_short} (H{p.house_from_lagna})
                </div>
              ))}
            </div>
          </div>
        )}

        {khara && (
          <div className="vx-mini-box" id="khara-drekkana-box">
            <h5>
              <i className="fa-solid fa-triangle-exclamation" /> 22nd Drekkana (Khara Drekkana — Saravali Ch. 10)
            </h5>
            <div className="vx-khara-details">
              <div>
                <strong>22nd Drekkana Sign:</strong> {khara.rasi_name} (Decanate {khara.decanate}:{' '}
                {khara.degree_span})
              </div>
              <div>
                <strong>Khara Lord (8th of D3):</strong>{' '}
                <span className="vx-lord-chip sub">{khara.lord}</span>
              </div>
              <div>
                <strong>Classical Classification:</strong>{' '}
                <span className="vx-nature-badge">{khara.nature}</span>
              </div>
            </div>

            {nadi?.elemental_trines && (
              <div style={{ marginTop: '10px', borderTop: '1px dashed rgba(217,119,6,0.25)', paddingTop: '8px' }}>
                <strong style={{ fontSize: '11px', color: 'var(--accent-gold)' }}>
                  <i className="fa-solid fa-fire-flame-curved" /> Bhrigu Nadi Elemental Trines (1–5–9):
                </strong>
                <div className="vx-trine-grid">
                  {Object.entries(nadi.elemental_trines).map(([tName, info]) => (
                    <div key={tName} className="vx-trine-row">
                      <strong>{tName.split(' ')[0]}:</strong>{' '}
                      {info.planets.length ? info.planets.join(', ') : 'Empty'}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>

      {/* 2. Planetary Avasthas + Vimsopaka Bala + D2/D4/D7 Vargas */}
      <div style={{ marginTop: '16px' }}>
        <h5 className="vx-sub-heading">
          <i className="fa-solid fa-scale-balanced" /> Planetary Avasthas (BPHS Ch. 45), Vimsopaka Bala (/20) & Extra Vargas (D2, D4, D7)
        </h5>
        <div className="vx-table-scroll">
          <table className="vx-data-table" id="avasthas-vimsopaka-table">
            <thead>
              <tr>
                <th>Graha</th>
                <th>Baladi (Age)</th>
                <th>Jagradadi</th>
                <th>Deeptadi (Dignity State)</th>
                <th>Sayanadi (BPHS Ch. 45)</th>
                <th>Vimsopaka (/20)</th>
                <th>D2 (Hora)</th>
                <th>D4 (Turya)</th>
                <th>D7 (Saptamsa)</th>
              </tr>
            </thead>
            <tbody>
              {GRAHAS.map((g) => {
                const av = avasthas[g];
                const vb = vimsopaka[g];
                const pl = chart.placements?.[g];
                if (!av && !pl) return null;
                return (
                  <tr key={g}>
                    <td>
                      <strong>{g}</strong>
                    </td>
                    <td>
                      {av ? (
                        <span title={av.baladi_meaning}>
                          {av.baladi.split(' ')[0]}{' '}
                          <small className="vx-muted">({Math.round(av.proportion_multiplier * 100)}%)</small>
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>{av?.jagradadi?.split(' ')[0] || '—'}</td>
                    <td>
                      <span className="vx-deeptadi-chip">{av?.deeptadi?.split(' ')[0] || '—'}</span>
                    </td>
                    <td>
                      {av ? (
                        <span>
                          {av.sayanadi} <small className="vx-muted">[{av.cheshta_sub_state}]</small>
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>
                      {vb ? (
                        <span className="vx-vb-score">
                          <strong>{vb.score}</strong>/20 <small>({vb.percentage}%)</small>
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>{pl?.hora_rasi_name?.split(' ')[0] || '—'}</td>
                    <td>{pl?.chaturthamsha_rasi_name?.split(' ')[0] || '—'}</td>
                    <td>{pl?.saptamsha_rasi_name?.split(' ')[0] || '—'}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
