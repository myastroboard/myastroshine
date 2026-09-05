import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EditorInspector, type EditorInspectorProps } from '@/components/EditorInspector';
import { DEFAULT_GEOMETRY, DEFAULT_PARAMETERS } from '@/types';

function makeProps(overrides: Partial<EditorInspectorProps> = {}): EditorInspectorProps {
  return {
    activeStep: 'light',
    onStepChange: vi.fn(),
    parameters: DEFAULT_PARAMETERS,
    onParameterChange: vi.fn(),
    onResetSection: vi.fn(),
    onCurveChange: vi.fn(),
    onResetCurves: vi.fn(),
    isProcessing: false,
    start: {
      onAutoAstro: vi.fn(),
      autoAstroLoading: false,
      autoAstroError: null,
      presets: [],
      activePreset: undefined,
      onPresetApply: vi.fn(),
      onPresetDelete: vi.fn(),
      onResetAll: vi.fn(),
    },
    framing: {
      available: true,
      dimensions: { width: 4000, height: 3000 },
      geometry: DEFAULT_GEOMETRY,
      ratioFrac: null,
      dirty: false,
      onGeometryChange: vi.fn(),
      onRatioFracChange: vi.fn(),
      onApply: vi.fn(),
      onReset: vi.fn(),
    },
    stars: { enabled: false, onToggle: vi.fn(), sourceCount: null, loading: false },
    depth: {
      focalPoint: null,
      picking: false,
      onTogglePick: vi.fn(),
      onClear: vi.fn(),
      onOpenViewer: vi.fn(),
      error: null,
    },
    exportActions: {
      canSendToAstroDex: false,
      onDownload: vi.fn(),
      onSendToAstroDex: vi.fn(),
      onSaveAsPreset: vi.fn(),
    },
    ...overrides,
  };
}

describe('EditorInspector', () => {
  it('shows the light sliders on the light step', () => {
    render(<EditorInspector {...makeProps({ activeStep: 'light' })} />);

    expect(screen.getByLabelText('Exposure')).toBeInTheDocument();
    expect(screen.getByLabelText('Contrast')).toBeInTheDocument();
  });

  it('routes the header Reset to the active step params', () => {
    const onResetSection = vi.fn();
    render(<EditorInspector {...makeProps({ activeStep: 'colour', onResetSection })} />);

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(onResetSection).toHaveBeenCalledWith(['saturation', 'vibrance']);
  });

  it('advances to the next workflow step via the Next link', () => {
    const onStepChange = vi.fn();
    render(<EditorInspector {...makeProps({ activeStep: 'light', onStepChange })} />);

    fireEvent.click(screen.getByRole('button', { name: /Next: Curves/ }));
    expect(onStepChange).toHaveBeenCalledWith('curves');
  });

  it('commits the framing draft via Apply framing', () => {
    const onApply = vi.fn();
    render(
      <EditorInspector
        {...makeProps({
          activeStep: 'frame',
          framing: { ...makeProps().framing, dirty: true, onApply },
        })}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Apply framing' }));
    expect(onApply).toHaveBeenCalledTimes(1);
  });

  it('explains that framing is unavailable for a stacked composite', () => {
    render(
      <EditorInspector
        {...makeProps({
          activeStep: 'frame',
          framing: { ...makeProps().framing, available: false },
        })}
      />,
    );

    expect(screen.getByText(/stacked composite/i)).toBeInTheDocument();
  });

  it('toggles the star mask from the stars step', () => {
    const onToggle = vi.fn();
    render(
      <EditorInspector
        {...makeProps({
          activeStep: 'stars',
          stars: { enabled: false, onToggle, sourceCount: null, loading: false },
        })}
      />,
    );

    fireEvent.click(screen.getByRole('checkbox', { name: /show star mask/i }));
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it('opens the Depth Shift viewer from the depth step', () => {
    const onOpenViewer = vi.fn();
    render(
      <EditorInspector
        {...makeProps({
          activeStep: 'depth',
          depth: { ...makeProps().depth, onOpenViewer },
        })}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: /Open Depth Shift viewer/i }));
    expect(onOpenViewer).toHaveBeenCalledTimes(1);
  });
});
