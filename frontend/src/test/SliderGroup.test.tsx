import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { SliderGroup } from '@/components/SliderGroup';
import { DEFAULT_PARAMETERS, type SliderParameterKey } from '@/types';

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
        keys={['bogusKey' as SliderParameterKey]}
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
      />,
    );

    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
  });

  it('snaps temperature to the standard Kelvin stops and reports the tone', () => {
    const onParameterChange = vi.fn();
    render(
      <SliderGroup
        keys={['temperature']}
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={onParameterChange}
      />,
    );

    // default 6500 K reads as neutral, thumb at that stop's index (5 of 0..8)
    const slider = screen.getByLabelText('Temperature');
    expect(slider).toHaveValue('5');
    expect(screen.getByText(/Neutral · 6500 K/)).toBeInTheDocument();

    // moving one stop warmer emits the standard Kelvin value, not the raw index
    fireEvent.change(slider, { target: { value: '4' } });
    expect(onParameterChange).toHaveBeenCalledWith('temperature', 6000);
  });

  it('parks the temperature thumb on the nearest stop for a non-standard value', () => {
    render(
      <SliderGroup
        keys={['temperature']}
        parameters={{ ...DEFAULT_PARAMETERS, temperature: 6200 }}
        onParameterChange={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Temperature')).toHaveValue('4'); // nearest: 6000 K
    expect(screen.getByText(/Warm · 6200 K/)).toBeInTheDocument(); // shows the real value
  });
});
