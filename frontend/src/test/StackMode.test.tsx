import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { StackMode } from '@/components/stacking/StackMode';

describe('StackMode', () => {
  it('marks the current mode as pressed and the other as not', () => {
    render(<StackMode mode="single" onModeChange={vi.fn()} />);

    const single = screen.getByRole('button', { name: /single image/i });
    const stack = screen.getByRole('button', { name: /multi-image stack/i });

    expect(single).toHaveAttribute('aria-pressed', 'true');
    expect(single.className).toContain('segmented-item-active');
    expect(stack).toHaveAttribute('aria-pressed', 'false');
    expect(stack.className).not.toContain('segmented-item-active');
  });

  it('reflects the stack mode as active when passed', () => {
    render(<StackMode mode="stack" onModeChange={vi.fn()} />);

    expect(screen.getByRole('button', { name: /single image/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(screen.getByRole('button', { name: /multi-image stack/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });

  it('calls onModeChange with the clicked mode', () => {
    const onModeChange = vi.fn();
    render(<StackMode mode="single" onModeChange={onModeChange} />);

    fireEvent.click(screen.getByRole('button', { name: /multi-image stack/i }));
    expect(onModeChange).toHaveBeenCalledWith('stack');

    fireEvent.click(screen.getByRole('button', { name: /single image/i }));
    expect(onModeChange).toHaveBeenCalledWith('single');
  });
});
