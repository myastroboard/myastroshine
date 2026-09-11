import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StackResults } from '@/components/stacking/StackResults';
import type { StackResult, StackStatistics } from '@/types';

const STATS: StackStatistics = {
  framesStacked: 8,
  framesExcluded: 1,
  framesAutoRejected: 0,
  combinationMethod: 'average',
  registrationTransform: 'similarity',
  registrationRmsPx: null,
  referenceFrame: 0,
  snrImprovement: 1.8,
  measuredNoiseReduction: null,
  calibrated: false,
  postProcessed: false,
  drizzleFactor: 1,
};

const BASE: StackResult = {
  stackId: 'stack-1',
  status: 'completed',
  sessionId: 'session-1',
  stackedImageUrl: '/preview.jpg',
  statistics: STATS,
  frames: [],
  calibration: null,
  error: null,
};

describe('StackResults', () => {
  it('shows a failure message when the result carries an error', () => {
    render(
      <StackResults
        result={{ ...BASE, status: 'failed', statistics: null, stackedImageUrl: null, error: 'boom' }}
        onEnhance={vi.fn()}
        onDownload={vi.fn()}
      />,
    );
    expect(screen.getByText('Stacking failed: boom')).toBeInTheDocument();
  });

  it('shows an ellipsis status message while not completed and no error', () => {
    render(
      <StackResults
        result={{ ...BASE, status: 'processing', statistics: null, stackedImageUrl: null }}
        onEnhance={vi.fn()}
        onDownload={vi.fn()}
      />,
    );
    expect(screen.getByText('Stack processing...')).toBeInTheDocument();
  });

  it('falls back when completed but statistics are missing', () => {
    render(
      <StackResults
        result={{ ...BASE, statistics: null }}
        onEnhance={vi.fn()}
        onDownload={vi.fn()}
      />,
    );
    expect(screen.getByText('Stack completed...')).toBeInTheDocument();
  });

  it('falls back when completed but the composite URL is missing', () => {
    render(
      <StackResults
        result={{ ...BASE, stackedImageUrl: null }}
        onEnhance={vi.fn()}
        onDownload={vi.fn()}
      />,
    );
    expect(screen.getByText('Stack completed...')).toBeInTheDocument();
  });

  it('renders only the base rows when every optional stat is absent', () => {
    render(<StackResults result={BASE} onEnhance={vi.fn()} onDownload={vi.fn()} />);

    expect(screen.getByText('Frames stacked')).toBeInTheDocument();
    expect(screen.getByText('8')).toBeInTheDocument();
    expect(screen.getByText('Frames excluded')).toBeInTheDocument();
    expect(screen.getByText('1.80x')).toBeInTheDocument();
    expect(screen.queryByText('Auto-rejected')).not.toBeInTheDocument();
    expect(screen.queryByText('Alignment residual')).not.toBeInTheDocument();
    expect(screen.queryByText('Calibration')).not.toBeInTheDocument();
    expect(screen.queryByText('Cleaned up')).not.toBeInTheDocument();
    expect(screen.queryByText('Drizzle')).not.toBeInTheDocument();
    expect(screen.queryByText('Measured noise reduction')).not.toBeInTheDocument();
  });

  it('renders every optional row when present', () => {
    const fullStats: StackStatistics = {
      ...STATS,
      framesAutoRejected: 2,
      registrationRmsPx: 0.512,
      calibrated: true,
      postProcessed: true,
      drizzleFactor: 2,
      measuredNoiseReduction: 1.234,
    };
    render(
      <StackResults
        result={{ ...BASE, statistics: fullStats }}
        onEnhance={vi.fn()}
        onDownload={vi.fn()}
      />,
    );

    expect(screen.getByText('Auto-rejected')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('Alignment residual')).toBeInTheDocument();
    expect(screen.getByText('0.51 px')).toBeInTheDocument();
    expect(screen.getAllByText('Applied').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('Drizzle')).toBeInTheDocument();
    expect(screen.getByText('2x')).toBeInTheDocument();
    expect(screen.getByText('Measured noise reduction')).toBeInTheDocument();
    expect(screen.getByText('1.23x')).toBeInTheDocument();
  });

  it('fires the enhance and download callbacks', () => {
    const onEnhance = vi.fn();
    const onDownload = vi.fn();
    render(<StackResults result={BASE} onEnhance={onEnhance} onDownload={onDownload} />);

    fireEvent.click(screen.getByRole('button', { name: /enhance composite/i }));
    fireEvent.click(screen.getByRole('button', { name: /download composite/i }));

    expect(onEnhance).toHaveBeenCalledTimes(1);
    expect(onDownload).toHaveBeenCalledTimes(1);
  });
});
