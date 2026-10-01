import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { MilestoneTimeline } from '@/components/MilestoneTimeline';
import type { Milestone } from '@/hooks/useMilestones';
import { DEFAULT_PARAMETERS } from '@/types';

const origin: Milestone = {
  id: 's-0',
  kind: 'origin',
  ordinal: 0,
  parameters: DEFAULT_PARAMETERS,
  focalPoint: null,
  createdAt: 0,
};

const first: Milestone = {
  id: 's-1',
  kind: 'saved',
  ordinal: 1,
  parameters: { ...DEFAULT_PARAMETERS, exposure: 0.3 },
  focalPoint: null,
  createdAt: 1,
};

function renderTimeline(
  milestones: Milestone[],
  activeId: string | null,
  extra: Partial<{ onCapture: () => void; onRestore: (m: Milestone) => void; disabled: boolean }> = {},
) {
  return render(
    <MilestoneTimeline
      milestones={milestones}
      activeId={activeId}
      onCapture={extra.onCapture ?? vi.fn()}
      onRestore={extra.onRestore ?? vi.fn()}
      disabled={extra.disabled}
    />,
  );
}

describe('MilestoneTimeline', () => {
  it('explains what go-back points are for, next to the original photo and the add button', () => {
    renderTimeline([origin], origin.id);

    expect(screen.getByText('Go-back points')).toBeInTheDocument();
    expect(screen.getByText(/one click brings you back/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Go back to Original photo' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark this point' })).toBeInTheDocument();
  });

  it('captures a point when the add button is clicked', () => {
    const onCapture = vi.fn();
    renderTimeline([origin], origin.id, { onCapture });

    fireEvent.click(screen.getByRole('button', { name: 'Mark this point' }));
    expect(onCapture).toHaveBeenCalledTimes(1);
  });

  it('names a point after the steps that changed since the previous one', () => {
    const second: Milestone = {
      ...first,
      id: 's-2',
      ordinal: 2,
      parameters: { ...first.parameters, saturation: 1.4, denoise: 30, starReduction: 20 },
    };
    renderTimeline([origin, first, second], second.id);

    expect(screen.getByRole('button', { name: 'Go back to 1 - Light' })).toHaveTextContent(
      '1 - Light',
    );
    // Three steps changed: the chip spells out two, the full name keeps all.
    const chip = screen.getByRole('button', { name: 'Go back to 2 - Colour, Detail, Stars' });
    expect(chip).toHaveTextContent('2 - Colour, Detail, ...');
    expect(chip).toHaveAttribute('title', '2 - Colour, Detail, Stars');
  });

  it('falls back to a plain number when a point changed nothing', () => {
    const same: Milestone = { ...first, id: 's-2', ordinal: 2 };
    renderTimeline([origin, first, same], null);

    expect(screen.getByRole('button', { name: 'Go back to Point 2' })).toBeInTheDocument();
  });

  it('restores the point whose chip is clicked', () => {
    const onRestore = vi.fn();
    renderTimeline([origin, first], origin.id, { onRestore });

    fireEvent.click(screen.getByRole('button', { name: 'Go back to 1 - Light' }));
    expect(onRestore).toHaveBeenCalledWith(first);
  });

  it('marks the active point with aria-pressed', () => {
    renderTimeline([origin, first], first.id);

    expect(screen.getByRole('button', { name: 'Go back to 1 - Light' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Go back to Original photo' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('confirms a just-created point and how to use it', () => {
    renderTimeline([origin, first], first.id);

    expect(screen.getByText(/Point 1 created - click it any time/)).toBeInTheDocument();
    expect(screen.queryByText(/one click brings you back/i)).not.toBeInTheDocument();
  });

  it('highlights the add button while the current edit is held by no point', () => {
    const { rerender } = renderTimeline([origin, first], null);
    expect(screen.getByRole('button', { name: 'Mark this point' })).toHaveClass('bg-accent-wash');

    rerender(
      <MilestoneTimeline
        milestones={[origin, first]}
        activeId={first.id}
        onCapture={vi.fn()}
        onRestore={vi.fn()}
      />,
    );
    expect(screen.getByRole('button', { name: 'Mark this point' })).not.toHaveClass(
      'bg-accent-wash',
    );
  });

  it('disables every control while a job is processing', () => {
    renderTimeline([origin, first], first.id, { disabled: true });

    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled();
    }
  });
});
