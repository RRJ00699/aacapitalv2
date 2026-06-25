'use client';

import React from 'react';
import OwnershipTrendPanel from './OwnershipTrendPanel';
// import TranscriptIntelligencePanel from './TranscriptIntelligencePanel'; // retired
import ManagementCredibilityPanel from './ManagementCredibilityPanel';

type Props = { symbol: string };

export default function Phase1WorkspacePanels({ symbol }: Props) {
  if (!symbol) return null;
  return (
    <div className="space-y-4">
      <OwnershipTrendPanel symbol={symbol} />
      {/* MFIntelligencePanel removed — superseded by MFOwnershipPanel (shows fund names, weights, dates, 💎 fresh initiations) */}
      {/* Transcript Intelligence retired: no loader for transcript_* tables; the same
          Screener concall data is already shown in Management Credibility below.
      <TranscriptIntelligencePanel symbol={symbol} /> */}
      <ManagementCredibilityPanel symbol={symbol} />
    </div>
  );
}
