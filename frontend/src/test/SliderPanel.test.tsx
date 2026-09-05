import { fireEvent, render, screen, within } from '@testing-library/react';
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
        onResetSection={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText('Contrast'), { target: { value: '1.8' } });

    expect(onParameterChange).toHaveBeenCalledWith('contrast', 1.8);
  });

  it('calls onReset from the "Reset all" button', () => {
    const onReset = vi.fn();
    render(
      <SliderPanel
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
        onReset={onReset}
        onResetSection={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Reset all' }));

    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('exposes each parameter hint via the info button, described for screen readers', () => {
    render(
      <SliderPanel
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
        onReset={vi.fn()}
        onResetSection={vi.fn()}
      />,
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
        onResetSection={vi.fn()}
        isProcessing
      />,
    );

    // Contrast (Light) and Saturation (Colour) - both open-by-default sections.
    expect(screen.getByLabelText('Contrast')).toBeDisabled();
    expect(screen.getByLabelText('Saturation')).toBeDisabled();
  });

  it('collapses Detail/Stars/Depth by default but keeps Light/Colour open', () => {
    render(
      <SliderPanel
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
        onReset={vi.fn()}
        onResetSection={vi.fn()}
      />,
    );

    expect(screen.getByLabelText('Contrast')).toBeVisible();
    expect(screen.getByLabelText('Saturation')).toBeVisible();
    expect(screen.getByLabelText('Denoise')).not.toBeVisible();

    fireEvent.click(screen.getByText('Detail'));
    expect(screen.getByLabelText('Denoise')).toBeVisible();
  });

  it('resets only a section\'s own parameters via its "Reset" button', () => {
    const onResetSection = vi.fn();
    render(
      <SliderPanel
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
        onReset={vi.fn()}
        onResetSection={onResetSection}
      />,
    );

    const lightSection = screen.getByText('Light').closest('details') as HTMLElement;
    fireEvent.click(within(lightSection).getByRole('button', { name: 'Reset' }));

    expect(onResetSection).toHaveBeenCalledWith(['contrast', 'brightness', 'highlights', 'shadows']);
  });

  it('omits the star mask toggle when no handler is given', () => {
    render(
      <SliderPanel
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
        onReset={vi.fn()}
        onResetSection={vi.fn()}
      />,
    );

    expect(screen.queryByText('Show star mask')).not.toBeInTheDocument();
  });

  it('reports the star mask toggle and shows the detected source count', () => {
    const onStarMaskToggle = vi.fn();
    render(
      <SliderPanel
        parameters={DEFAULT_PARAMETERS}
        onParameterChange={vi.fn()}
        onReset={vi.fn()}
        onResetSection={vi.fn()}
        starMaskEnabled
        onStarMaskToggle={onStarMaskToggle}
        starMaskSourceCount={42}
      />,
    );

    fireEvent.click(screen.getByText('Stars')); // Stars is collapsed by default

    expect(screen.getByText('42 sources')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: /show star mask/i }));
    expect(onStarMaskToggle).toHaveBeenCalledWith(false);
  });
});
