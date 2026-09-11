import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StackCalibrationPanel } from '@/components/stacking/StackCalibrationPanel';
import type { CalibrationSummary } from '@/types';

const EMPTY: CalibrationSummary = {
  frames: { dark: 0, flat: 0, bias: 0, darkFlat: 0 },
  cosmeticCorrection: true,
};

function file(name: string): File {
  return new File([new Uint8Array([1])], name, { type: 'image/png' });
}

describe('StackCalibrationPanel', () => {
  it('shows no count or clear button while a kind has zero frames', () => {
    render(
      <StackCalibrationPanel
        calibration={EMPTY}
        cosmeticCorrection={false}
        disabled={false}
        onAdd={vi.fn()}
        onClear={vi.fn()}
        onToggleCosmetic={vi.fn()}
      />,
    );

    expect(screen.queryByText(/0 frames/i)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /clear/i })).not.toBeInTheDocument();
    // one "Add" button per calibration kind
    expect(screen.getAllByRole('button', { name: /^add$/i })).toHaveLength(4);
  });

  it('shows the count and a clear button once a kind has frames, and calls onClear', () => {
    const onClear = vi.fn();
    render(
      <StackCalibrationPanel
        calibration={{ ...EMPTY, frames: { ...EMPTY.frames, dark: 3 } }}
        cosmeticCorrection={false}
        disabled={false}
        onAdd={vi.fn()}
        onClear={onClear}
        onToggleCosmetic={vi.fn()}
      />,
    );

    expect(screen.getByText('3 frames')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /clear/i }));
    expect(onClear).toHaveBeenCalledWith('dark');
  });

  it('opens the hidden file input when Add is clicked and forwards picked files', () => {
    const onAdd = vi.fn();
    const { container } = render(
      <StackCalibrationPanel
        calibration={EMPTY}
        cosmeticCorrection={false}
        disabled={false}
        onAdd={onAdd}
        onClear={vi.fn()}
        onToggleCosmetic={vi.fn()}
      />,
    );

    const addButtons = screen.getAllByRole('button', { name: /^add$/i });
    const clickSpy = vi.spyOn(HTMLInputElement.prototype, 'click');
    fireEvent.click(addButtons[1]); // flats
    expect(clickSpy).toHaveBeenCalled();
    clickSpy.mockRestore();

    const inputs = container.querySelectorAll<HTMLInputElement>('input[type="file"]');
    fireEvent.change(inputs[1], { target: { files: [file('flat.png')] } });
    expect(onAdd).toHaveBeenCalledWith('flat', [expect.any(File)]);
    expect(inputs[1].value).toBe('');
  });

  it('disables add/clear buttons and the cosmetic checkbox while disabled', () => {
    render(
      <StackCalibrationPanel
        calibration={{ ...EMPTY, frames: { ...EMPTY.frames, dark: 2 } }}
        cosmeticCorrection={true}
        disabled={true}
        onAdd={vi.fn()}
        onClear={vi.fn()}
        onToggleCosmetic={vi.fn()}
      />,
    );

    for (const button of screen.getAllByRole('button', { name: /^add$/i })) {
      expect(button).toBeDisabled();
    }
    expect(screen.getByRole('button', { name: /clear/i })).toBeDisabled();
    expect(screen.getByRole('checkbox', { name: /repair hot & dead pixels/i })).toBeDisabled();
  });

  it('disables the cosmetic checkbox when there is no dark/flat source, even if not globally disabled', () => {
    render(
      <StackCalibrationPanel
        calibration={EMPTY}
        cosmeticCorrection={false}
        disabled={false}
        onAdd={vi.fn()}
        onClear={vi.fn()}
        onToggleCosmetic={vi.fn()}
      />,
    );

    expect(screen.getByRole('checkbox', { name: /repair hot & dead pixels/i })).toBeDisabled();
  });

  it('enables and toggles the cosmetic checkbox once a dark or flat source exists', () => {
    const onToggleCosmetic = vi.fn();
    render(
      <StackCalibrationPanel
        calibration={{ ...EMPTY, frames: { ...EMPTY.frames, flat: 1 } }}
        cosmeticCorrection={false}
        disabled={false}
        onAdd={vi.fn()}
        onClear={vi.fn()}
        onToggleCosmetic={onToggleCosmetic}
      />,
    );

    const checkbox = screen.getByRole('checkbox', { name: /repair hot & dead pixels/i });
    expect(checkbox).not.toBeDisabled();
    fireEvent.click(checkbox);
    expect(onToggleCosmetic).toHaveBeenCalledWith(true);
  });
});
