import React from 'react';
import { useViewport } from '@xyflow/react';
import { LAYER_BAND_COLORS, LAYER_LABELS, LayerBand } from '../utils/capabilityAbstractionUtils';

type CapabilityAbstractionLayerBandsProps = {
  focusLayer?: string;
  bands: LayerBand[];
};

const CapabilityAbstractionLayerBands: React.FC<CapabilityAbstractionLayerBandsProps> = ({ focusLayer, bands }) => {
  const viewport = useViewport();
  const spanStart = -2000;
  const spanWidth = 6000;

  return (
    <div className="absolute inset-0 pointer-events-none" style={{ zIndex: 0 }}>
      {bands.map((band) => {
        const top = viewport.y + band.y * viewport.zoom;
        const height = band.h * viewport.zoom;
        const left = viewport.x + spanStart * viewport.zoom;
        const width = spanWidth * viewport.zoom;
        const isFocus = band.layer === focusLayer;

        return (
          <div
            key={band.layer}
            className="absolute"
            style={{
              top,
              left,
              width,
              height,
              backgroundColor: isFocus ? '#dbeafe' : LAYER_BAND_COLORS[band.layer] ?? '#f9fafb',
              borderBottom: '1px dashed #e5e7eb',
              opacity: 0.55,
              pointerEvents: 'none',
              zIndex: 0,
            }}
          >
            <span className="absolute left-2 top-1 text-[9px] font-bold text-gray-400 uppercase tracking-widest">
              {LAYER_LABELS[band.layer] ?? band.layer}
              {isFocus ? ' 🎯' : ''}
            </span>
          </div>
        );
      })}
    </div>
  );
};

export default CapabilityAbstractionLayerBands;
