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

  it('reads the tone as cool above the neutral temperature', () => {
    render(
      <SliderGroup
        keys={['temperature']}
        parameters={{ ...DEFAULT_PARAMETERS, temperature: 7000 }}
        onParameterChange={vi.fn()}
      />,
    );

    expect(screen.getByText(/Cool · 7000 K/)).toBeInTheDocument();
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

  it('shows the revert arrow only next to the active slider and calls onRevert', () => {
    const onRevert = vi.fn();
    const { rerender } = render(
      <SliderGroup
        keys={['contrast', 'exposure']}
        parameters={{ ...DEFAULT_PARAMETERS, contrast: 1.6 }}
        revert={{ key: 'contrast', value: 1 }}
        onRevert={onRevert}
        onParameterChange={vi.fn()}
      />,
    );

    const revert = screen.getByRole('button', { name: /revert contrast/i });
    expect(screen.queryByRole('button', { name: /revert exposure/i })).not.toBeInTheDocument();
    fireEvent.click(revert);
    expect(onRevert).toHaveBeenCalledTimes(1);

    // gone once the value is back at the revert target
    rerender(
      <SliderGroup
        keys={['contrast']}
        parameters={DEFAULT_PARAMETERS}
        revert={{ key: 'contrast', value: 1 }}
        onRevert={onRevert}
        onParameterChange={vi.fn()}
      />,
    );
    expect(screen.queryByRole('button', { name: /revert contrast/i })).not.toBeInTheDocument();
  });

  it('fills the track from the neutral value to the thumb', () => {
    render(
      <SliderGroup
        keys={['contrast', 'denoise']}
        parameters={{ ...DEFAULT_PARAMETERS, contrast: 2, denoise: 25 }}
        onParameterChange={vi.fn()}
      />,
    );

    // contrast: neutral 1.0 in 0.5-3.0 -> 0.2; value 2.0 -> 0.6
    const contrast = screen.getByLabelText('Contrast');
    expect(contrast.style.getPropertyValue('--fill-from')).toBe('0.2');
    expect(contrast.style.getPropertyValue('--fill-to')).toBe('0.6');
    // denoise: neutral 0 is the low end of 0-100
    const denoise = screen.getByLabelText('Denoise');
    expect(denoise.style.getPropertyValue('--fill-from')).toBe('0');
    expect(denoise.style.getPropertyValue('--fill-to')).toBe('0.25');
  });

  it('marks the neutral point only when it sits inside the range', () => {
    const { container } = render(
      <SliderGroup keys={['exposure']} parameters={DEFAULT_PARAMETERS} onParameterChange={vi.fn()} />,
    );
    expect(container.querySelectorAll('span.bg-line-strong')).toHaveLength(1);

    const { container: low } = render(
      <SliderGroup keys={['denoise']} parameters={DEFAULT_PARAMETERS} onParameterChange={vi.fn()} />,
    );
    expect(low.querySelectorAll('span.bg-line-strong')).toHaveLength(0);
  });

  it('draws an explanatory gradient track instead of the fill for white balance and colour', () => {
    render(
      <SliderGroup
        keys={['temperature', 'tint', 'exposure', 'saturation']}
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Temperature')).toHaveClass('slider-track-temperature');
    expect(screen.getByLabelText('Tint')).toHaveClass('slider-track-tint');
    expect(screen.getByLabelText('Exposure')).toHaveClass('slider-track-exposure');
    const saturation = screen.getByLabelText('Saturation');
    expect(saturation).toHaveClass('slider-track-colour');
    expect(saturation.style.getPropertyValue('--fill-to')).toBe('');
  });

  it('puts a slider back to neutral on double-click', () => {
    const onParameterChange = vi.fn();
    render(
      <SliderGroup
        keys={['exposure', 'temperature']}
        parameters={{ ...DEFAULT_PARAMETERS, exposure: 0.5, temperature: 4000 }}
        onParameterChange={onParameterChange}
      />,
    );

    fireEvent.doubleClick(screen.getByLabelText('Exposure'));
    expect(onParameterChange).toHaveBeenCalledWith('exposure', 0);
    fireEvent.doubleClick(screen.getByLabelText('Temperature'));
    expect(onParameterChange).toHaveBeenCalledWith('temperature', 6500);
  });

  it('ignores a double-click when already neutral or while processing', () => {
    const onParameterChange = vi.fn();
    const { rerender } = render(
      <SliderGroup keys={['exposure']} parameters={DEFAULT_PARAMETERS} onParameterChange={onParameterChange} />,
    );
    fireEvent.doubleClick(screen.getByLabelText('Exposure'));

    rerender(
      <SliderGroup
        keys={['exposure']}
        parameters={{ ...DEFAULT_PARAMETERS, exposure: 0.5 }}
        onParameterChange={onParameterChange}
        isProcessing
      />,
    );
    fireEvent.doubleClick(screen.getByLabelText('Exposure'));
    expect(onParameterChange).not.toHaveBeenCalled();
  });

  it('opens a parameter hint on tap and closes it on blur', () => {
    render(<SliderGroup keys={['contrast']} parameters={DEFAULT_PARAMETERS} onParameterChange={vi.fn()} />);

    const info = screen.getByRole('button', { name: 'About Contrast' });
    const tooltip = screen.getByRole('tooltip');
    expect(info).toHaveAttribute('aria-expanded', 'false');
    expect(tooltip).toHaveClass('opacity-0');

    fireEvent.click(info);
    expect(info).toHaveAttribute('aria-expanded', 'true');
    expect(tooltip).toHaveClass('opacity-100');

    fireEvent.blur(info);
    expect(tooltip).toHaveClass('opacity-0');
  });
});
