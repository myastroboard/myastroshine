import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EditorRail } from '@/components/EditorRail';
import { DEFAULT_PARAMETERS, DEFAULT_STACK_PARAMETERS, type EditorStepId } from '@/types';

function renderRail(
  props: Partial<{
    activeStep: EditorStepId;
    onStepChange: () => void;
    parameters: typeof DEFAULT_PARAMETERS;
    focalPoint: { x: number; y: number } | null;
    isStack: boolean;
  }> = {},
) {
  return render(
    <EditorRail
      activeStep={props.activeStep ?? 'light'}
      onStepChange={props.onStepChange ?? vi.fn()}
      parameters={props.parameters ?? DEFAULT_PARAMETERS}
      focalPoint={props.focalPoint ?? null}
      isStack={props.isStack ?? false}
    />,
  );
}

describe('EditorRail', () => {
  it('lists the workflow steps from start to export', () => {
    renderRail();

    const labels = screen.getAllByRole('button').map((button) => button.textContent);
    expect(labels[0]).toContain('Start');
    expect(labels[1]).toContain('Framing');
    expect(labels.at(-1)).toContain('Export');
  });

  it('hides the Stack step for an ordinary image and shows it for a composite', () => {
    const { rerender } = renderRail({ isStack: false });
    expect(screen.queryByRole('button', { name: /Stack/ })).not.toBeInTheDocument();

    rerender(
      <EditorRail
        activeStep="light"
        onStepChange={vi.fn()}
        parameters={DEFAULT_PARAMETERS}
        focalPoint={null}
        isStack
      />,
    );
    expect(screen.getByRole('button', { name: /Stack/ })).toBeInTheDocument();
  });

  it('changes the active step on click', () => {
    const onStepChange = vi.fn();
    renderRail({ onStepChange });

    fireEvent.click(screen.getByRole('button', { name: /Stars/ }));
    expect(onStepChange).toHaveBeenCalledWith('stars');
  });

  it('marks the active step with aria-current', () => {
    renderRail({ activeStep: 'detail' });

    expect(screen.getByRole('button', { name: /Detail/ })).toHaveAttribute('aria-current', 'step');
  });

  it('flags a step whose parameters differ from the default', () => {
    renderRail({ parameters: { ...DEFAULT_PARAMETERS, exposure: 0.4 } });

    const lightButton = screen.getByRole('button', { name: /Light/ });
    expect(lightButton.querySelector('[aria-label="changed from default"]')).toBeInTheDocument();
  });

  it('flags the Stack step once its controls leave the default', () => {
    renderRail({
      isStack: true,
      parameters: {
        ...DEFAULT_PARAMETERS,
        stack: { ...DEFAULT_STACK_PARAMETERS, backgroundExtraction: 0 },
      },
    });

    const stackButton = screen.getByRole('button', { name: /Stack/ });
    expect(stackButton.querySelector('[aria-label="changed from default"]')).toBeInTheDocument();
  });

  it('flags the Depth step once a focal point is set', () => {
    renderRail({ focalPoint: { x: 0.5, y: 0.5 } });

    const depthButton = screen.getByRole('button', { name: /3D effect/ });
    expect(depthButton.querySelector('[aria-label="changed from default"]')).toBeInTheDocument();
  });

  it('groups the steps under phase headings with a plain-language subtitle each', () => {
    renderRail();

    expect(screen.getByText('Prepare')).toBeInTheDocument();
    expect(screen.getByText('Enhance')).toBeInTheDocument();
    expect(screen.getByText('Finish')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Light/ })).toHaveAccessibleDescription(
      'Brightness and contrast',
    );
  });

  it('draws an icon, not a number, for every step', () => {
    renderRail();

    for (const button of screen.getAllByRole('button')) {
      expect(button.querySelector('svg')).toBeInTheDocument();
      // The old rail numbered the steps 1-8; no badge carries a bare number now.
      const badges = Array.from(button.querySelectorAll('span')).map((span) => span.textContent);
      expect(badges).not.toContainEqual(expect.stringMatching(/^\d+$/));
    }
  });

  it('scrolls the active step into view in the phone tab bar, not on desktop', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    const matchMedia = vi.fn().mockReturnValue({ matches: true });
    vi.stubGlobal('matchMedia', matchMedia);

    const { rerender } = renderRail({ activeStep: 'light' });
    expect(scrollIntoView).toHaveBeenCalledTimes(1);

    matchMedia.mockReturnValue({ matches: false });
    rerender(
      <EditorRail
        activeStep="stars"
        onStepChange={vi.fn()}
        parameters={DEFAULT_PARAMETERS}
        focalPoint={null}
        isStack={false}
      />,
    );
    expect(scrollIntoView).toHaveBeenCalledTimes(1);
    vi.unstubAllGlobals();
  });
});
