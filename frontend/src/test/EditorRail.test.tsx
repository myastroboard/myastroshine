import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EditorRail } from '@/components/EditorRail';
import { DEFAULT_PARAMETERS } from '@/types';

describe('EditorRail', () => {
  it('lists the workflow steps from start to export', () => {
    render(
      <EditorRail
        activeStep="light"
        onStepChange={vi.fn()}
        parameters={DEFAULT_PARAMETERS}
        focalPoint={null}
      />,
    );

    const labels = screen.getAllByRole('button').map((button) => button.textContent);
    expect(labels[0]).toContain('Start');
    expect(labels[1]).toContain('Framing');
    expect(labels.at(-1)).toContain('Export');
  });

  it('changes the active step on click', () => {
    const onStepChange = vi.fn();
    render(
      <EditorRail
        activeStep="light"
        onStepChange={onStepChange}
        parameters={DEFAULT_PARAMETERS}
        focalPoint={null}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Stars/ }));
    expect(onStepChange).toHaveBeenCalledWith('stars');
  });

  it('marks the active step with aria-current', () => {
    render(
      <EditorRail
        activeStep="detail"
        onStepChange={vi.fn()}
        parameters={DEFAULT_PARAMETERS}
        focalPoint={null}
      />,
    );

    expect(screen.getByRole('button', { name: /Detail/ })).toHaveAttribute('aria-current', 'step');
  });

  it('flags a step whose parameters differ from the default', () => {
    render(
      <EditorRail
        activeStep="light"
        onStepChange={vi.fn()}
        parameters={{ ...DEFAULT_PARAMETERS, exposure: 0.4 }}
        focalPoint={null}
      />,
    );

    const lightButton = screen.getByRole('button', { name: /Light/ });
    expect(lightButton.querySelector('[aria-label="changed from default"]')).toBeInTheDocument();
  });

  it('flags the Depth step once a focal point is set', () => {
    render(
      <EditorRail
        activeStep="light"
        onStepChange={vi.fn()}
        parameters={DEFAULT_PARAMETERS}
        focalPoint={{ x: 0.5, y: 0.5 }}
      />,
    );

    const depthButton = screen.getByRole('button', { name: /Depth/ });
    expect(depthButton.querySelector('[aria-label="changed from default"]')).toBeInTheDocument();
  });
});
