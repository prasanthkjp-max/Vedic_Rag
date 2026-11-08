import React, { useState } from 'react';
import { ArgalaItem, ChartResponse } from '../types/astrology';
import { beforeParen, firstWord, isCurrentPeriod, parenPart, yearsSince } from '../lib/format';

interface Props {
  chart: ChartResponse;
}

const KARAKA_ORDER = ['AK', 'AmK', 'BK', 'MK', 'PK', 'GK', 'DK'];

function ArgalaList({ items, emptyLabel }: { items?: ArgalaItem[]; emptyLabel: string }) {
  const list = Array.isArray(items) ? items : [];
  if (list.length === 0) return <ul className="vx-compact-list"><li>{emptyLabel}</li></ul>;
  return (
    <ul className="vx-compact-list">
      {list.map((a, i) => (
        <li key={`${a.type}-${i}`} title={a.status}>
          <strong>
            {a.type} ({a.argala_sign}):
          </strong>{' '}
          {a.argala_planets?.length ? a.argala_planets.join(', ') : 'None'}
          {a.virodha_planets?.length ? (
            <small className="vx-muted">
              {' '}
              · Virodha ({a.virodha_sign}): {a.virodha_planets.join(', ')}
            </small>
          ) : null}
          <small className="vx-muted"> — {a.status}</small>
        </li>
      ))}
    </ul>
  );
}

export const JaiminiSystemPanel: React.FC<Props> = ({ chart }) => {
  const jaimini = chart.jaimini;
  const [openMahaIdx, setOpenMahaIdx] = useState<number | null>(null);
  const [charaFilter, setCharaFilter] = useState('');

  if (!jaimini || !Array.isArray(jaimini.chara_dasas) || !Array.isArray(jaimini.karakas)) {
    return <div className="vx-empty-state">Jaimini Sutra data is not available for this chart.</div>;
  }

  const charaDasas = jaimini.chara_dasas;
  const karakaByCode = new Map(jaimini.karakas.map((k) => [k.code, k]));
  const totalCharaYears = charaDasas.reduce((acc, c) => acc + (c.duration_years || 0), 0) || 90;
  // Age from the first period's start (= birth date), so the "now" marker is exact.
  const currentAge = yearsSince(charaDasas[0]?.start_date);

  const qLower = charaFilter.trim().toLowerCase();
  const filteredChara = charaDasas
    .map((cd, idx) => ({ cd, idx }))
    .filter(({ cd }) => {
      if (!qLower) return true;
      if (
        cd.rasi_name.toLowerCase().includes(qLower) ||
        cd.dasa_lord.toLowerCase().includes(qLower) ||
        cd.start_date.includes(qLower) ||
        cd.end_date.includes(qLower)
      ) {
        return true;
      }
      const qYear = parseInt(qLower, 10);
      const sYear = parseInt(cd.start_date.slice(0, 4), 10);
      const eYear = parseInt(cd.end_date.slice(0, 4), 10);
      return !isNaN(qYear) && qYear >= 1900 && qYear <= 2200 && sYear <= qYear && qYear <= eYear;
    });

  const jumpToRunningChara = () => {
    setCharaFilter('');
    const activeIdx = charaDasas.findIndex((cd) => isCurrentPeriod(cd.start_date, cd.end_date));
    if (activeIdx >= 0) {
      setOpenMahaIdx(activeIdx);
      const el = document.getElementById(`chara-card-${activeIdx}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  };

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
          const k = karakaByCode.get(code);
          if (!k) return null;
          const isKey = code === 'AK' || code === 'AmK' || code === 'DK';
          return (
            <div key={code} className={`vx-karaka-card ${isKey ? 'highlight' : ''}`}>
              <div className="vx-karaka-top">
                <span className="vx-karaka-code">{k.code}</span>
                <span className="vx-karaka-planet">{k.planet}</span>
              </div>
              <div className="vx-karaka-name">{beforeParen(k.role)}</div>
              <div className="vx-karaka-meaning">{parenPart(k.role)}</div>
              <div className="vx-karaka-meta">
                <span>
                  D1: {firstWord(k.rasi_name)} ({Number(k.degree).toFixed(2)}°)
                </span>
                <span>D9: {firstWord(k.navamsha_rasi_name)}</span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Argala summary */}
      <div className="vx-two-col" style={{ marginTop: '14px' }}>
        <div className="vx-mini-box">
          <h5>
            <i className="fa-solid fa-shield-halved" /> Argala (Planetary Intervention) on Lagna
          </h5>
          <ArgalaList items={jaimini.argala_on_lagna} emptyLabel="None" />
        </div>
        <div className="vx-mini-box">
          <h5>
            <i className="fa-solid fa-eye" /> Argala on Atmakaraka ({jaimini.atmakaraka?.planet})
          </h5>
          <ArgalaList items={jaimini.argala_on_atmakaraka} emptyLabel="None" />
        </div>
      </div>

      {/* 12-Rasi Jaimini Chara Dasa */}
      <div style={{ marginTop: '18px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px', marginBottom: '8px' }}>
          <h5 className="vx-sub-heading" style={{ margin: 0 }}>
            <i className="fa-solid fa-timeline" /> Jaimini Chara Dasa (Sign-Based Mahadasa & Antardasa)
          </h5>
          <div className="vx-dasa-explorer-controls">
            <input
              type="text"
              className="vx-dasa-search-input"
              placeholder="Filter sign, lord, or year (e.g. Mesha, Mars, 2026)..."
              value={charaFilter}
              onChange={(e) => setCharaFilter(e.target.value)}
            />
            <button type="button" className="vx-jump-today-btn" onClick={jumpToRunningChara}>
              <i className="fa-solid fa-crosshairs" /> Jump to Today
            </button>
          </div>
        </div>

        {/* Life Age Ribbon for Jaimini Chara Dasa */}
        <div className="vx-life-ribbon-box" style={{ marginBottom: '10px' }}>
          <div className="vx-life-ribbon-track">
            {charaDasas.map((cd, idx) => {
              const widthPct = Math.max(4, ((cd.duration_years || 1) / totalCharaYears) * 100);
              const active = isCurrentPeriod(cd.start_date, cd.end_date);
              return (
                <div
                  key={`${cd.rasi_index}-seg-${idx}`}
                  className={`vx-life-ribbon-seg ${active ? 'active' : ''}`}
                  style={{
                    width: `${widthPct}%`,
                    background: idx % 2 === 0 ? '#d97706' : '#ea580c',
                  }}
                  title={`${firstWord(cd.rasi_name)} (${cd.duration_years}Y): ${cd.start_date} → ${cd.end_date}`}
                  onClick={() => setOpenMahaIdx(idx)}
                >
                  <span>{firstWord(cd.rasi_name).slice(0, 3)}</span>
                </div>
              );
            })}
            <div
              className="vx-life-ribbon-now"
              style={{ left: `${Math.min(98, Math.max(2, (currentAge / totalCharaYears) * 100))}%` }}
              title={`Today (~Age ${Math.floor(currentAge)})`}
            />
          </div>
        </div>

        <div className="vx-chara-dasa-grid" id="jaimini-chara-dasa-grid">
          {filteredChara.map(({ cd, idx }) => {
            const active = isCurrentPeriod(cd.start_date, cd.end_date);
            const isOpen = openMahaIdx === idx || (openMahaIdx === null && active) || !!qLower;
            return (
              <div
                key={`${cd.rasi_index}-${idx}`}
                id={`chara-card-${idx}`}
                className={`vx-dasa-card ${active ? 'active' : ''}`}
              >
                <div className="vx-dasa-card-head" onClick={() => setOpenMahaIdx(isOpen ? -1 : idx)}>
                  <div>
                    <strong>{firstWord(cd.rasi_name)}</strong>{' '}
                    <span className="vx-subtext">({parenPart(cd.dasa_lord) || cd.dasa_lord})</span>
                    {active && <span className="vx-now-badge">ACTIVE NOW</span>}
                  </div>
                  <span className="vx-dur-pill vx-tabular">{cd.duration_years}Y</span>
                </div>
                <div className="vx-dasa-card-dates vx-tabular">
                  {cd.start_date} → {cd.end_date}
                </div>
                {isOpen && (
                  <div className="vx-dasa-card-bhuktis">
                    {(cd.bhuktis || []).map((b, bIdx) => {
                      const bActive = isCurrentPeriod(b.start_date, b.end_date);
                      return (
                        <div key={bIdx} className={`vx-bhukti-row ${bActive ? 'active' : ''}`}>
                          <span>
                            {firstWord(b.bhukti_lord)} <small className="vx-muted">({parenPart(b.bhukti_lord)})</small>{' '}
                            {bActive && <strong>• NOW</strong>}
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
    </div>
  );
};
