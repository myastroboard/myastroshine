import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StylePanel } from '@/components/StylePanel';
import { DEFAULT_LOOK_PARAMETERS, GENERAL_LOOK_CATALOG, type LookId } from '@/types';

const thumbnailUrl = (look: LookId | null) => `/thumb/${look ?? 'none'}`;

describe('StylePanel', () => {
  it('shows "No style" first and every look with its own thumbnail', () => {
    const { container } = render(
      <StylePanel
        look={DEFAULT_LOOK_PARAMETERS}
        looks={GENERAL_LOOK_CATALOG.looks}
        scene="general"
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    const radios = screen.getAllByRole('radio');
    expect(radios.map((radio) => radio.textContent)).toEqual([
      'No style',
      'Vivid',
      'Soft glow',
      'Cinematic',
    ]);
    expect(radios[0]).toHaveAttribute('aria-checked', 'true');
    const sources = [...container.querySelectorAll('img')].map((img) => img.getAttribute('src'));
    expect(sources).toEqual(['/thumb/none', '/thumb/vivid', '/thumb/soft_glow', '/thumb/cinematic']);
    // No look chosen: no strength slider, the "no style" explanation instead.
    expect(screen.queryByRole('slider')).not.toBeInTheDocument();
    expect(screen.getByText(/exactly as you edited it/)).toBeInTheDocument();
  });

  it('picks a look, or goes back to none', () => {
    const onLookChange = vi.fn();
    render(
      <StylePanel
        look={{ lookId: 'vivid', amount: 60 }}
        looks={GENERAL_LOOK_CATALOG.looks}
        scene="general"
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
        looks={GENERAL_LOOK_CATALOG.looks}
        scene="general"
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
        looks={GENERAL_LOOK_CATALOG.looks}
        scene="general"
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing
      />,
    );

    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).toBeDisabled();
    }
    expect(screen.getByRole('slider')).toBeDisabled();
  });

  it('offers the night-landscape looks first and says why on a night landscape', () => {
    render(
      <StylePanel
        look={DEFAULT_LOOK_PARAMETERS}
        looks={['galactic_core', 'blue_hour', 'vivid', 'soft_glow', 'cinematic']}
        scene="nightscape"
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    expect(screen.getAllByRole('radio').map((radio) => radio.textContent)).toEqual([
      'No style',
      'Galactic core',
      'Blue hour',
      'Vivid',
      'Soft glow',
      'Cinematic',
    ]);
    expect(screen.getByText(/treat the sky and the ground separately/)).toBeInTheDocument();
  });

  it('says nothing about the landscape on an ordinary image', () => {
    render(
      <StylePanel
        look={DEFAULT_LOOK_PARAMETERS}
        looks={GENERAL_LOOK_CATALOG.looks}
        scene="general"
        thumbnailUrl={thumbnailUrl}
        onLookChange={vi.fn()}
        isProcessing={false}
      />,
    );

    expect(screen.queryByText(/treat the sky and the ground/)).not.toBeInTheDocument();
  });
});
