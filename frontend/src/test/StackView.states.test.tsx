import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { StackView } from '@/components/stacking/StackView';
import { useStackProcessing } from '@/hooks/useStackProcessing';
import { apiClient } from '@/services/api';
import type { StackResult } from '@/types';

// The workflow states are driven by useStackProcessing; stub it so each test can
// put the view straight into the state it checks (the end-to-end flow through
// the real hook lives in StackView.test.tsx).
vi.mock('@/hooks/useStackProcessing', () => ({ useStackProcessing: vi.fn() }));
vi.mock('@/hooks/useWatchStack', () => ({ useWatchStack: () => null }));
vi.mock('@/hooks/useServerConfig', () => ({
  useServerConfig: () => ({ stackingMaxFrames: 2000, maxImageSizeMb: 100 }),
}));
vi.mock('@/services/api', () => ({
  apiClient: { downloadImage: vi.fn() },
}));

type HookState = ReturnType<typeof useStackProcessing>;

const FRAMES = [
  { index: 0, thumbUrl: '/thumb/0', excluded: false, quality: null },
  { index: 1, thumbUrl: '/thumb/1', excluded: true, quality: null },
];

const RESULT = {
  stackId: 'stack-abcdef123',
  status: 'completed',
  jobId: 'job-1',
  wsStatusUrl: '/ws/stack-status/job-1',
  sessionId: 'composite-session',
  stackedImageUrl: '/preview/composite',
  statistics: {
    framesStacked: 1,
    framesExcluded: 1,
    framesAutoRejected: 0,
    combinationMethod: 'average',
    registrationTransform: 'similarity',
    registrationRmsPx: null,
    referenceFrame: 0,
    snrImprovement: 1,
    measuredNoiseReduction: null,
    calibrated: true,
    postProcessed: false,
    drizzleFactor: 1,
  },
  frames: FRAMES,
  calibration: { frames: { dark: 2, flat: 0, bias: 0, darkFlat: 0 }, cosmeticCorrection: true },
  error: null,
} as unknown as StackResult;

function hookState(overrides: Partial<HookState>): HookState {
  return {
    phase: 'reviewing',
    pending: [],
    uploaded: FRAMES,
    selected: null,
    activeCount: 1,
    calibration: { frames: { dark: 2, flat: 0, bias: 0, darkFlat: 0 }, cosmeticCorrection: true },
    result: null,
    progress: { percent: 0, step: '' },
    error: null,
    addFiles: vi.fn(),
    removePending: vi.fn(),
    uploadFrames: vi.fn().mockResolvedValue(undefined),
    toggleExclude: vi.fn().mockResolvedValue(undefined),
    addCalibrationFiles: vi.fn().mockResolvedValue(undefined),
    clearCalibrationKind: vi.fn().mockResolvedValue(undefined),
    select: vi.fn(),
    stack: vi.fn().mockResolvedValue(undefined),
    attachToStack: vi.fn(),
    reset: vi.fn(),
    ...overrides,
  } as HookState;
}

const useHook = vi.mocked(useStackProcessing);

describe('StackView workflow states', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('reports working while in the editor and shows the hook error', () => {
    useHook.mockReturnValue(hookState({ error: 'Stack failed: not enough stars' }));
    const onWorkingChange = vi.fn();

    render(<StackView onEnhanceComposite={vi.fn()} onWorkingChange={onWorkingChange} />);

    expect(onWorkingChange).toHaveBeenCalledWith(true);
    expect(screen.getByText('Stack failed: not enough stars')).toBeInTheDocument();
  });

  it('offers to upload the frames still pending, from inside the editor', () => {
    const state = hookState({
      pending: [{ id: 'p1', name: 'c.png', sizeBytes: 3, file: new File(['x'], 'c.png') }],
    });
    useHook.mockReturnValue(state);
    render(<StackView onEnhanceComposite={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /upload 1 more/i }));

    expect(state.uploadFrames).toHaveBeenCalled();
  });

  it('wires the Calibration step and the Settings step', () => {
    const state = hookState({});
    useHook.mockReturnValue(state);
    const { container } = render(<StackView onEnhanceComposite={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /calibration/i }));
    fireEvent.click(screen.getAllByRole('button', { name: /^clear$/i })[0]);
    expect(state.clearCalibrationKind).toHaveBeenCalledWith('dark');
    const inputs = container.querySelectorAll<HTMLInputElement>('input[type="file"]');
    fireEvent.change(inputs[inputs.length - 1], { target: { files: [new File(['x'], 'bias.fit')] } });
    expect(state.addCalibrationFiles).toHaveBeenCalled();
    fireEvent.click(screen.getByRole('checkbox', { name: /hot & dead pixels/i }));

    fireEvent.click(screen.getByRole('button', { name: /^3\s*settings/i }));
    expect(screen.getByRole('button', { name: /^3\s*settings/i })).toHaveAttribute('aria-current', 'step');
  });

  it('when done with a frame selected, shows that frame and a way back to the composite', () => {
    const state = hookState({ phase: 'done', result: RESULT, selected: 0 });
    useHook.mockReturnValue(state);
    const { container } = render(<StackView onEnhanceComposite={vi.fn()} />);

    expect(container.querySelector('img[src="/thumb/0"]')).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: /back to composite/i }));

    expect(state.select).toHaveBeenCalledWith(0);
  });

  it('shows the frame counter next to the stacking percentage', () => {
    useHook.mockReturnValue(
      hookState({ phase: 'processing', progress: { percent: 40, step: 'registration', detail: '12/30' } }),
    );
    render(<StackView onEnhanceComposite={vi.fn()} />);

    expect(screen.getAllByText(/12\/30/).length).toBeGreaterThan(0);
  });

  it('downloads the composite from the Result step', async () => {
    const state = hookState({ phase: 'done', result: RESULT });
    useHook.mockReturnValue(state);
    vi.mocked(apiClient.downloadImage).mockResolvedValue(new Blob(['jpg']));
    const createUrl = vi.fn(() => 'blob:stack');
    const revokeUrl = vi.fn();
    Object.assign(URL, { createObjectURL: createUrl, revokeObjectURL: revokeUrl });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => undefined);
    render(<StackView onEnhanceComposite={vi.fn()} />);

    fireEvent.click(screen.getByRole('button', { name: /download composite/i }));

    await waitFor(() => expect(revokeUrl).toHaveBeenCalledWith('blob:stack'));
    expect(apiClient.downloadImage).toHaveBeenCalledWith('composite-session');
    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });

  it('does not download or enhance a result without a composite session', async () => {
    useHook.mockReturnValue(hookState({ phase: 'done', result: { ...RESULT, sessionId: null } }));
    const onEnhanceComposite = vi.fn();
    render(<StackView onEnhanceComposite={onEnhanceComposite} />);

    fireEvent.click(screen.getByRole('button', { name: /download composite/i }));
    fireEvent.click(screen.getByRole('button', { name: /enhance composite/i }));

    await Promise.resolve();
    expect(apiClient.downloadImage).not.toHaveBeenCalled();
    expect(onEnhanceComposite).not.toHaveBeenCalled();
  });

  it('goes back to Frames when a finished stack returns to review', () => {
    useHook.mockReturnValue(hookState({ phase: 'done', result: RESULT }));
    const { rerender } = render(<StackView onEnhanceComposite={vi.fn()} />);
    expect(screen.getByRole('button', { name: /^4\s*result/i })).toHaveAttribute('aria-current', 'step');

    useHook.mockReturnValue(hookState({ phase: 'reviewing', result: RESULT }));
    rerender(<StackView onEnhanceComposite={vi.fn()} />);

    expect(screen.getByRole('button', { name: /^1\s*frames/i })).toHaveAttribute('aria-current', 'step');
  });

  it('reports working and guards the page as soon as frames are picked', () => {
    useHook.mockReturnValue(
      hookState({
        phase: 'collecting',
        uploaded: [],
        pending: [{ id: 'p1', name: 'a.png', sizeBytes: 3, file: new File(['x'], 'a.png') }],
      }),
    );
    const onWorkingChange = vi.fn();
    render(<StackView onEnhanceComposite={vi.fn()} onWorkingChange={onWorkingChange} />);

    const event = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(event);

    expect(onWorkingChange).toHaveBeenCalledWith(true);
    expect(event.defaultPrevented).toBe(true);
  });
});

