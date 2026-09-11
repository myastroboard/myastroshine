import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HistogramDisplay } from '@/components/HistogramDisplay';
import type { HistogramData } from '@/types';

describe('HistogramDisplay', () => {
  it('draws one polyline per channel, scaled against the tallest bin', () => {
    const data: HistogramData = {
      r: [0, 10, 20],
      g: [5, 5, 5],
      b: [0, 0, 0],
    };

    const { container } = render(<HistogramDisplay data={data} />);

    const svg = screen.getByRole('img', { name: 'RGB histogram' });
    expect(svg).toBeInTheDocument();

    const polylines = container.querySelectorAll('polyline');
    expect(polylines).toHaveLength(3);

    // max across all channels is 20 -> y = 64 - (value/20)*64
    expect(polylines[0]).toHaveAttribute('points', '0,64 1,32 2,0');
    expect(polylines[0]).toHaveClass('stroke-channel-red');

    // g stays flat at value 5 out of max 20 -> y = 64 - (5/20)*64 = 48
    expect(polylines[1]).toHaveAttribute('points', '0,48 1,48 2,48');
    expect(polylines[1]).toHaveClass('stroke-channel-green');

    // b is all zero -> baseline at y = 64
    expect(polylines[2]).toHaveAttribute('points', '0,64 1,64 2,64');
    expect(polylines[2]).toHaveClass('stroke-channel-blue');
  });

  it('falls back to a max of 1 when every channel is empty of signal', () => {
    const data: HistogramData = { r: [0, 0], g: [0, 0], b: [0, 0] };

    const { container } = render(<HistogramDisplay data={data} />);

    const polylines = container.querySelectorAll('polyline');
    polylines.forEach((polyline) => {
      expect(polyline).toHaveAttribute('points', '0,64 1,64');
    });
  });

  it('renders an empty polyline for empty channel arrays', () => {
    const data: HistogramData = { r: [], g: [], b: [] };

    const { container } = render(<HistogramDisplay data={data} />);

    const polylines = container.querySelectorAll('polyline');
    expect(polylines).toHaveLength(3);
    polylines.forEach((polyline) => {
      expect(polyline).toHaveAttribute('points', '');
    });
  });
});
