import { render } from '@testing-library/react';
import type { ComponentType } from 'react';
import { describe, expect, it } from 'vitest';

import * as icons from '@/components/icons';

// Every runtime export is an icon component (IconProps is a type only).
const entries = Object.entries(icons) as [string, ComponentType<icons.IconProps>][];

describe('icons', () => {
  it('exports the line-icon family', () => {
    expect(entries.length).toBeGreaterThan(20);
  });

  it.each(entries)('%s draws a decorative 24px currentColor line icon', (_name, Icon) => {
    const { container } = render(<Icon />);
    const svg = container.querySelector('svg')!;

    expect(svg).toHaveAttribute('viewBox', '0 0 24 24');
    expect(svg).toHaveAttribute('stroke', 'currentColor');
    expect(svg).toHaveAttribute('aria-hidden');
    // The default size applies when the caller passes none.
    expect(svg).toHaveClass('h-4', 'w-4');
  });

  it('takes its size and colour from the caller', () => {
    const { container } = render(<icons.StarIcon className="h-6 w-6 text-accent" />);

    expect(container.querySelector('svg')).toHaveClass('h-6', 'w-6', 'text-accent');
    expect(container.querySelector('svg')).not.toHaveClass('h-4');
  });
});
