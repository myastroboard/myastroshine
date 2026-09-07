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

describe('MilestoneTimeline', () => {
  it('shows the origin marker, the help text and the add button', () => {
    render(
      <MilestoneTimeline
        milestones={[origin]}
        activeId={origin.id}
        onCapture={vi.fn()}
        onRestore={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Restore Original' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Save milestone' })).toBeInTheDocument();
    expect(screen.getByText(/jump back to this point/i)).toBeInTheDocument();
  });

  it('captures a milestone when the add button is clicked', () => {
    const onCapture = vi.fn();
    render(
      <MilestoneTimeline
        milestones={[origin]}
        activeId={origin.id}
        onCapture={onCapture}
        onRestore={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Save milestone' }));
    expect(onCapture).toHaveBeenCalledTimes(1);
  });

  it('restores the milestone whose marker is clicked', () => {
    const onRestore = vi.fn();
    render(
      <MilestoneTimeline
        milestones={[origin, first]}
        activeId={origin.id}
        onCapture={vi.fn()}
        onRestore={onRestore}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Restore Milestone 1' }));
    expect(onRestore).toHaveBeenCalledWith(first);
  });

  it('marks the active milestone with aria-pressed', () => {
    render(
      <MilestoneTimeline
        milestones={[origin, first]}
        activeId={first.id}
        onCapture={vi.fn()}
        onRestore={vi.fn()}
      />,
    );

    expect(screen.getByRole('button', { name: 'Restore Milestone 1' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: 'Restore Original' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('disables every control while a job is processing', () => {
    render(
      <MilestoneTimeline
        milestones={[origin, first]}
        activeId={first.id}
        onCapture={vi.fn()}
        onRestore={vi.fn()}
        disabled
      />,
    );

    for (const button of screen.getAllByRole('button')) {
      expect(button).toBeDisabled();
    }
  });
});
