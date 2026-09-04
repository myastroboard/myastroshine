import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { StackView } from '@/components/stacking/StackView';
import { apiClient } from '@/services/api';

vi.mock('@/services/api', () => ({
  apiClient: {
    initiateStack: vi.fn(),
    uploadStackFrame: vi.fn(),
    processStack: vi.fn(),
    getStack: vi.fn(),
    downloadImage: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

function frameFile(name: string): File {
  return new File([new Uint8Array([1, 2, 3])], name, { type: 'image/png' });
}

describe('StackView', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.initiateStack.mockResolvedValue({
      stackId: 'stack-1',
      status: 'ready',
      frameCount: 2,
      receivedFrames: 0,
    });
    mocked.uploadStackFrame.mockResolvedValue({
      frameIndex: 0,
      receivedFrames: 1,
      frameCount: 2,
      status: 'ready',
    });
    mocked.processStack.mockResolvedValue({
      stackId: 'stack-1',
      status: 'completed',
      jobId: 'job-1',
      wsStatusUrl: '/ws/stack-status/job-1',
      sessionId: 'composite-session',
      stackedImageUrl: '/api/preview/composite-session?full=true',
      statistics: {
        framesStacked: 2,
        framesRejected: 0,
        combinationMethod: 'median',
        cosmicRaysRemoved: 3,
        registrationSuccessRate: 100,
        snrImprovement: 1.41,
      },
      error: null,
    });
  });

  it('uploads frames, stacks them, and shows statistics', async () => {
    render(<StackView onEnhanceComposite={vi.fn()} />);

    const input = screen.getByLabelText(/add frames/i);
    fireEvent.change(input, { target: { files: [frameFile('a.png'), frameFile('b.png')] } });

    fireEvent.click(screen.getByRole('button', { name: /stack 2 frames/i }));

    await waitFor(() => {
      expect(screen.getByText(/SNR improvement/i)).toBeInTheDocument();
    });
    expect(screen.getByText('1.41x')).toBeInTheDocument();
    expect(mocked.initiateStack).toHaveBeenCalledWith(2, expect.objectContaining({ combinationMethod: 'median' }));
    expect(mocked.uploadStackFrame).toHaveBeenCalledTimes(2);
  });

  it('hands the composite session to the enhancer', async () => {
    const onEnhance = vi.fn();
    render(<StackView onEnhanceComposite={onEnhance} />);

    fireEvent.change(screen.getByLabelText(/add frames/i), {
      target: { files: [frameFile('a.png'), frameFile('b.png')] },
    });
    fireEvent.click(screen.getByRole('button', { name: /stack 2 frames/i }));

    await waitFor(() => screen.getByRole('button', { name: /enhance composite/i }));
    fireEvent.click(screen.getByRole('button', { name: /enhance composite/i }));

    expect(onEnhance).toHaveBeenCalledWith('composite-session');
  });

  it('requires at least two frames', async () => {
    render(<StackView onEnhanceComposite={vi.fn()} />);

    fireEvent.change(screen.getByLabelText(/add frames/i), {
      target: { files: [frameFile('only.png')] },
    });

    expect(screen.getByRole('button', { name: /stack 1 frames/i })).toBeDisabled();
  });
});
