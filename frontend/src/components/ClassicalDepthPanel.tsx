import React from 'react';
import { astroStore, useAstroStore } from '../store/astroStore';
import { ChartResponse } from '../types/astrology';
import { firstWord } from '../lib/format';

interface Props {
  chart: ChartResponse;
}

const GRAHAS = ['Sun', 'Moon', 'Mars', 'Mercury', 'Jupiter', 'Venus', 'Saturn', 'Rahu', 'Ketu'];

export const ClassicalDepthPanel: React.FC<Props> = ({ chart }) => {
  const { selectedPlanet } = useAstroStore();
  const arudha = chart.arudha_padas;
  const avasthas = chart.avasthas || {};
  const vimsopaka = chart.vimsopaka_bala || {};
  const khara = chart.khara_drekkana;
  const nadi = chart.nadi;
  // Empty {} (light mode) is truthy in JS, so test for real content, not just presence.
  const hasArudha = !!arudha?.arudha_lagna;
  const hasKhara = !!khara?.rasi_name;
  const padas = Object.values(arudha?.padas || {}).sort((a, b) => a.house - b.house);

  const openShloka = (query: string, title: string) => {
    if (typeof window.openScriptureDrawer === 'function') {
      window.openScriptureDrawer(query, title);
    }
  };

  return (
    <div className="vx-panel-section" id="react-classical-depth-panel">
      {/* 1. Arudha Padas (AL, UL, A2..A11) & 22nd Drekkana */}
      <div className="vx-two-col">
        {hasArudha && arudha && (
          <div className="vx-mini-box" id="arudha-padas-box">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <h5 style={{ margin: 0 }}>
                <i className="fa-solid fa-landmark-dome" /> Arudha Padas (BPHS Ch. 29 — Maya & Manifestation)
              </h5>
              <button
                type="button"
                className="vx-shloka-link-btn"
                onClick={() =>
                  openShloka(
                    `Arudha Pada ${arudha.arudha_lagna?.pada_rasi_short || ''} Upapada ${arudha.upapada_lagna?.pada_rasi_short || ''} (BPHS Ch. 29)`,
                    'Arudha Padas & Upapada (BPHS Ch. 29)'
                  )
                }
              >
                <i className="fa-solid fa-scroll" /> Shloka
              </button>
            </div>
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
              {padas.map((p) => (
                <div
                  key={p.code}
                  className={`vx-pada-chip ${p.house === 1 || p.house === 12 ? 'key' : ''}`}
                  title={`${p.alias} — House ${p.house} (${p.house_rasi}, Lord ${p.house_lord})`}
                  onClick={() => astroStore.setSelectedPlanet(p.house_lord, true)}
                  style={{ cursor: 'pointer' }}
                >
                  <strong>{p.code}:</strong> {p.pada_rasi_short} (H{p.house_from_lagna})
                </div>
              ))}
            </div>
          </div>
        )}

        {hasKhara && khara && (
          <div className="vx-mini-box" id="khara-drekkana-box">
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px' }}>
              <h5 style={{ margin: 0 }}>
                <i className="fa-solid fa-triangle-exclamation" /> 22nd Drekkana (Khara Drekkana — Saravali Ch. 10)
              </h5>
              <button
                type="button"
                className="vx-shloka-link-btn"
                onClick={() =>
                  openShloka(
                    `22nd Drekkana Khara ${firstWord(khara.nature)} (Saravali Ch. 10 & Jataka Parijata)`,
                    '22nd Drekkana (Saravali Ch. 10)'
                  )
                }
              >
                <i className="fa-solid fa-scroll" /> Shloka
              </button>
            </div>
            <div className="vx-khara-details">
              <div>
                <strong>22nd Drekkana Sign:</strong> {khara.rasi_name} ({khara.decanate_label})
              </div>
              <div>
                <strong>Khara Lord (8th of D3):</strong>{' '}
                <span
                  className="vx-lord-chip sub"
                  style={{ cursor: 'pointer' }}
                  onClick={() => astroStore.setSelectedPlanet(khara.lord, true)}
                >
                  {khara.lord}
                </span>
              </div>
              <div>
                <strong>Classical Classification:</strong>{' '}
                <span className="vx-nature-badge">{khara.nature}</span>
              </div>
            </div>

            {Array.isArray(nadi?.elemental_trines) && nadi.elemental_trines.length > 0 && (
              <div style={{ marginTop: '10px', borderTop: '1px dashed rgba(217,119,6,0.25)', paddingTop: '8px' }}>
                <strong style={{ fontSize: '11px', color: 'var(--accent-gold)' }}>
                  <i className="fa-solid fa-fire-flame-curved" /> Bhrigu Nadi Elemental Trines (1–5–9):
                </strong>
                <div className="vx-trine-grid">
                  {nadi.elemental_trines.map((t) => (
                    <div key={t.tattva} className="vx-trine-row" title={(t.signs || []).join(', ')}>
                      <strong>{firstWord(t.tattva)}:</strong>{' '}
                      {t.planets?.length ? t.planets.join(', ') : 'Empty'}
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
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '8px', flexWrap: 'wrap', gap: '8px' }}>
          <h5 className="vx-sub-heading" style={{ margin: 0 }}>
            <i className="fa-solid fa-scale-balanced" /> Planetary Avasthas (BPHS Ch. 45), Vimsopaka Bala (/20) & Extra Vargas (D2, D4, D7)
          </h5>
          <button
            type="button"
            className="vx-shloka-link-btn"
            onClick={() =>
              openShloka(
                'planetary avastha Sayanadi Deepta Kumara Yuva (BPHS Ch. 45)',
                'Planetary Avasthas (BPHS Ch. 45)'
              )
            }
          >
            <i className="fa-solid fa-book-open" /> Inspect BPHS Ch. 45 Shlokas
          </button>
        </div>
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
                const isSelected = selectedPlanet === g;
                return (
                  <tr
                    key={g}
                    data-planet={g}
                    className={isSelected ? 'vx-planet-row-highlighted' : ''}
                    onClick={() => astroStore.setSelectedPlanet(isSelected ? null : g, true)}
                    style={{ cursor: 'pointer' }}
                    title="Click to highlight Graha Drishti (aspects) on the Kundali chart"
                  >
                    <td>
                      <strong>{g}</strong>
                      {isSelected && <span className="vx-drishti-dot" title="Active Drishti Highlight" />}
                    </td>
                    <td>
                      {av ? (
                        <span title={av.baladi}>
                          {firstWord(av.baladi)}{' '}
                          <small className="vx-muted">({Math.round(Number(av.baladi_result_pct) || 0)}%)</small>
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>{firstWord(av?.jagradadi) || '—'}</td>
                    <td>
                      <span className="vx-deeptadi-chip">{firstWord(av?.deeptadi) || '—'}</span>
                    </td>
                    <td>
                      {av ? (
                        <span>{av.sayanadi}</span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td className="vx-tabular">
                      {vb ? (
                        <span className="vx-vb-score">
                          <strong>{vb.score}</strong>/{vb.max_score ?? 20} <small title={vb.status}>({vb.percentage}%)</small>
                        </span>
                      ) : (
                        '—'
                      )}
                    </td>
                    <td>{firstWord(pl?.hora_rasi_name) || '—'}</td>
                    <td>{firstWord(pl?.chaturthamsha_rasi_name) || '—'}</td>
                    <td>{firstWord(pl?.saptamsha_rasi_name) || '—'}</td>
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
