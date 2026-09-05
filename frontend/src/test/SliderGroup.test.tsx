import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SliderGroup } from '@/components/SliderGroup';
import { DEFAULT_PARAMETERS } from '@/types';

describe('SliderGroup', () => {
  it('renders one labelled slider per key and reports changes with the key and value', () => {
    const onParameterChange = vi.fn();
    render(
      <SliderGroup
        keys={['exposure', 'contrast']}
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={onParameterChange}
      />,
    );

    fireEvent.change(screen.getByLabelText('Exposure'), { target: { value: '0.3' } });
    expect(onParameterChange).toHaveBeenCalledWith('exposure', 0.3);
  });

  it('exposes each parameter hint via the info button, described for screen readers', () => {
    render(
      <SliderGroup
        keys={['contrast']}
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
      />,
    );

    const infoButton = screen.getByRole('button', { name: 'About Contrast' });
    const describedBy = infoButton.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent(/stretches the tonal range/i);
  });

  it('disables every slider while processing', () => {
    render(
      <SliderGroup
        keys={['exposure', 'contrast']}
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
        isProcessing
      />,
    );

    expect(screen.getByLabelText('Exposure')).toBeDisabled();
    expect(screen.getByLabelText('Contrast')).toBeDisabled();
  });

  it('skips a key with no numeric bounds', () => {
    render(
      <SliderGroup
        keys={['depthShiftIntensity']}
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
      />,
    );

    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
  });
});
