import React from 'react';
import { ChartResponse } from '../types/astrology';

interface Props {
  chart: ChartResponse;
}

const HOUSE_MEANINGS: Record<number, string> = {
  1: 'Self, Health & Longevity',
  2: 'Wealth, Family (Kutumba) & Speech',
  3: 'Courage, Siblings & Short Travel',
  4: 'Home, Property, Vehicles & Education',
  5: 'Progeny, Intelligence & Speculation',
  6: 'Disease, Debt, Litigation & Service',
  7: 'Marriage, Spouse & Partnership',
  8: 'Obstacles, Sudden Events & Longevity',
  9: 'Fortune (Bhagya), Dharma & Long Travel',
  10: 'Career (Karma), Authority & Profession',
  11: 'Fulfillment of Desires (Labha) & Gains',
  12: 'Expenses, Foreign Residence & Moksha',
};

export const KPSystemPanel: React.FC<Props> = ({ chart }) => {
  const kp = chart.kp;
  if (!kp || !kp.cusps) {
    return <div className="vx-empty-state">KP Cuspal data is not available for this chart.</div>;
  }

  return (
    <div className="vx-panel-section" id="react-kp-panel">
      <div className="vx-panel-header">
        <div>
          <h4>
            <i className="fa-solid fa-Satellite-dish" /> Krishnamurti Padhati (KP) — 12 Placidus House Cusps & Stellar Sub-Lords
          </h4>
          <p>
            In KP Astrology, the <strong>Star-Lord (Nakshatra Lord)</strong> shows the source of an event and the{' '}
            <strong>Sub-Lord</strong> decides whether the house matter is promised or denied.
          </p>
        </div>
      </div>

      <div className="vx-table-scroll">
        <table className="vx-data-table" id="kp-cusps-table">
          <thead>
            <tr>
              <th>Cusp</th>
              <th>Sign (Rasi)</th>
              <th>Degree</th>
              <th>Nakshatra</th>
              <th>Rasi Lord</th>
              <th>Star Lord</th>
              <th>Sub-Lord</th>
              <th>Sub-Sub-Lord</th>
              <th>Key Significators (Levels I–IV)</th>
            </tr>
          </thead>
          <tbody>
            {kp.cusps.map((c) => {
              const sig = kp.house_significators?.[String(c.house)];
              return (
                <tr key={c.house}>
                  <td>
                    <span className="vx-cusp-badge">Cusp {c.house}</span>
                    <div className="vx-subtext">{HOUSE_MEANINGS[c.house]}</div>
                  </td>
                  <td>{c.rasi_name.split(' ')[0]}</td>
                  <td>{c.degree_in_sign.toFixed(2)}°</td>
                  <td>{c.nakshatra}</td>
                  <td>{c.rasi_lord}</td>
                  <td>
                    <span className="vx-lord-chip star">{c.star_lord}</span>
                  </td>
                  <td>
                    <span className="vx-lord-chip sub">{c.sub_lord}</span>
                  </td>
                  <td>
                    <span className="vx-lord-chip ssub">{c.sub_sub_lord}</span>
                  </td>
                  <td>
                    {sig ? (
                      <div className="vx-sig-levels">
                        <span title="Level I: Occupants of Star of Occupants">
                          <strong>L1:</strong> {sig.level_1_occupants_of_star_of_occupants.join(', ') || '—'}
                        </span>
                        <span title="Level II: Direct Occupants">
                          <strong>L2:</strong> {sig.level_2_occupants.join(', ') || '—'}
                        </span>
                        <span title="Level III: Occupants of Star of Owner">
                          <strong>L3:</strong> {sig.level_3_occupants_of_star_of_owner.join(', ') || '—'}
                        </span>
                        <span title="Level IV: House Owner">
                          <strong>L4:</strong> {sig.level_4_owner}
                        </span>
                      </div>
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
};
