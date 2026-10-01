import type { ReactNode } from 'react';
import { act, fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { CaptureInfoPanelProps } from '@/components/CaptureInfoPanel';
import type { DepthShiftViewerProps } from '@/components/DepthShiftViewer';
import type { EditorInspectorProps } from '@/components/EditorInspector';
import type { EditorRailProps } from '@/components/EditorRail';
import { EditorView } from '@/components/EditorView';
import type { ImagePreviewProps } from '@/components/ImagePreview';
import type { MilestoneTimelineProps } from '@/components/MilestoneTimeline';
import type { SavePresetDialogProps } from '@/components/SavePresetDialog';
import { apiClient } from '@/services/api';
import {
  DEFAULT_GEOMETRY,
  DEFAULT_PARAMETERS,
  type CaptureInfo,
  type EditorSession,
  type GeometryParameters,
  type ProcessingParameters,
} from '@/types';

// EditorView orchestrates hooks and child components. Every hook is stubbed with
// controllable state, and every child is a stub that captures its props, so each
// test drives one handler and checks what it did.
interface Captured {
  inspector: EditorInspectorProps;
  rail: EditorRailProps;
  preview: ImagePreviewProps;
  milestones: MilestoneTimelineProps;
  capture: CaptureInfoPanelProps;
  depthViewer: DepthShiftViewerProps;
  savePreset: SavePresetDialogProps;
}

const h = vi.hoisted(() => ({
  captured: {} as Partial<Captured>,
  state: {} as FakeState,
}));

function stub<K extends keyof Captured>(name: K) {
  return (props: Captured[K]) => {
    h.captured[name] = props;
    // Pass children through: the preview card hosts the versions strip.
    return <div data-testid={name}>{(props as { children?: ReactNode }).children}</div>;
  };
}

vi.mock('@/components/EditorInspector', () => ({ EditorInspector: stub('inspector') }));
vi.mock('@/components/EditorRail', () => ({ EditorRail: stub('rail') }));
vi.mock('@/components/ImagePreview', () => ({ ImagePreview: stub('preview') }));
vi.mock('@/components/MilestoneTimeline', () => ({ MilestoneTimeline: stub('milestones') }));
vi.mock('@/components/CaptureInfoPanel', () => ({ CaptureInfoPanel: stub('capture') }));
vi.mock('@/components/DepthShiftViewer', () => ({ DepthShiftViewer: stub('depthViewer') }));
vi.mock('@/components/SavePresetDialog', () => ({ SavePresetDialog: stub('savePreset') }));

vi.mock('@/hooks/useImageProcessing', () => ({ useImageProcessing: () => h.state.processing }));
vi.mock('@/hooks/usePresets', () => ({ usePresets: () => h.state.presets }));
vi.mock('@/hooks/useDepthShift', () => ({ useDepthShift: () => h.state.depth }));
vi.mock('@/hooks/useServerConfig', () => ({
  useServerConfig: () => ({ starlessEngines: ['classic'], denoiseEngines: ['classic'] }),
}));
vi.mock('@/hooks/useStarMask', () => ({ useStarMask: () => h.state.starMask }));
vi.mock('@/hooks/useAutoAstro', () => ({ useAutoAstro: () => h.state.autoAstro }));
vi.mock('@/hooks/useCaptureInfo', () => ({ useCaptureInfo: () => h.state.captureInfo }));
vi.mock('@/hooks/useAstroDexIntegration', () => ({
  useAstroDexIntegration: () => h.state.astrodex,
}));
vi.mock('@/hooks/useMilestones', () => ({ useMilestones: () => h.state.milestones }));
vi.mock('@/services/api', () => ({
  apiClient: {
    previewUrl: (sessionId: string, opts: Record<string, unknown> = {}) =>
      `/preview/${sessionId}?${new URLSearchParams(opts as Record<string, string>).toString()}`,
    downloadImage: vi.fn(),
  },
}));

const JOB = { sessionId: 's', jobId: 'job-1', status: 'queued' };

function makeState(parameters: ProcessingParameters) {
  return {
    processing: {
      parameters,
      status: 'idle',
      progress: null,
      currentStep: '',
      previewVersion: 0,
      sliderRevert: null,
      revertSlider: vi.fn(),
      updateParameter: vi.fn(),
      updateStarRemovalEngine: vi.fn(),
      updateDenoiseEngine: vi.fn(),
      updateStackParameter: vi.fn(),
      updateChannelCurve: vi.fn(),
      applyGeometry: vi.fn(),
      trackJob: vi.fn(),
      resetParameters: vi.fn(),
      resetStack: vi.fn(),
      resetCurves: vi.fn(),
      resetKeys: vi.fn(),
      syncParameters: vi.fn(),
      restoreParameters: vi.fn(),
    },
    presets: {
      presets: [{ presetId: 'p1', name: 'Nebula', parameters: { contrast: 1.4 } }],
      applyPreset: vi.fn().mockResolvedValue(JOB),
      activePreset: undefined,
      savePreset: vi.fn().mockResolvedValue(undefined),
      deletePreset: vi.fn().mockRejectedValue(new Error('built-in')),
      clearActivePreset: vi.fn(),
    },
    depth: {
      layerUrls: [] as string[],
      intensity: 50,
      setIntensity: vi.fn(),
      generate: vi.fn().mockResolvedValue(undefined),
      error: null as string | null,
    },
    starMask: {
      stars: [],
      sourceCount: null,
      detect: vi.fn().mockResolvedValue(undefined),
      clear: vi.fn(),
      isLoading: false,
    },
    autoAstro: { apply: vi.fn(), isLoading: false, error: null },
    captureInfo: null as CaptureInfo | null,
    astrodex: {
      returnImage: vi.fn().mockResolvedValue(true),
      isLoading: false,
      success: false,
      error: null,
    },
    milestones: { milestones: [], activeId: null as string | null, capture: vi.fn() },
  };
}

type FakeState = ReturnType<typeof makeState>;

function resetState(parameters: ProcessingParameters = DEFAULT_PARAMETERS): void {
  h.captured = {};
  h.state = makeState(parameters);
}

const SESSION: EditorSession = {
  sessionId: 'abcdef1234567890',
  dimensions: { width: 4000, height: 2000 },
  originalFilename: 'm42.tiff',
};

const EDITED: ProcessingParameters = { ...DEFAULT_PARAMETERS, contrast: 1.6 };

function renderEditor(session: EditorSession = SESSION, onExit = vi.fn()) {
  const view = render(<EditorView session={session} onExit={onExit} />);
  return { ...view, onExit };
}

/** The props a stubbed child was last rendered with (fails if it never rendered). */
function captured<K extends keyof Captured>(name: K): Captured[K] {
  const props = h.captured[name];
  if (!props) {
    throw new Error(`${name} was not rendered`);
  }
  return props;
}

const inspector = () => captured('inspector');
const preview = () => captured('preview');

describe('EditorView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetState();
  });

  describe('session-derived defaults', () => {
    it('starts on Start with an export name from the uploaded file', () => {
      renderEditor();

      expect(inspector().activeStep).toBe('start');
      expect(inspector().exportActions.defaultFilename).toBe('m42_myastroshine');
      expect(inspector().exportActions.canReturnToAstroDex).toBe(false);
      expect(preview().aspectRatio).toBe(2);
      expect(screen.queryByTestId('capture')).not.toBeInTheDocument();
    });

    it('starts a stacked composite on the Stack step, without dimensions or framing', () => {
      h.state.captureInfo = { frames: 12 } as unknown as CaptureInfo;
      renderEditor({ sessionId: 'stack-session-1', isStack: true });

      expect(inspector().activeStep).toBe('stack');
      expect(inspector().stack.available).toBe(true);
      expect(inspector().framing.available).toBe(false);
      expect(inspector().framing.dimensions).toEqual({ width: 0, height: 0 });
      expect(inspector().exportActions.defaultFilename).toBe('myastroshine_stack-se');
      expect(preview().aspectRatio).toBeUndefined();
      expect(screen.getByTestId('capture')).toBeInTheDocument();
    });

    it('names the export after the Astrodex object for a handoff session', () => {
      renderEditor({ sessionId: 's1', astrodex: { itemId: 'i1', objectName: 'M31' } });

      expect(inspector().exportActions.defaultFilename).toBe('M31_myastroshine');
      expect(inspector().exportActions.astrodexObjectName).toBe('M31');
    });

    it('uses the geometry-aware original once the framing changed, and swaps sides on a quarter turn', () => {
      const geometry: GeometryParameters = { ...DEFAULT_GEOMETRY, rotateQuarters: 1 };
      resetState({ ...DEFAULT_PARAMETERS, geometry });
      renderEditor();

      expect(preview().originalUrl).toContain('geometry=true');
      expect(preview().aspectRatio).toBe(0.5);
    });

    it('labels a StarNet2 pass while it runs', () => {
      resetState({ ...DEFAULT_PARAMETERS, starRemovalEngine: 'starnet2' });
      h.state.processing.currentStep = 'star_removal';
      h.state.processing.status = 'processing';
      renderEditor();

      expect(preview().progressLabel).toMatch(/StarNet2/);
      expect(inspector().isProcessing).toBe(true);
    });
  });

  describe('leaving the editor', () => {
    it('exits straight away without edits', () => {
      const { onExit } = renderEditor();

      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));

      expect(onExit).toHaveBeenCalled();
    });

    it('asks before discarding edits, guards the page, and can be cancelled', () => {
      resetState(EDITED);
      const { onExit } = renderEditor();
      const unload = new Event('beforeunload', { cancelable: true });
      window.dispatchEvent(unload);
      expect(unload.defaultPrevented).toBe(true);

      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));
      fireEvent.click(screen.getByRole('dialog').firstElementChild as HTMLElement); // inside: stays
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('dialog')); // backdrop
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument();

      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));
      fireEvent.click(screen.getByRole('button', { name: /discard/i }));
      expect(onExit).toHaveBeenCalled();
    });

    it('stands down once the current edit was sent back to Astrodex', async () => {
      resetState(EDITED);
      const { onExit } = renderEditor({ sessionId: 's1', astrodex: { itemId: 'i', objectName: null } });

      await act(async () => inspector().exportActions.onReturnToAstroDex());
      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));

      expect(h.state.astrodex.returnImage).toHaveBeenCalledWith('s1');
      expect(onExit).toHaveBeenCalled();
    });

    it('still asks when the Astrodex delivery failed or the edit moved on since', async () => {
      resetState(EDITED);
      h.state.astrodex.returnImage = vi.fn().mockResolvedValue(false);
      const session = { sessionId: 's1', astrodex: { itemId: 'i', objectName: null } };
      const { rerender, onExit } = renderEditor(session);
      await act(async () => inspector().exportActions.onReturnToAstroDex());
      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

      h.state.astrodex.returnImage = vi.fn().mockResolvedValue(true);
      await act(async () => inspector().exportActions.onReturnToAstroDex());
      act(() => inspector().depth.onClear()); // focal point unchanged (null): still delivered
      act(() => preview().onFocalPointPick!({ x: 0.2, y: 0.3 })); // moved on
      rerender(<EditorView session={session} onExit={onExit} />);
      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('compares the focal point delivered to Astrodex with the current one', async () => {
      const session = { sessionId: 's1', astrodex: { itemId: 'i', objectName: null } };
      const { onExit } = renderEditor(session);
      act(() => preview().onFocalPointPick!({ x: 0.2, y: 0.3 }));
      await act(async () => inspector().exportActions.onReturnToAstroDex());

      act(() => preview().onFocalPointPick!({ x: 0.2, y: 0.3 })); // same point
      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));
      expect(onExit).toHaveBeenCalledTimes(1);

      act(() => preview().onFocalPointPick!({ x: 0.2, y: 0.8 })); // same x, new y
      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));
      expect(screen.getByRole('dialog')).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

      act(() => preview().onFocalPointPick!({ x: 0.9, y: 0.3 })); // new x
      fireEvent.click(screen.getByRole('button', { name: /new photo/i }));
      expect(screen.getByRole('dialog')).toBeInTheDocument();
    });

    it('does nothing when asked to return without an Astrodex session', async () => {
      renderEditor();

      await act(async () => inspector().exportActions.onReturnToAstroDex());

      expect(h.state.astrodex.returnImage).not.toHaveBeenCalled();
    });
  });

  describe('framing', () => {
    const cropped: GeometryParameters = { ...DEFAULT_GEOMETRY, cropW: 0.5 };

    it('previews the crop on the Frame step and commits it when leaving the step', () => {
      renderEditor();
      act(() => inspector().onStepChange('frame'));
      expect(preview().framing).not.toBeNull();

      act(() => inspector().framing.onGeometryChange(cropped));
      expect(inspector().framing.dirty).toBe(true);
      act(() => inspector().framing.onRatioFracChange(0.5));
      act(() => inspector().onStepChange('light'));

      expect(h.state.processing.applyGeometry).toHaveBeenCalledWith(cropped);
      expect(preview().framing).toBeNull();
    });

    it('leaves the Frame step without committing when nothing changed', () => {
      renderEditor();
      act(() => inspector().onStepChange('frame'));
      act(() => inspector().onStepChange('light'));

      expect(h.state.processing.applyGeometry).not.toHaveBeenCalled();
    });

    it('applies the draft on demand and resets back to the full frame', () => {
      resetState({ ...DEFAULT_PARAMETERS, geometry: cropped });
      renderEditor();

      act(() => inspector().framing.onApply());
      expect(h.state.processing.applyGeometry).toHaveBeenCalledWith(cropped);

      act(() => inspector().framing.onReset());
      expect(h.state.processing.applyGeometry).toHaveBeenLastCalledWith(DEFAULT_GEOMETRY);
    });

    it('resets only the draft when the applied framing is already the full frame', () => {
      renderEditor();
      act(() => inspector().framing.onGeometryChange(cropped));

      act(() => inspector().framing.onReset());

      expect(h.state.processing.applyGeometry).not.toHaveBeenCalled();
      expect(inspector().framing.geometry).toEqual(DEFAULT_GEOMETRY);
    });
  });

  describe('star mask', () => {
    it('detects stars when shown, re-detects after the sliders settle, clears when hidden', () => {
      vi.useFakeTimers();
      try {
        renderEditor();
        act(() => inspector().stars.onToggle(true));
        expect(h.state.starMask.detect).toHaveBeenCalledTimes(1);
        expect(preview().starMaskOverlay).toEqual([]);

        act(() => {
          vi.advanceTimersByTime(500);
        });
        expect(h.state.starMask.detect).toHaveBeenCalledTimes(2);

        act(() => inspector().stars.onToggle(false));
        expect(h.state.starMask.clear).toHaveBeenCalled();
        expect(preview().starMaskOverlay).toBeNull();
      } finally {
        vi.useRealTimers();
      }
    });
  });

  describe('looks: presets, Auto Astro, manual edits', () => {
    it('applies a preset as a look, keeping the framing, and follows its job', async () => {
      const geometry = { ...DEFAULT_GEOMETRY, cropW: 0.7 };
      resetState({ ...DEFAULT_PARAMETERS, geometry });
      renderEditor();

      await act(async () => inspector().start.onPresetApply('p1'));

      expect(h.state.processing.syncParameters).toHaveBeenCalledWith(
        expect.objectContaining({ contrast: 1.4, geometry }),
      );
      expect(h.state.processing.trackJob).toHaveBeenCalledWith(JOB);
    });

    it('still follows the job of a preset that is not in the list', async () => {
      renderEditor();

      await act(async () => inspector().start.onPresetApply('gone'));

      expect(h.state.processing.syncParameters).not.toHaveBeenCalled();
      expect(h.state.processing.trackJob).toHaveBeenCalledWith(JOB);
    });

    it('swallows a refused preset delete', async () => {
      renderEditor();

      await act(async () => inspector().start.onPresetDelete('system_nebula'));

      expect(h.state.presets.deletePreset).toHaveBeenCalledWith('system_nebula');
    });

    it('applies Auto Astro when it proposes something, and ignores a failed run', async () => {
      h.state.autoAstro.apply = vi
        .fn()
        .mockResolvedValueOnce({ ...JOB, parameters: { exposure: 0.3 } })
        .mockResolvedValueOnce(null);
      renderEditor();

      await act(async () => inspector().start.onAutoAstro());
      expect(h.state.processing.syncParameters).toHaveBeenCalledWith(
        expect.objectContaining({ exposure: 0.3 }),
      );
      expect(h.state.processing.trackJob).toHaveBeenCalledTimes(1);

      await act(async () => inspector().start.onAutoAstro());
      expect(h.state.processing.trackJob).toHaveBeenCalledTimes(1);
      expect(h.state.presets.clearActivePreset).toHaveBeenCalledTimes(2);
    });

    it('routes every manual edit through, dropping the active preset each time', () => {
      renderEditor();
      const p = h.state.processing;
      const i = inspector();

      act(() => i.onParameterChange('contrast', 1.2));
      act(() => i.onSliderRevert());
      act(() => i.start.onResetAll());
      act(() => i.onResetSection(['contrast']));
      act(() => i.onResetCurves());
      act(() => i.onCurveChange('red', [{ x: 0, y: 0 }]));
      act(() => i.stack.onParameterChange('stretch', 0.4));
      act(() => i.stack.onReset());

      expect(p.updateParameter).toHaveBeenCalledWith('contrast', 1.2);
      expect(p.revertSlider).toHaveBeenCalled();
      expect(p.resetParameters).toHaveBeenCalled();
      expect(p.resetKeys).toHaveBeenCalledWith(['contrast']);
      expect(p.resetCurves).toHaveBeenCalled();
      expect(p.updateChannelCurve).toHaveBeenCalledWith('red', [{ x: 0, y: 0 }]);
      expect(p.updateStackParameter).toHaveBeenCalledWith('stretch', 0.4);
      expect(p.resetStack).toHaveBeenCalled();
      expect(h.state.presets.clearActivePreset).toHaveBeenCalledTimes(8);
    });
  });

  describe('milestones and depth', () => {
    const milestone = {
      id: 'm1',
      kind: 'saved' as const,
      ordinal: 1,
      parameters: EDITED,
      focalPoint: { x: 0.4, y: 0.6 },
      createdAt: 1,
    };

    it('restores a milestone, regenerating an open depth view', () => {
      h.state.depth.layerUrls = ['/l0'];
      renderEditor();

      act(() => captured('milestones').onRestore(milestone));

      expect(h.state.processing.restoreParameters).toHaveBeenCalledWith(EDITED);
      expect(h.state.depth.generate).toHaveBeenCalledWith(7, { x: 0.4, y: 0.6 });
      expect(preview().focalPoint).toEqual({ x: 0.4, y: 0.6 });
    });

    it('restores a milestone without a focal point and no depth view open', () => {
      renderEditor();

      act(() => captured('milestones').onRestore({ ...milestone, focalPoint: null }));
      expect(h.state.depth.generate).not.toHaveBeenCalled();

      h.state.depth.layerUrls = ['/l0'];
      act(() => captured('milestones').onRestore({ ...milestone, focalPoint: null }));
      expect(h.state.depth.generate).toHaveBeenCalledWith(7, undefined);
    });

    it('keeps unsaved work as a new point before going back, so nothing is lost', () => {
      renderEditor();
      act(() => captured('milestones').onRestore(milestone));
      expect(h.state.milestones.capture).toHaveBeenCalledTimes(1);
    });

    it('does not duplicate a point when the current state already matches one', () => {
      h.state.milestones.activeId = 'm0';
      renderEditor();
      act(() => captured('milestones').onRestore(milestone));
      expect(h.state.milestones.capture).not.toHaveBeenCalled();
    });

    it('picks and clears the focal point, and stops picking when leaving the Depth step', () => {
      renderEditor();
      act(() => inspector().onStepChange('depth'));
      act(() => inspector().depth.onTogglePick());
      expect(preview().pickingFocalPoint).toBe(true);

      act(() => preview().onFocalPointPick!({ x: 0.1, y: 0.9 }));
      expect(h.state.depth.generate).toHaveBeenCalledWith(7, { x: 0.1, y: 0.9 });
      expect(inspector().depth.picking).toBe(false);

      act(() => inspector().depth.onTogglePick());
      act(() => inspector().onStepChange('export'));
      expect(inspector().depth.picking).toBe(false);

      act(() => inspector().depth.onClear());
      expect(h.state.depth.generate).toHaveBeenLastCalledWith(7);
    });

    it('opens the depth viewer: generating first, then the layers, and closes it', () => {
      const { rerender } = renderEditor();
      act(() => preview().onFocalPointPick!({ x: 0.5, y: 0.5 }));
      h.state.depth.generate.mockClear();

      act(() => inspector().depth.onOpenViewer());
      expect(h.state.depth.generate).toHaveBeenCalledWith(7, { x: 0.5, y: 0.5 });
      expect(screen.getByText(/generating/i)).toBeInTheDocument();

      h.state.depth.layerUrls = ['/l0', '/l1'];
      rerender(<EditorView session={SESSION} onExit={vi.fn()} />);
      expect(screen.getByTestId('depthViewer')).toBeInTheDocument();
      act(() => inspector().depth.onOpenViewer()); // layers ready: no regeneration
      expect(h.state.depth.generate).toHaveBeenCalledTimes(1);

      act(() => captured('depthViewer').onClose());
      expect(screen.queryByTestId('depthViewer')).not.toBeInTheDocument();
    });

    it('opens the depth viewer with no focal point, and shows a depth failure', () => {
      h.state.depth.error = 'out of memory';
      renderEditor();

      act(() => inspector().depth.onOpenViewer());

      expect(h.state.depth.generate).toHaveBeenCalledWith(7, undefined);
      expect(screen.getByText(/out of memory/)).toBeInTheDocument();
    });
  });

  describe('export', () => {
    it('downloads under the typed name, or the default when it is blank', async () => {
      vi.mocked(apiClient.downloadImage).mockResolvedValue(new Blob(['jpg']));
      Object.assign(URL, { createObjectURL: vi.fn(() => 'blob:x'), revokeObjectURL: vi.fn() });
      const names: string[] = [];
      const click = vi
        .spyOn(HTMLAnchorElement.prototype, 'click')
        .mockImplementation(function (this: HTMLAnchorElement) {
          names.push(this.download);
        });
      renderEditor();

      await act(async () => inspector().exportActions.onDownload('  final.png '));
      await act(async () => inspector().exportActions.onDownload('   '));

      expect(names).toEqual(['final.jpg', 'm42_myastroshine.jpg']);
      click.mockRestore();
    });

    it('saves the current look as a preset from a dialog', async () => {
      resetState(EDITED);
      renderEditor();

      act(() => inspector().exportActions.onSaveAsPreset());
      await act(async () => {
        await captured('savePreset').onSave('Mine', 'notes');
      });
      expect(h.state.presets.savePreset).toHaveBeenCalledWith({
        name: 'Mine',
        description: 'notes',
        parameters: EDITED,
      });

      act(() => captured('savePreset').onClose());
      expect(screen.queryByTestId('savePreset')).not.toBeInTheDocument();
    });
  });
});
