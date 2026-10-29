import React from 'react';
import { astroStore, useAstroStore } from '../store/astroStore';
import { ClassicalDepthPanel } from './ClassicalDepthPanel';
import { KPSystemPanel } from './KPSystemPanel';
import { JaiminiSystemPanel } from './JaiminiSystemPanel';
import { AshtottariDasaPanel } from './AshtottariDasaPanel';
import { RagCorpusInspector } from './RagCorpusInspector';

export const AdvancedAstrologyWorkspace: React.FC = () => {
  const { chart, activePanelTab } = useAstroStore();

  if (!chart) {
    return null;
  }

  const tabs: {
    id: typeof activePanelTab;
    label: string;
    icon: string;
    badge?: string;
  }[] = [
    {
      id: 'classical',
      label: 'Avasthas, Arudha Padas & Vimsopaka',
      icon: 'fa-scale-balanced',
      badge: 'BPHS',
    },
    {
      id: 'kp',
      label: 'KP Cusps & 4-Level Significators',
      icon: 'fa-compass-drafting',
      badge: '12 Cusps',
    },
    {
      id: 'jaimini',
      label: 'Jaimini Karakas & Chara Dasa',
      icon: 'fa-crown',
      badge: chart.jaimini?.atmakaraka?.planet
        ? `AK: ${chart.jaimini.atmakaraka.planet}`
        : '7 Karakas',
    },
    {
      id: 'dasa',
      label: '108-Year Ashtottari Dasa',
      icon: 'fa-hourglass-half',
      badge: '108Y',
    },
    {
      id: 'rag',
      label: 'RAG Scripture Grounding',
      icon: 'fa-book-journal-whills',
      badge: '8 Books',
    },
  ];

  return (
    <div className="vx-react-workspace" id="react-advanced-astrology-workspace">
      <div className="vx-workspace-tabbar" role="tablist">
        {tabs.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={activePanelTab === t.id}
            data-testid={`tab-adv-${t.id}`}
            className={`vx-workspace-tab ${activePanelTab === t.id ? 'active' : ''}`}
            onClick={() => astroStore.setActivePanelTab(t.id)}
          >
            <i className={`fa-solid ${t.icon}`} />
            <span>{t.label}</span>
            {t.badge && <span className="vx-tab-badge">{t.badge}</span>}
          </button>
        ))}
      </div>

      <div className="vx-workspace-body">
        {activePanelTab === 'classical' && <ClassicalDepthPanel chart={chart} />}
        {activePanelTab === 'kp' && <KPSystemPanel chart={chart} />}
        {activePanelTab === 'jaimini' && <JaiminiSystemPanel chart={chart} />}
        {activePanelTab === 'dasa' && <AshtottariDasaPanel chart={chart} />}
        {activePanelTab === 'rag' && <RagCorpusInspector chart={chart} />}
      </div>
    </div>
  );
};
