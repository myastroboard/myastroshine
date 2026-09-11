import { fireEvent, render, screen } from '@testing-library/react';
import type { ComponentProps } from 'react';
import { describe, expect, it, vi } from 'vitest';

import { FramingControls } from '@/components/FramingControls';
import { baseAspectRatio, rectForRatio } from '@/services/framingGeometry';
import { DEFAULT_GEOMETRY } from '@/types';
import type { Dimensions } from '@/types';

const dimensions: Dimensions = { width: 1600, height: 900 }; // 16:9

function renderControls(overrides: Partial<ComponentProps<typeof FramingControls>> = {}) {
  const onGeometryChange = vi.fn();
  const onRatioFracChange = vi.fn();
  const onApply = vi.fn();
  const onReset = vi.fn();
  const utils = render(
    <FramingControls
      dimensions={dimensions}
      geometry={DEFAULT_GEOMETRY}
      ratioFrac={null}
      dirty={false}
      onGeometryChange={onGeometryChange}
      onRatioFracChange={onRatioFracChange}
      onApply={onApply}
      onReset={onReset}
      {...overrides}
    />,
  );
  return { ...utils, onGeometryChange, onRatioFracChange, onApply, onReset };
}

describe('FramingControls', () => {
  it('renders every ratio chip with "Free" active by default', () => {
    renderControls();

    ['Free', 'Original', '1:1', '16:9', '3:2', '4:5', '5:4'].forEach((label) => {
      expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: 'Free' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: '1:1' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('marks a ratio chip active once its fraction matches the current lock', () => {
    const baseAspect = baseAspectRatio(dimensions, DEFAULT_GEOMETRY.rotateQuarters);
    const oneToOneFrac = 1 / baseAspect;
    renderControls({ ratioFrac: oneToOneFrac });

    expect(screen.getByRole('button', { name: '1:1' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByRole('button', { name: 'Free' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('clears the ratio lock without touching the crop rect when "Free" is chosen', () => {
    const { onGeometryChange, onRatioFracChange } = renderControls({ ratioFrac: 1 });

    fireEvent.click(screen.getByRole('button', { name: 'Free' }));

    expect(onRatioFracChange).toHaveBeenCalledWith(null);
    expect(onGeometryChange).not.toHaveBeenCalled();
  });

  it('applies a ratio chip choice as a new fraction lock and crop rect', () => {
    const { onGeometryChange, onRatioFracChange } = renderControls();

    fireEvent.click(screen.getByRole('button', { name: '1:1' }));

    const baseAspect = baseAspectRatio(dimensions, DEFAULT_GEOMETRY.rotateQuarters);
    const { ratioFrac, rect } = rectForRatio(1, baseAspect);
    expect(onRatioFracChange).toHaveBeenCalledWith(ratioFrac);
    expect(onGeometryChange).toHaveBeenCalledWith({
      ...DEFAULT_GEOMETRY,
      cropX: rect!.x,
      cropY: rect!.y,
      cropW: rect!.w,
      cropH: rect!.h,
    });
  });

  it('reports a straighten change and shows the rounded degree readout', () => {
    const { onGeometryChange } = renderControls({
      geometry: { ...DEFAULT_GEOMETRY, straighten: 12.34 },
    });

    expect(screen.getByText('12.3°')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Straighten'), { target: { value: '-5.5' } });
    expect(onGeometryChange).toHaveBeenCalledWith({
      ...DEFAULT_GEOMETRY,
      straighten: -5.5,
    });
  });

  it('rotates 90 degrees, clearing any ratio lock and resetting the crop', () => {
    const { onGeometryChange, onRatioFracChange } = renderControls({
      geometry: { ...DEFAULT_GEOMETRY, rotateQuarters: 1, cropX: 0.1, cropY: 0.2, cropW: 0.5, cropH: 0.5 },
      ratioFrac: 1,
    });

    fireEvent.click(screen.getByRole('button', { name: 'Rotate 90°' }));

    expect(onRatioFracChange).toHaveBeenCalledWith(null);
    expect(onGeometryChange).toHaveBeenCalledWith({
      ...DEFAULT_GEOMETRY,
      rotateQuarters: 2,
      cropX: 0,
      cropY: 0,
      cropW: 1,
      cropH: 1,
    });
  });

  it('wraps rotation from 3 back to 0', () => {
    const { onGeometryChange } = renderControls({
      geometry: { ...DEFAULT_GEOMETRY, rotateQuarters: 3 },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Rotate 90°' }));

    expect(onGeometryChange).toHaveBeenCalledWith(
      expect.objectContaining({ rotateQuarters: 0 }),
    );
  });

  it('toggles horizontal flip and mirrors the crop X position', () => {
    const { onGeometryChange } = renderControls({
      geometry: { ...DEFAULT_GEOMETRY, cropX: 0.1, cropW: 0.3 },
    });

    const flipH = screen.getByRole('button', { name: 'Flip H' });
    expect(flipH).toHaveAttribute('aria-pressed', 'false');

    fireEvent.click(flipH);

    expect(onGeometryChange).toHaveBeenCalledWith({
      ...DEFAULT_GEOMETRY,
      cropX: 0.6000000000000001, // 1 - 0.1 - 0.3 (float arithmetic)
      cropW: 0.3,
      flipHorizontal: true,
    });
  });

  it('toggles vertical flip and mirrors the crop Y position', () => {
    const { onGeometryChange } = renderControls({
      geometry: { ...DEFAULT_GEOMETRY, cropY: 0.2, cropH: 0.4, flipVertical: true },
    });

    const flipV = screen.getByRole('button', { name: 'Flip V' });
    expect(flipV).toHaveAttribute('aria-pressed', 'true');

    fireEvent.click(flipV);

    expect(onGeometryChange).toHaveBeenCalledWith({
      ...DEFAULT_GEOMETRY,
      cropY: 0.4, // 1 - 0.2 - 0.4
      cropH: 0.4,
      flipVertical: false,
    });
  });

  it('disables Apply while clean and enables it once the framing is dirty', () => {
    const { onApply, rerender } = renderControls({ dirty: false });

    expect(screen.getByRole('button', { name: 'Apply framing' })).toBeDisabled();

    rerender(
      <FramingControls
        dimensions={dimensions}
        geometry={DEFAULT_GEOMETRY}
        ratioFrac={null}
        dirty
        onGeometryChange={vi.fn()}
        onRatioFracChange={vi.fn()}
        onApply={onApply}
        onReset={vi.fn()}
      />,
    );

    const apply = screen.getByRole('button', { name: 'Apply framing' });
    expect(apply).toBeEnabled();
    fireEvent.click(apply);
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('clears the ratio lock and resets the framing from the Reset button', () => {
    const { onReset, onRatioFracChange } = renderControls({ ratioFrac: 1 });

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));

    expect(onRatioFracChange).toHaveBeenCalledWith(null);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it('disables every control while processing', () => {
    renderControls({ isProcessing: true, dirty: true });

    expect(screen.getByRole('button', { name: 'Free' })).toBeDisabled();
    expect(screen.getByLabelText('Straighten')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Rotate 90°' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Flip H' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Flip V' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Apply framing' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Reset' })).toBeDisabled();
  });
});
