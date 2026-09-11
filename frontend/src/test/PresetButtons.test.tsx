import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { PresetButtons } from '@/components/PresetButtons';
import { DEFAULT_PARAMETERS, type Preset } from '@/types';

function preset(overrides: Partial<Preset>): Preset {
  return {
    presetId: 'system_nebula',
    name: 'Nebula',
    category: 'astronomy',
    description: 'raw english description',
    parameters: DEFAULT_PARAMETERS,
    author: 'system',
    isFavorite: false,
    ...overrides,
  };
}

describe('PresetButtons', () => {
  it('shows the translated name for a built-in preset, not the stored one', () => {
    render(
      <PresetButtons
        presets={[preset({ presetId: 'system_deep_field', name: 'STORED NAME' })]}
        onPresetApply={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Deep Field' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'STORED NAME' })).not.toBeInTheDocument();
  });

  it('keeps a user preset name as-is and offers a two-click delete', () => {
    const onPresetDelete = vi.fn();
    render(
      <PresetButtons
        presets={[preset({ presetId: 'user_x_ab12', name: 'My look', author: 'user' })]}
        onPresetApply={vi.fn()}
        onPresetDelete={onPresetDelete}
      />,
    );

    expect(screen.getByRole('button', { name: 'My look' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Delete preset My look' }));
    expect(onPresetDelete).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: 'Confirm delete preset My look' }));
    expect(onPresetDelete).toHaveBeenCalledWith('user_x_ab12');
  });

  it('reports which preset was applied', () => {
    const onPresetApply = vi.fn();
    render(<PresetButtons presets={[preset({})]} onPresetApply={onPresetApply} />);

    fireEvent.click(screen.getByRole('button', { name: 'Nebula' }));
    expect(onPresetApply).toHaveBeenCalledWith('system_nebula');
  });

  it('marks the active preset as pressed and highlighted', () => {
    render(
      <PresetButtons
        presets={[preset({})]}
        activePreset="system_nebula"
        onPresetApply={vi.fn()}
      />,
    );

    const chip = screen.getByRole('button', { name: 'Nebula' });
    expect(chip).toHaveAttribute('aria-pressed', 'true');
    expect(chip).toHaveClass('chip-active');
  });

  it('does not offer a delete affordance for a built-in preset even with a handler', () => {
    render(
      <PresetButtons
        presets={[preset({})]}
        onPresetApply={vi.fn()}
        onPresetDelete={vi.fn()}
      />,
    );

    expect(screen.queryByRole('button', { name: /delete preset/i })).not.toBeInTheDocument();
  });
});
