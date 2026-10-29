import React from 'react';
import { astroStore, useAstroStore } from '../store/astroStore';
import { AstroSystem, AyanamsaName, DasaSystem } from '../types/astrology';

const SYSTEMS: { id: AstroSystem; label: string; badge: string }[] = [
  { id: 'Parashara', label: 'Parashara (Drik)', badge: 'BPHS' },
  { id: 'KP', label: 'KP Stellar', badge: 'Sub-Lords' },
  { id: 'Jaimini', label: 'Jaimini Sutras', badge: 'Karakas' },
  { id: 'Nadi', label: 'Bhrigu Nadi', badge: 'Trines' },
  { id: 'Vakya', label: 'Vakya Siddhanta', badge: 'South Indian' },
];

const DASAS: { id: DasaSystem; label: string }[] = [
  { id: 'Vimshottari', label: 'Vimshottari (120Y)' },
  { id: 'Ashtottari', label: 'Ashtottari (108Y)' },
  { id: 'Chara', label: 'Jaimini Chara Dasa' },
];

const AYANAMSAS: { id: AyanamsaName; label: string }[] = [
  { id: 'Lahiri', label: 'Lahiri (Chitrapaksha)' },
  { id: 'KP', label: 'KP (Krishnamurti)' },
  { id: 'Raman', label: 'B.V. Raman' },
  { id: 'Yukteshwar', label: 'Sri Yukteshwar' },
  { id: 'Fagan-Bradley', label: 'Fagan-Bradley' },
  { id: 'DP', label: 'Dasa Paddhati (DP)' },
  { id: 'Tropical', label: 'Tropical (Sayana)' },
];

export const SystemSelectorBar: React.FC = () => {
  const { system, timing, ayanamsa, chart } = useAstroStore();

  const applyAndRecalculate = (
    next: Partial<{ system: AstroSystem; timing: DasaSystem; ayanamsa: AyanamsaName }>
  ) => {
    astroStore.setSystemConfig(next);
    if (chart && typeof window.generateBirthChart === 'function') {
      window.generateBirthChart();
    }
  };

  return (
    <div className="vx-react-selector-bar" id="react-system-selector-bar">
      <div className="vx-react-selector-group">
        <span className="vx-react-selector-label">
          <i className="fa-solid fa-compass-drafting" /> Calculation System:
        </span>
        <div className="vx-react-pill-row">
          {SYSTEMS.map((s) => (
            <button
              key={s.id}
              type="button"
              data-testid={`btn-sys-${s.id.toLowerCase()}`}
              className={`vx-react-pill ${system === s.id ? 'active' : ''}`}
              onClick={() => {
                const updates: Partial<{
                  system: AstroSystem;
                  timing: DasaSystem;
                  ayanamsa: AyanamsaName;
                }> = { system: s.id };
                if (s.id === 'Jaimini' && timing === 'Vimshottari') {
                  updates.timing = 'Chara';
                } else if (s.id === 'KP' && ayanamsa === 'Lahiri') {
                  updates.ayanamsa = 'KP';
                }
                applyAndRecalculate(updates);
              }}
            >
              <span>{s.label}</span>
              <span className="vx-react-pill-badge">{s.badge}</span>
            </button>
          ))}
        </div>
      </div>

      <div className="vx-react-selector-row2">
        <div className="vx-react-selector-group">
          <span className="vx-react-selector-label">
            <i className="fa-solid fa-hourglass-half" /> Dasa Timing:
          </span>
          <div className="vx-react-pill-row">
            {DASAS.map((d) => (
              <button
                key={d.id}
                type="button"
                data-testid={`btn-dasa-${d.id.toLowerCase()}`}
                className={`vx-react-pill sm ${timing === d.id ? 'active' : ''}`}
                onClick={() => applyAndRecalculate({ timing: d.id })}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>

        <div className="vx-react-selector-group">
          <span className="vx-react-selector-label">
            <i className="fa-solid fa-star" /> Ayanamsa:
          </span>
          <select
            className="vx-react-select"
            data-testid="select-react-ayanamsa"
            value={ayanamsa}
            onChange={(e) => applyAndRecalculate({ ayanamsa: e.target.value as AyanamsaName })}
          >
            {AYANAMSAS.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label}
              </option>
            ))}
          </select>
        </div>
      </div>
    </div>
  );
};
