import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EditorInspector, type EditorInspectorProps } from '@/components/EditorInspector';
import {
  DEFAULT_GEOMETRY,
  DEFAULT_PARAMETERS,
  type DenoiseEngine,
  type StarlessEngine,
} from '@/types';

function makeProps(overrides: Partial<EditorInspectorProps> = {}): EditorInspectorProps {
  return {
    activeStep: 'light',
    onStepChange: vi.fn(),
    parameters: DEFAULT_PARAMETERS,
    onParameterChange: vi.fn(),
    sliderRevert: null,
    onSliderRevert: vi.fn(),
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
    stack: { available: false, onParameterChange: vi.fn(), onReset: vi.fn() },
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
    stars: {
      enabled: false,
      onToggle: vi.fn(),
      sourceCount: null,
      loading: false,
      engines: ['classic'] as StarlessEngine[],
      engine: 'classic' as StarlessEngine,
      onEngineChange: vi.fn(),
    },
    denoise: {
      engines: ['classic'] as DenoiseEngine[],
      engine: 'classic' as DenoiseEngine,
      onEngineChange: vi.fn(),
    },
    depth: {
      focalPoint: null,
      picking: false,
      onTogglePick: vi.fn(),
      onClear: vi.fn(),
      onOpenViewer: vi.fn(),
      error: null,
    },
    exportActions: {
      canReturnToAstroDex: false,
      astrodexObjectName: null,
      astrodexReturning: false,
      astrodexReturned: false,
      astrodexError: null,
      defaultFilename: 'photo_myastroshine',
      onDownload: vi.fn(),
      onReturnToAstroDex: vi.fn(),
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

  it('groups reduce, remove and detection on the stars step', () => {
    const onToggle = vi.fn();
    render(
      <EditorInspector
        {...makeProps({
          activeStep: 'stars',
          stars: {
            enabled: false,
            onToggle,
            sourceCount: null,
            loading: false,
            engines: ['classic'] as StarlessEngine[],
            engine: 'classic' as StarlessEngine,
            onEngineChange: vi.fn(),
          },
        })}
      />,
    );

    // reduce + remove + detection sliders all live in the one step
    expect(screen.getByLabelText('Star reduction')).toBeInTheDocument();
    expect(screen.getByLabelText('Remove stars')).toBeInTheDocument();
    expect(screen.getByLabelText('Bring stars back')).toBeInTheDocument();
    expect(screen.getByLabelText('Star sensitivity')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: /show star mask/i }));
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it('routes the header Reset on the stars step across all of its params', () => {
    const onResetSection = vi.fn();
    render(<EditorInspector {...makeProps({ activeStep: 'stars', onResetSection })} />);

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(onResetSection).toHaveBeenCalledWith([
      'starReduction',
      'starRemoval',
      'starRecombine',
      'starSensitivity',
      'starMaxSize',
    ]);
  });

  it('shows the linear post-stack controls on the stack step', () => {
    const onParameterChange = vi.fn();
    render(
      <EditorInspector
        {...makeProps({
          activeStep: 'stack',
          stack: { available: true, onParameterChange, onReset: vi.fn() },
        })}
      />,
    );

    expect(screen.getByLabelText('Stretch')).toBeInTheDocument();
    expect(screen.getByLabelText('Background extraction')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('checkbox', { name: /Colour calibration/i }));
    expect(onParameterChange).toHaveBeenCalledWith('colorCalibration', false);
  });

  it('switches the stretch method on the stack step, adaptive by default', () => {
    const onParameterChange = vi.fn();
    render(
      <EditorInspector
        {...makeProps({
          activeStep: 'stack',
          stack: { available: true, onParameterChange, onReset: vi.fn() },
        })}
      />,
    );

    const group = screen.getByRole('radiogroup', { name: 'Stretch method' });
    expect(group).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: 'Adaptive' })).toHaveAttribute(
      'aria-checked',
      'true',
    );

    fireEvent.click(screen.getByRole('radio', { name: 'Classic' }));
    expect(onParameterChange).toHaveBeenCalledWith('stretchMode', 'classic');
  });

  it('routes the header Reset on the stack step to its own reset', () => {
    const onReset = vi.fn();
    render(
      <EditorInspector
        {...makeProps({
          activeStep: 'stack',
          parameters: {
            ...DEFAULT_PARAMETERS,
            stack: { ...DEFAULT_PARAMETERS.stack, stretch: 0.9 },
          },
          stack: { available: true, onParameterChange: vi.fn(), onReset },
        })}
      />,
    );

    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
    expect(onReset).toHaveBeenCalledTimes(1);
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

  describe('start step', () => {
    it('runs Auto Astro and resets all adjustments', () => {
      const props = makeProps({ activeStep: 'start' });
      render(<EditorInspector {...props} />);

      fireEvent.click(screen.getByRole('button', { name: 'Auto Astro' }));
      fireEvent.click(screen.getByRole('button', { name: /reset all adjustments/i }));

      expect(props.start.onAutoAstro).toHaveBeenCalled();
      expect(props.start.onResetAll).toHaveBeenCalled();
    });

    it('shows Auto Astro running, then its failure', () => {
      const base = makeProps({ activeStep: 'start' });
      const { rerender } = render(
        <EditorInspector {...base} start={{ ...base.start, autoAstroLoading: true }} />,
      );
      expect(screen.getByRole('button', { name: /analyzing/i })).toBeDisabled();

      rerender(
        <EditorInspector {...base} start={{ ...base.start, autoAstroError: 'no stars found' }} />,
      );
      expect(screen.getByText('Auto Astro failed: no stars found')).toBeInTheDocument();
    });
  });

  it('edits the stretch and background extraction sliders on the stack step', () => {
    const onParameterChange = vi.fn();
    render(
      <EditorInspector
        {...makeProps({
          activeStep: 'stack',
          stack: { available: true, onParameterChange, onReset: vi.fn() },
        })}
      />,
    );

    fireEvent.change(screen.getByLabelText('Stretch'), { target: { value: '0.4' } });
    fireEvent.change(screen.getByLabelText('Background extraction'), { target: { value: '60' } });

    expect(onParameterChange).toHaveBeenCalledWith('stretch', 0.4);
    expect(onParameterChange).toHaveBeenCalledWith('backgroundExtraction', 60);
  });

  it('shows the tone curve on the curves step and resets it from the header', () => {
    const onResetCurves = vi.fn();
    render(<EditorInspector {...makeProps({ activeStep: 'curves', onResetCurves })} />);

    expect(screen.getByRole('img', { name: 'Tone curve' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Reset' }));

    expect(onResetCurves).toHaveBeenCalled();
  });

  it('offers the StarNet2 engine on the stars step when the server has it', () => {
    const base = makeProps({ activeStep: 'stars' });
    const onEngineChange = vi.fn();
    const { rerender } = render(
      <EditorInspector
        {...base}
        stars={{ ...base.stars, engines: ['classic', 'starnet2'], onEngineChange }}
      />,
    );

    fireEvent.click(screen.getByRole('radio', { name: 'StarNet2' }));
    expect(onEngineChange).toHaveBeenCalledWith('starnet2');
    expect(screen.queryByText(/Uses the StarNet2 model/)).not.toBeInTheDocument();

    rerender(
      <EditorInspector
        {...base}
        stars={{ ...base.stars, engines: ['classic', 'starnet2'], engine: 'starnet2', onEngineChange }}
      />,
    );
    expect(screen.getByRole('radio', { name: 'StarNet2' })).toHaveAttribute('aria-checked', 'true');
    expect(screen.getByText(/Uses the StarNet2 model/)).toBeInTheDocument();
  });

  it('shows the star mask source count once detection finishes', () => {
    const base = makeProps({ activeStep: 'stars' });
    const { rerender } = render(
      <EditorInspector {...base} stars={{ ...base.stars, enabled: true, loading: true }} />,
    );
    expect(screen.getByText('...')).toBeInTheDocument();

    rerender(
      <EditorInspector {...base} stars={{ ...base.stars, enabled: true, sourceCount: 412 }} />,
    );
    expect(screen.getByText('412 sources')).toBeInTheDocument();

    rerender(<EditorInspector {...base} stars={{ ...base.stars, enabled: true }} />);
    expect(screen.queryByText(/sources/)).not.toBeInTheDocument();
  });

  it('offers the DeepSNR engine on the detail step when the server has it', () => {
    const base = makeProps({ activeStep: 'detail' });
    const onEngineChange = vi.fn();
    render(
      <EditorInspector
        {...base}
        denoise={{ engines: ['classic', 'deepsnr'], engine: 'deepsnr', onEngineChange }}
      />,
    );

    expect(screen.getByText(/Uses the DeepSNR model/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('radio', { name: 'Classic' }));
    expect(onEngineChange).toHaveBeenCalledWith('classic');
  });

  it('renders the export step', () => {
    render(<EditorInspector {...makeProps({ activeStep: 'export' })} />);

    expect(screen.getByDisplayValue('photo_myastroshine')).toBeInTheDocument();
  });

  it('walks the depth focal point states and reports a depth failure', () => {
    const base = makeProps({ activeStep: 'depth' });
    const onClear = vi.fn();
    const { rerender } = render(
      <EditorInspector {...base} depth={{ ...base.depth, picking: true }} />,
    );
    expect(screen.getByRole('button', { name: 'Cancel' })).toBeInTheDocument();

    rerender(
      <EditorInspector
        {...base}
        depth={{ ...base.depth, focalPoint: { x: 0.5, y: 0.5 }, onClear, error: 'out of memory' }}
      />,
    );
    expect(screen.getByRole('button', { name: 'Change focal point' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Clear focal point' }));
    expect(onClear).toHaveBeenCalled();
    expect(screen.getByText('Depth shift failed: out of memory')).toBeInTheDocument();
  });
});

