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

  it('formats a duration under an hour as minutes only', () => {
    render(<CaptureInfoPanel info={{ totalExposureS: 900 }} />);

    expect(screen.getByText('15min')).toBeInTheDocument();
  });

  it('formats a whole-hour duration without a minutes suffix', () => {
    render(<CaptureInfoPanel info={{ totalExposureS: 7200 }} />);

    expect(screen.getByText('2h')).toBeInTheDocument();
  });

  it('shows the frame count alone when no per-frame exposure is known', () => {
    render(<CaptureInfoPanel info={{ frameCount: 42 }} />);

    expect(screen.getByText('42')).toBeInTheDocument();
  });

  it('formats a valid capture date', () => {
    render(<CaptureInfoPanel info={{ dateObs: '2024-05-01T00:00:00Z' }} />);

    const expected = new Date('2024-05-01T00:00:00Z').toLocaleDateString();
    expect(screen.getByText(expected)).toBeInTheDocument();
  });

  it('omits an unparsable capture date', () => {
    render(<CaptureInfoPanel info={{ dateObs: 'not-a-date', objectName: 'M 42' }} />);

    expect(screen.getByText('M 42')).toBeInTheDocument();
    expect(screen.queryByText(/Date/)).not.toBeInTheDocument();
  });
});
