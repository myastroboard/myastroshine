import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { StackView } from '@/components/stacking/StackView';
import { apiClient } from '@/services/api';
import type { StackResult } from '@/types';

vi.mock('@/services/api', () => ({
  apiClient: {
    initiateStack: vi.fn(),
    uploadStackFrames: vi.fn(),
    excludeStackFrame: vi.fn(),
    processStack: vi.fn(),
    getStack: vi.fn(),
    getConfig: vi.fn(),
    downloadImage: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

function frameFile(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: 'image/png' });
}

const FRAMES = [
  { index: 0, thumbUrl: '/api/stack/stack-1/frame/0/thumb', excluded: false },
  { index: 1, thumbUrl: '/api/stack/stack-1/frame/1/thumb', excluded: false },
];

const RESULT: StackResult = {
  stackId: 'stack-1',
  status: 'completed',
  jobId: 'job-1',
  wsStatusUrl: '/ws/stack-status/job-1',
  sessionId: 'composite-session',
  stackedImageUrl: '/api/preview/composite-session?full=true',
  statistics: {
    framesStacked: 2,
    framesExcluded: 0,
    combinationMethod: 'average',
    registrationTransform: 'similarity',
    snrImprovement: 1.41,
    measuredNoiseReduction: null,
  },
  frames: FRAMES,
  error: null,
};

function fileInput(container: HTMLElement): HTMLInputElement {
  const input = container.querySelector<HTMLInputElement>('input[type="file"]');
  if (!input) {
    throw new Error('no file input');
  }
  return input;
}

async function pickFramesAndUpload(container: HTMLElement, names = ['a.png', 'b.png']) {
  fireEvent.change(fileInput(container), { target: { files: names.map(frameFile) } });
  fireEvent.click(await screen.findByRole('button', { name: /upload 2 frames/i }));
  await screen.findByRole('button', { name: /stack 2 frames/i });
}

describe('StackView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.getConfig.mockResolvedValue({
      maxImageSizeMb: 100,
      stackingEnabled: true,
      stackingMaxFrames: 2000,
    });
    mocked.initiateStack.mockResolvedValue({
      stackId: 'stack-1',
      status: 'waiting_for_frames',
      frameCount: 2,
      receivedFrames: 0,
    });
    mocked.uploadStackFrames.mockResolvedValue({
      stackId: 'stack-1',
      status: 'ready',
      frameCount: 2,
      receivedFrames: 2,
    });
    mocked.getStack.mockResolvedValue({ ...RESULT, status: 'ready', statistics: null });
    mocked.excludeStackFrame.mockResolvedValue({ ...FRAMES[1], excluded: true });
    mocked.processStack.mockResolvedValue(RESULT);
  });

  it('collects frames, uploads them in one batch, then stacks', async () => {
    const { container } = render(<StackView onEnhanceComposite={vi.fn()} />);
    await pickFramesAndUpload(container);

    fireEvent.click(screen.getByRole('button', { name: /stack 2 frames/i }));

    await waitFor(() => expect(screen.getByText(/SNR improvement/i)).toBeInTheDocument());
    expect(screen.getByText('1.41x')).toBeInTheDocument();
    expect(mocked.initiateStack).toHaveBeenCalledWith(
      2,
      expect.objectContaining({ combinationMethod: 'average' }),
    );
    expect(mocked.uploadStackFrames).toHaveBeenCalledWith('stack-1', 0, [
      expect.any(File),
      expect.any(File),
    ]);
    expect(mocked.processStack).toHaveBeenCalledWith(
      'stack-1',
      expect.objectContaining({ combinationMethod: 'average' }),
    );
  });

  it('excludes a frame from the review grid', async () => {
    const { container } = render(<StackView onEnhanceComposite={vi.fn()} />);
    await pickFramesAndUpload(container);

    const checkboxes = screen.getAllByRole('checkbox');
    fireEvent.click(checkboxes[1]);

    await waitFor(() => expect(mocked.excludeStackFrame).toHaveBeenCalledWith('stack-1', 1, true));
  });

  it('re-stacks with the current settings after a first result', async () => {
    const { container } = render(<StackView onEnhanceComposite={vi.fn()} />);
    await pickFramesAndUpload(container);
    fireEvent.click(screen.getByRole('button', { name: /stack 2 frames/i }));
    await screen.findByRole('button', { name: /enhance composite/i });

    fireEvent.click(screen.getByRole('button', { name: /re-stack 2 frames/i }));

    await waitFor(() => expect(mocked.processStack).toHaveBeenCalledTimes(2));
    expect(mocked.processStack).toHaveBeenLastCalledWith(
      'stack-1',
      expect.objectContaining({ combinationMethod: 'average' }),
    );
  });

  it('hands the composite session to the enhancer', async () => {
    const onEnhance = vi.fn();
    const { container } = render(<StackView onEnhanceComposite={onEnhance} />);
    await pickFramesAndUpload(container);
    fireEvent.click(screen.getByRole('button', { name: /stack 2 frames/i }));

    await waitFor(() => screen.getByRole('button', { name: /enhance composite/i }));
    fireEvent.click(screen.getByRole('button', { name: /enhance composite/i }));

    expect(onEnhance).toHaveBeenCalledWith('composite-session');
  });

  it('will not upload fewer than two frames', async () => {
    const { container } = render(<StackView onEnhanceComposite={vi.fn()} />);
    fireEvent.change(fileInput(container), { target: { files: [frameFile('only.png')] } });

    expect(screen.getByRole('button', { name: /upload 1 frames/i })).toBeDisabled();
  });
});
