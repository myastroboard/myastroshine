import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import App from '@/App';
import { apiClient } from '@/services/api';

vi.mock('@/components/EditorView', () => ({
  EditorView: ({ session, onExit }: { session: unknown; onExit: () => void }) => (
    <div data-testid="editor-view">
      <span data-testid="editor-session">{JSON.stringify(session)}</span>
      <button onClick={onExit}>exit-editor</button>
    </div>
  ),
}));

vi.mock('@/components/Footer', () => ({
  Footer: () => <footer data-testid="footer" />,
}));

vi.mock('@/components/ImageUpload', () => ({
  ImageUpload: ({
    onUpload,
    isLoading,
    progress,
    maxSizeMb,
  }: {
    onUpload: (file: File) => void;
    isLoading?: boolean;
    progress?: number | null;
    maxSizeMb?: number;
  }) => (
    <div data-testid="image-upload">
      <span data-testid="upload-state">
        {String(isLoading)}:{String(progress)}:{String(maxSizeMb)}
      </span>
      <button onClick={() => onUpload(new File(['x'], 'photo.jpg', { type: 'image/jpeg' }))}>
        do-upload
      </button>
    </div>
  ),
}));

vi.mock('@/components/SettingsView', () => ({
  SettingsView: ({ onClose }: { onClose: () => void }) => (
    <div data-testid="settings-view">
      <button onClick={onClose}>close-settings</button>
    </div>
  ),
}));

vi.mock('@/components/stacking/StackMode', () => ({
  StackMode: ({
    mode,
    onModeChange,
  }: {
    mode: string;
    onModeChange: (mode: 'single' | 'stack') => void;
  }) => (
    <div data-testid="stack-mode">
      <span data-testid="current-mode">{mode}</span>
      <button onClick={() => onModeChange('stack')}>go-stack</button>
      <button onClick={() => onModeChange('single')}>go-single</button>
    </div>
  ),
}));

vi.mock('@/components/stacking/StackView', () => ({
  StackView: ({
    onEnhanceComposite,
    onWorkingChange,
  }: {
    onEnhanceComposite: (sessionId: string) => void;
    onWorkingChange: (working: boolean) => void;
  }) => (
    <div data-testid="stack-view">
      <button onClick={() => onEnhanceComposite('composite-session-1')}>enhance</button>
      <button onClick={() => onWorkingChange(true)}>set-working</button>
      <button onClick={() => onWorkingChange(false)}>clear-working</button>
    </div>
  ),
}));

vi.mock('@/hooks/useServerConfig', () => ({
  useServerConfig: () => ({
    maxImageSizeMb: 42,
    stackingEnabled: true,
    stackingMaxFrames: 100,
    starlessEngines: ['classic'],
    denoiseEngines: ['classic'],
  }),
}));

vi.mock('@/services/api', () => ({
  apiClient: {
    resumeAstrodexHandoff: vi.fn(),
    uploadImage: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

function resetLocation() {
  window.history.pushState({}, '', '/');
}

describe('App', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    resetLocation();
  });

  afterEach(() => {
    resetLocation();
  });

  it('renders the upload screen by default with the server-configured size cap', () => {
    render(<App />);

    expect(screen.getByTestId('image-upload')).toBeInTheDocument();
    expect(screen.getByTestId('upload-state')).toHaveTextContent('false:null:42');
    expect(screen.getByTestId('stack-mode')).toBeInTheDocument();
    expect(screen.getByTestId('footer')).toBeInTheDocument();
  });

  it('opens straight on the settings route when the URL hash says so', () => {
    window.history.pushState({}, '', '#/settings');
    render(<App />);

    expect(screen.getByTestId('settings-view')).toBeInTheDocument();
    expect(screen.queryByTestId('image-upload')).not.toBeInTheDocument();
    const settingsButton = screen.getByRole('button', { name: 'Settings' });
    expect(settingsButton).toHaveAttribute('aria-current', 'page');
    expect(settingsButton.className).toContain('btn-outline');
  });

  it('toggles between the editor and settings routes via the nav button and hash routing', async () => {
    render(<App />);

    const navButton = screen.getByRole('button', { name: 'Settings' });
    expect(navButton).not.toHaveAttribute('aria-current');
    expect(navButton.className).toContain('btn-ghost');

    // Navigation is driven by the `hashchange` event, which jsdom dispatches
    // asynchronously - the route only updates once that event is handled.
    fireEvent.click(navButton);
    await screen.findByTestId('settings-view');
    expect(window.location.hash).toBe('#/settings');

    // Clicking the same nav button while already on settings toggles back
    // (exercises both arms of the toggle, not just the dedicated close button).
    fireEvent.click(screen.getByRole('button', { name: 'Settings' }));
    await screen.findByTestId('image-upload');
    expect(window.location.hash).toBe('#/');

    // And the settings screen's own close control navigates back too.
    fireEvent.click(navButton);
    await screen.findByTestId('settings-view');
    fireEvent.click(screen.getByRole('button', { name: 'close-settings' }));
    await screen.findByTestId('image-upload');
  });

  it('returns to the editor route from the logo button', async () => {
    window.history.pushState({}, '', '#/settings');
    render(<App />);

    expect(screen.getByTestId('settings-view')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: /MyAstroShine/ }));

    await screen.findByTestId('image-upload');
  });

  it('switches to stack mode, hiding the mode picker while a stack is working', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'go-stack' }));
    expect(screen.getByTestId('current-mode')).toHaveTextContent('stack');
    expect(screen.getByTestId('stack-view')).toBeInTheDocument();
    expect(screen.getByTestId('stack-mode')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'set-working' }));
    expect(screen.queryByTestId('stack-mode')).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'clear-working' }));
    expect(screen.getByTestId('stack-mode')).toBeInTheDocument();
  });

  it('hides the mode picker once a single-image session is open', async () => {
    mocked.uploadImage.mockResolvedValue({
      sessionId: 'sess-1',
      imageUrl: '/x',
      dimensions: { width: 10, height: 10 },
      fileSizeBytes: 1,
      histogram: { r: [], g: [], b: [] },
      uploadTimestamp: '',
      expiresAt: '',
      isStack: false,
    });
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'do-upload' }));
    await screen.findByTestId('editor-view');

    expect(screen.queryByTestId('stack-mode')).not.toBeInTheDocument();
  });

  it('hands a stacked composite to the single-image editor', () => {
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'go-stack' }));
    fireEvent.click(screen.getByRole('button', { name: 'enhance' }));

    // Back on 'single' mode with a session open - the mode picker (which only
    // shows pre-session) is gone, along with the stacking view.
    expect(screen.queryByTestId('stack-mode')).not.toBeInTheDocument();
    expect(screen.queryByTestId('stack-view')).not.toBeInTheDocument();
    const session = JSON.parse(screen.getByTestId('editor-session').textContent ?? '{}');
    expect(session).toEqual({ sessionId: 'composite-session-1', isStack: true });
  });

  it('uploads an image, tracks progress, and opens the editor', async () => {
    let resolveUpload!: (value: {
      sessionId: string;
      imageUrl: string;
      dimensions: { width: number; height: number };
      fileSizeBytes: number;
      histogram: { r: number[]; g: number[]; b: number[] };
      uploadTimestamp: string;
      expiresAt: string;
      isStack: boolean;
    }) => void;
    mocked.uploadImage.mockImplementation(
      (_file, onProgress) =>
        new Promise((resolve) => {
          onProgress?.(0.4);
          resolveUpload = resolve;
        }),
    );

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'do-upload' }));

    await waitFor(() => expect(screen.getByTestId('upload-state')).toHaveTextContent('true:0.4:42'));

    await act(async () => {
      resolveUpload({
        sessionId: 'sess-2',
        imageUrl: '/x',
        dimensions: { width: 10, height: 10 },
        fileSizeBytes: 1,
        histogram: { r: [], g: [], b: [] },
        uploadTimestamp: '',
        expiresAt: '',
        isStack: false,
      });
    });

    await screen.findByTestId('editor-view');
    const session = JSON.parse(screen.getByTestId('editor-session').textContent ?? '{}');
    expect(session).toMatchObject({ sessionId: 'sess-2', originalFilename: 'photo.jpg' });
  });

  it('clears the progress indicator once the byte transfer completes (fraction >= 1)', async () => {
    mocked.uploadImage.mockImplementation((_file, onProgress) => {
      onProgress?.(1);
      return Promise.resolve({
        sessionId: 'sess-3',
        imageUrl: '/x',
        dimensions: { width: 10, height: 10 },
        fileSizeBytes: 1,
        histogram: { r: [], g: [], b: [] },
        uploadTimestamp: '',
        expiresAt: '',
        isStack: false,
      });
    });

    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'do-upload' }));

    await screen.findByTestId('editor-view');
  });

  it('shows the upload failure message and lets the user retry', async () => {
    mocked.uploadImage.mockRejectedValue(new Error('network down'));
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'do-upload' }));

    expect(await screen.findByText('network down')).toBeInTheDocument();
    expect(screen.getByTestId('image-upload')).toBeInTheDocument();
  });

  it('falls back to a generic message when the upload rejects without an Error', async () => {
    mocked.uploadImage.mockRejectedValue('boom');
    render(<App />);

    fireEvent.click(screen.getByRole('button', { name: 'do-upload' }));

    expect(await screen.findByText('Upload failed')).toBeInTheDocument();
  });

  it('exits the editor back to the upload screen, clearing any error', async () => {
    mocked.uploadImage.mockResolvedValue({
      sessionId: 'sess-4',
      imageUrl: '/x',
      dimensions: { width: 10, height: 10 },
      fileSizeBytes: 1,
      histogram: { r: [], g: [], b: [] },
      uploadTimestamp: '',
      expiresAt: '',
      isStack: false,
    });
    render(<App />);
    fireEvent.click(screen.getByRole('button', { name: 'do-upload' }));
    await screen.findByTestId('editor-view');

    fireEvent.click(screen.getByRole('button', { name: 'exit-editor' }));

    expect(screen.getByTestId('image-upload')).toBeInTheDocument();
  });

  it('resumes an AstroDex handoff carried in the hash fragment and opens the editor', async () => {
    window.history.pushState({}, '', '#/?handoff=tok-123');
    let resolveHandoff!: (value: {
      sessionId: string;
      imageUrl: string;
      histogram: { r: number[]; g: number[]; b: number[] };
      dimensions: { width: number; height: number };
      astrodexItemId: string;
      objectName: string;
    }) => void;
    mocked.resumeAstrodexHandoff.mockImplementation(
      () =>
        new Promise((resolve) => {
          resolveHandoff = resolve;
        }),
    );

    render(<App />);

    // The token is single-use: stripped from the URL right away.
    expect(window.location.hash).toBe('#/');
    expect(await screen.findByText('Opening your image from AstroDex...')).toBeInTheDocument();
    expect(mocked.resumeAstrodexHandoff).toHaveBeenCalledWith('tok-123');
    expect(screen.queryByTestId('stack-mode')).not.toBeInTheDocument();

    await act(async () => {
      resolveHandoff({
        sessionId: 'astrodex-sess',
        imageUrl: '/api/preview/astrodex-sess',
        histogram: { r: [], g: [], b: [] },
        dimensions: { width: 5, height: 5 },
        astrodexItemId: 'item-1',
        objectName: 'M42',
      });
    });

    await screen.findByTestId('editor-view');
    const session = JSON.parse(screen.getByTestId('editor-session').textContent ?? '{}');
    expect(session).toMatchObject({
      sessionId: 'astrodex-sess',
      astrodex: { itemId: 'item-1', objectName: 'M42' },
    });
  });

  it('resumes a handoff carried in the query string', async () => {
    window.history.pushState({}, '', '/?handoff=from-search');
    mocked.resumeAstrodexHandoff.mockResolvedValue({
      sessionId: 'astrodex-sess-2',
      imageUrl: '/api/preview/astrodex-sess-2',
      histogram: { r: [], g: [], b: [] },
      dimensions: { width: 5, height: 5 },
      astrodexItemId: 'item-2',
      objectName: null,
    });

    render(<App />);

    await screen.findByTestId('editor-view');
    expect(mocked.resumeAstrodexHandoff).toHaveBeenCalledWith('from-search');
  });

  it('does not treat an unrelated hash query as a handoff', () => {
    window.history.pushState({}, '', '#/?foo=bar');
    render(<App />);

    expect(mocked.resumeAstrodexHandoff).not.toHaveBeenCalled();
    expect(screen.getByTestId('image-upload')).toBeInTheDocument();
  });

  it('shows the handoff error message when resuming fails', async () => {
    mocked.resumeAstrodexHandoff.mockRejectedValue(new Error('bad token'));
    window.history.pushState({}, '', '#/?handoff=tok-err');

    render(<App />);

    expect(await screen.findByText('bad token')).toBeInTheDocument();
    expect(screen.getByTestId('image-upload')).toBeInTheDocument();
  });

  it('falls back to a generic handoff error when the rejection is not an Error', async () => {
    mocked.resumeAstrodexHandoff.mockRejectedValue('nope');
    window.history.pushState({}, '', '#/?handoff=tok-err2');

    render(<App />);

    expect(await screen.findByText('Could not open the AstroDex image')).toBeInTheDocument();
  });
});
