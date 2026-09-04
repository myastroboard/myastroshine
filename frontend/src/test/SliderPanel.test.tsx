import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SliderPanel } from '@/components/SliderPanel';
import { DEFAULT_PARAMETERS } from '@/types';

describe('SliderPanel', () => {
  it('reports a parameter change with the key and the new value', () => {
    const onParameterChange = vi.fn();
    render(
      <SliderPanel
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={onParameterChange}
        onReset={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Contrast'), { target: { value: '1.8' } });

    expect(onParameterChange).toHaveBeenCalledWith('contrast', 1.8);
  });

  it('calls onReset from the "Reset all" button', () => {
    const onReset = vi.fn();
    render(
      <SliderPanel parameters={DEFAULT_PARAMETERS} onParameterChange={vi.fn()} onReset={onReset} />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Reset all' }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('exposes each parameter hint via the info button, described for screen readers', () => {
    render(
      <SliderPanel parameters={DEFAULT_PARAMETERS} onParameterChange={vi.fn()} onReset={vi.fn()} />,
    );

    const infoButton = screen.getByRole('button', { name: 'About Contrast' });
    const describedBy = infoButton.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent(
      /stretches the tonal range/i,
    );
  });

  it('disables every slider while processing', () => {
    render(
      <SliderPanel
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
        onReset={vi.fn()}
        isProcessing
      />,
    );

    expect(screen.getByLabelText('Contrast')).toBeDisabled();
    expect(screen.getByLabelText('Denoise')).toBeDisabled();
  });
});
