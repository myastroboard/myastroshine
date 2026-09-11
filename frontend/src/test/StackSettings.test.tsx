import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StackSettings } from '@/components/stacking/StackSettings';
import type { StackSettings as StackSettingsValue } from '@/types';

const BASE: StackSettingsValue = {
  registrationTransform: 'similarity',
  combinationMethod: 'average',
  rejectionAlgo: 'winsorized_sigma',
  weighting: 'noise',
  cosmeticCorrection: true,
  qualityFilter: 'moderate',
  postProcess: true,
  drizzleFactor: 1,
};

describe('StackSettings', () => {
  it('renders every field with its current value', () => {
    render(<StackSettings settings={BASE} onChange={vi.fn()} />);

    expect(screen.getByLabelText(/alignment/i)).toHaveValue('similarity');
    expect(screen.getByLabelText(/combination/i)).toHaveValue('average');
    expect(screen.getByLabelText(/pixel rejection/i)).toHaveValue('winsorized_sigma');
    expect(screen.getByLabelText(/frame weighting/i)).toHaveValue('noise');
    expect(screen.getByLabelText(/auto-reject bad frames/i)).toHaveValue('moderate');
    expect(screen.getByLabelText(/drizzle/i)).toHaveValue('1');
    expect(screen.getByRole('checkbox', { name: /clean up the composite/i })).toBeChecked();
  });

  it('reports a transform change', () => {
    const onChange = vi.fn();
    render(<StackSettings settings={BASE} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/alignment/i), { target: { value: 'affine' } });
    expect(onChange).toHaveBeenCalledWith({ ...BASE, registrationTransform: 'affine' });
  });

  it('reports a combination method change', () => {
    const onChange = vi.fn();
    render(<StackSettings settings={BASE} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/combination/i), { target: { value: 'median' } });
    expect(onChange).toHaveBeenCalledWith({ ...BASE, combinationMethod: 'median' });
  });

  it('reports a rejection algorithm change', () => {
    const onChange = vi.fn();
    render(<StackSettings settings={BASE} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/pixel rejection/i), { target: { value: 'sigma' } });
    expect(onChange).toHaveBeenCalledWith({ ...BASE, rejectionAlgo: 'sigma' });
  });

  it('reports a weighting change', () => {
    const onChange = vi.fn();
    render(<StackSettings settings={BASE} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/frame weighting/i), { target: { value: 'quality' } });
    expect(onChange).toHaveBeenCalledWith({ ...BASE, weighting: 'quality' });
  });

  it('reports a quality filter change', () => {
    const onChange = vi.fn();
    render(<StackSettings settings={BASE} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/auto-reject bad frames/i), {
      target: { value: 'strict' },
    });
    expect(onChange).toHaveBeenCalledWith({ ...BASE, qualityFilter: 'strict' });
  });

  it('reports a drizzle factor change as a number', () => {
    const onChange = vi.fn();
    render(<StackSettings settings={BASE} onChange={onChange} />);
    fireEvent.change(screen.getByLabelText(/drizzle/i), { target: { value: '2' } });
    expect(onChange).toHaveBeenCalledWith({ ...BASE, drizzleFactor: 2 });
  });

  it('reports a post-process toggle', () => {
    const onChange = vi.fn();
    render(<StackSettings settings={BASE} onChange={onChange} />);
    fireEvent.click(screen.getByRole('checkbox', { name: /clean up the composite/i }));
    expect(onChange).toHaveBeenCalledWith({ ...BASE, postProcess: false });
  });
});
