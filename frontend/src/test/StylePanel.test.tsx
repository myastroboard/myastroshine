import { fireEvent, render, screen, within } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StylePanel } from '@/components/StylePanel';
import {
  DEFAULT_LOOK_CATALOG,
  DEFAULT_LOOK_PARAMETERS,
  type LookCatalog,
  type LookId,
} from '@/types';

const thumbnailUrl = (look: LookId | null) => `/thumb/${look ?? 'none'}`;

const NIGHT_CATALOG: LookCatalog = {
  scene: 'nightscape',
  groups: [
    { scene: 'nightscape', looks: ['galactic_core', 'blue_hour'] },
    ...DEFAULT_LOOK_CATALOG.groups,
  ],
};

/** The look choices only (the scene chips are radios too). */
function gallery(): HTMLElement[] {
  return within(screen.getByRole('radiogroup', { name: 'Finishing styles' })).getAllByRole('radio');
}

describe('StylePanel', () => {
  it('shows "No style" first and every look with its own thumbnail', () => {
    const { container } = render(
      <StylePanel
        look={DEFAULT_LOOK_PARAMETERS}
        catalog={DEFAULT_LOOK_CATALOG}
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    const radios = gallery();
    expect(radios.map((radio) => radio.textContent)).toEqual([
      'No style',
      'Vivid',
      'Soft glow',
      'Cinematic',
    ]);
    expect(radios[0]).toHaveAttribute('aria-checked', 'true');
    const sources = [...container.querySelectorAll('img')].map((img) => img.getAttribute('src'));
    expect(sources).toEqual([
      '/thumb/none',
      '/thumb/vivid',
      '/thumb/soft_glow',
      '/thumb/cinematic',
    ]);
    // No look chosen: no strength slider, the "no style" explanation instead.
    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
    expect(screen.getByText(/exactly as you edited it/)).toBeInTheDocument();
  });

  it('picks a look, or goes back to none', () => {
    const onLookChange = vi.fn();
    render(
      <StylePanel
        look={{ lookId: 'vivid', amount: 60 }}
        catalog={DEFAULT_LOOK_CATALOG}
        thumbnailUrl={thumbnailUrl}
        onLookChange={onLookChange}
        isProcessing={false}
      />,
    );

    fireEvent.click(screen.getByRole('radio', { name: 'Cinematic' }));
    fireEvent.click(screen.getByRole('radio', { name: 'No style' }));

    expect(onLookChange).toHaveBeenNthCalledWith(1, 'lookId', 'cinematic');
    expect(onLookChange).toHaveBeenNthCalledWith(2, 'lookId', null);
  });

  it('sets the strength of the chosen look', () => {
    const onLookChange = vi.fn();
    render(
      <StylePanel
        look={{ lookId: 'soft_glow', amount: 60 }}
        catalog={DEFAULT_LOOK_CATALOG}
        thumbnailUrl={thumbnailUrl}
        onLookChange={onLookChange}
        isProcessing={false}
      />,
    );

    expect(screen.getByRole('radio', { name: 'Soft glow' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByText(/dreamy glow/)).toBeInTheDocument();
    const slider = screen.getByRole('slider', { name: 'Strength' });
    expect(slider).toHaveValue('60');
    fireEvent.change(slider, { target: { value: '25' } });
    expect(onLookChange).toHaveBeenCalledWith('amount', 25);
  });

  it('locks the choices while a render is running', () => {
    render(
      <StylePanel
        look={{ lookId: 'vivid', amount: 60 }}
        catalog={DEFAULT_LOOK_CATALOG}
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing
      />,
    );

    for (const radio of gallery()) {
      expect(radio).toBeDisabled();
    }
    expect(screen.getByRole('slider')).toBeDisabled();
  });

  it('offers the night-landscape looks first and says why on a night landscape', () => {
    render(
      <StylePanel
        look={DEFAULT_LOOK_PARAMETERS}
        catalog={NIGHT_CATALOG}
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    expect(gallery().map((radio) => radio.textContent)).toEqual([
      'No style',
      'Galactic core',
      'Blue hour',
    ]);
    expect(screen.getByRole('radio', { name: 'Night landscape' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByText(/treat the sky and the ground separately/)).toBeInTheDocument();
  });

  it('says nothing about the landscape on an ordinary image', () => {
    render(
      <StylePanel
        look={DEFAULT_LOOK_PARAMETERS}
        catalog={DEFAULT_LOOK_CATALOG}
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    expect(screen.queryByText(/treat the sky and the ground/)).not.toBeInTheDocument();
  });

  it('switches group with the scene chips and keeps the pick', () => {
    const { rerender } = render(
      <StylePanel
        look={DEFAULT_LOOK_PARAMETERS}
        catalog={DEFAULT_LOOK_CATALOG}
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    fireEvent.click(screen.getByRole('radio', { name: 'Galaxy' }));
    expect(gallery().map((radio) => radio.textContent)).toEqual([
      'No style',
      'Deep field',
      'Warm core',
    ]);

    rerender(
      <StylePanel
        look={{ lookId: 'sparkle', amount: 60 }}
        catalog={DEFAULT_LOOK_CATALOG}
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );
    // The user's pick (Galaxy) wins over the look's own group until they change it.
    expect(screen.getByRole('radio', { name: 'Galaxy' })).toHaveAttribute('aria-checked', 'true');
  });

  it("opens on the chosen look's group", () => {
    render(
      <StylePanel
        look={{ lookId: 'sparkle', amount: 60 }}
        catalog={DEFAULT_LOOK_CATALOG}
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    expect(screen.getByRole('radio', { name: 'Star cluster' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    expect(screen.getByRole('radio', { name: 'Sparkle' })).toHaveAttribute('aria-checked', 'true');
  });

  it('falls back to the first group when the suggested one is missing', () => {
    render(
      <StylePanel
        look={DEFAULT_LOOK_PARAMETERS}
        catalog={{
          scene: 'nightscape',
          groups: [{ scene: 'nebula', looks: ['luminous'] }],
        }}
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    // One group: no chips, its looks shown.
    expect(screen.queryByRole('radiogroup', { name: 'Kind of photo' })).not.toBeInTheDocument();
    expect(gallery().map((radio) => radio.textContent)).toEqual(['No style', 'Luminous']);
  });

  it('shows only "No style" for an empty catalogue', () => {
    render(
      <StylePanel
        look={DEFAULT_LOOK_PARAMETERS}
        catalog={{ scene: 'general', groups: [] }}
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    expect(gallery().map((radio) => radio.textContent)).toEqual(['No style']);
  });
});
