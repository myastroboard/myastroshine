import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { StackProgress } from '@/components/stacking/StackProgress';

describe('StackProgress', () => {
  it('shows the percent, an active first step, and no detail when none is given', () => {
    render(<StackProgress percent={10} currentStep="upload" />);

    expect(screen.getByText('10%')).toBeInTheDocument();
    expect(screen.getByText('Uploading frames').className).toBe('text-muted');
    expect(screen.getByText('Alignment').className).toBe('text-ghost');
    expect(screen.queryByText(/·/)).not.toBeInTheDocument();
  });

  it('marks earlier steps done, the current step active with its detail, and later steps pending', () => {
    render(<StackProgress percent={55} currentStep="registration" detail="340/1066" />);

    expect(screen.getByText('Uploading frames').className).toBe('text-muted'); // done
    expect(screen.getByText('Calibration').className).toBe('text-muted'); // done
    expect(screen.getByText('Alignment').className).toBe('text-muted'); // active
    expect(screen.getByText('· 340/1066')).toBeInTheDocument();
    expect(screen.getByText('Normalization').className).toBe('text-ghost'); // pending
    expect(screen.getByText('Integration').className).toBe('text-ghost'); // pending
  });

  it('folds the post-processing backend step onto Integration', () => {
    render(<StackProgress percent={90} currentStep="post-processing" detail="cleanup" />);

    expect(screen.getByText('Integration').className).toBe('text-muted');
    expect(screen.getByText('· cleanup')).toBeInTheDocument();
  });

  it('marks every step done once currentStep is "done"', () => {
    render(<StackProgress percent={100} currentStep="done" />);

    for (const label of [
      'Uploading frames',
      'Calibration',
      'Alignment',
      'Normalization',
      'Integration',
    ]) {
      expect(screen.getByText(label).className).toBe('text-muted');
    }
  });

  it('treats an unknown step as fully pending', () => {
    render(<StackProgress percent={0} currentStep="mystery" />);

    for (const label of [
      'Uploading frames',
      'Calibration',
      'Alignment',
      'Normalization',
      'Integration',
    ]) {
      expect(screen.getByText(label).className).toBe('text-ghost');
    }
  });
});
