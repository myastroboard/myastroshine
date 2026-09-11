import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { CaptureInfoPanel } from '@/components/CaptureInfoPanel';
import type { CaptureInfo } from '@/types';

describe('CaptureInfoPanel', () => {
  it('shows the extracted fields, formatting frames and total exposure', () => {
    const info: CaptureInfo = {
      objectName: 'M 31',
      telescope: 'S50 Pro',
      filter: 'IRCUT',
      frameCount: 1406,
      exposureS: 10,
      totalExposureS: 14060,
      gain: 200,
      sensorTempC: 16.3125,
    };

    render(<CaptureInfoPanel info={info} />);

    expect(screen.getByText('M 31')).toBeInTheDocument();
    expect(screen.getByText('S50 Pro')).toBeInTheDocument();
    expect(screen.getByText('IRCUT')).toBeInTheDocument();
    expect(screen.getByText('1406 × 10s')).toBeInTheDocument();
    expect(screen.getByText('3h 54min')).toBeInTheDocument();
    expect(screen.getByText('200')).toBeInTheDocument();
    expect(screen.getByText('16.3°C')).toBeInTheDocument();
  });

  it('omits fields that are missing', () => {
    render(<CaptureInfoPanel info={{ objectName: 'NGC 7000' }} />);

    expect(screen.getByText('NGC 7000')).toBeInTheDocument();
    expect(screen.queryByText(/Telescope|Télescope/)).not.toBeInTheDocument();
  });

  it('renders nothing when every field is absent', () => {
    const { container } = render(<CaptureInfoPanel info={{}} />);

    expect(container).toBeEmptyDOMElement();
  });
});
