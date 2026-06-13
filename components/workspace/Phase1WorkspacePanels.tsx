'use client';

import React from 'react';
import OwnershipTrendPanel from './OwnershipTrendPanel';
import MFIntelligencePanel from './MFIntelligencePanel';
import TranscriptIntelligencePanel from './TranscriptIntelligencePanel';
import ManagementCredibilityPanel from './ManagementCredibilityPanel';

type Props = { symbol: string };

export default function Phase1WorkspacePanels({ symbol }: Props) {
  if (!symbol) return null;
  return (
    <div className="space-y-4">
      <OwnershipTrendPanel symbol={symbol} />
      <MFIntelligencePanel symbol={symbol} />
      <TranscriptIntelligencePanel symbol={symbol} />
      <ManagementCredibilityPanel symbol={symbol} />
    </div>
  );
}
