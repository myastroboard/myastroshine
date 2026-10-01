import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { EngineInstaller } from '@/components/EngineInstaller';
import { ApiError, apiClient } from '@/services/api';
import type { EngineStatus, StagedEngine } from '@/types';

vi.mock('@/services/api', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/services/api')>()),
  apiClient: {
    stageEngine: vi.fn(),
    installEngine: vi.fn(),
    discardStagedEngine: vi.fn(),
    removeEngine: vi.fn(),
  },
}));

const mocked = vi.mocked(apiClient);

const FOUND: EngineStatus = {
  configured: true,
  found: true,
  version: '2.6.1',
  knownGood: true,
  detail: 'StarNet2 2.6.1 detected',
};

const STAGED: StagedEngine = {
  stagingId: 'abc123',
  engine: 'starnet2',
  archiveName: 'starnet2-linux.zip',
  status: FOUND,
  licenseText: 'STARNET2 SOFTWARE LICENSE AGREEMENT',
};

function renderInstaller(status?: EngineStatus, onChanged = vi.fn()) {
  const view = render(
    <EngineInstaller engine="starnet2" name="StarNet2" status={status} onChanged={onChanged} />,
  );
  return { ...view, onChanged };
}

function pick(file: File | null = new File(['zip'], 'starnet2-linux.zip')) {
  fireEvent.change(screen.getByLabelText('StarNet2 archive'), {
    target: { files: file ? [file] : [] },
  });
}

describe('EngineInstaller', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mocked.stageEngine.mockResolvedValue(STAGED);
    mocked.installEngine.mockResolvedValue({
      ...FOUND,
      installed: {
        version: '2.6.1',
        archiveName: 'starnet2-linux.zip',
        licenseAcceptedAt: '2026-10-01T07:00:00Z',
        path: '/data/engines/starnet2/starnet2',
      },
    });
    mocked.discardStagedEngine.mockResolvedValue(undefined);
    mocked.removeEngine.mockResolvedValue(undefined);
  });

  it('opens the picker from the install button', () => {
    renderInstaller();
    const click = vi.spyOn(HTMLInputElement.prototype, 'click').mockImplementation(() => undefined);

    fireEvent.click(screen.getByRole('button', { name: 'Install StarNet2 from its archive' }));

    expect(click).toHaveBeenCalled();
    click.mockRestore();
  });

  it('ignores a picker change without a file', () => {
    renderInstaller();

    pick(null);

    expect(mocked.stageEngine).not.toHaveBeenCalled();
  });

  it('shows upload progress, then the checking step', async () => {
    let report: (fraction: number) => void = () => undefined;
    let finish: (staged: StagedEngine) => void = () => undefined;
    mocked.stageEngine.mockImplementation((_engine, _file, onProgress) => {
      report = onProgress ?? report;
      return new Promise((resolve) => {
        finish = resolve;
      });
    });
    renderInstaller();

    pick();
    await waitFor(() => expect(mocked.stageEngine).toHaveBeenCalled());
    report(0.4);
    expect(await screen.findByText('Uploading... 40%')).toBeInTheDocument();
    report(1);
    expect(await screen.findByText('Checking the package...')).toBeInTheDocument();

    finish(STAGED);
    expect(await screen.findByText('STARNET2 SOFTWARE LICENSE AGREEMENT')).toBeInTheDocument();
  });

  it('installs only once the licence is accepted', async () => {
    const { onChanged } = renderInstaller();
    pick();

    const install = await screen.findByRole('button', { name: 'Install' });
    expect(install).toBeDisabled();
    expect(screen.getByText(/starnet2-linux\.zip: StarNet2 2\.6\.1 detected/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: /accept its licence/i }));
    fireEvent.click(install);

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith('/data/engines/starnet2/starnet2'));
    expect(mocked.installEngine).toHaveBeenCalledWith('starnet2', 'abc123');
    expect(screen.queryByText('STARNET2 SOFTWARE LICENSE AGREEMENT')).not.toBeInTheDocument();
  });

  it('reports an empty path when the install answer has no package', async () => {
    mocked.installEngine.mockResolvedValue({ ...FOUND, installed: null });
    const { onChanged } = renderInstaller();
    pick();
    fireEvent.click(await screen.findByRole('checkbox', { name: /accept its licence/i }));

    fireEvent.click(screen.getByRole('button', { name: 'Install' }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(''));
  });

  it('cancels a staged package, even if discarding it fails', async () => {
    mocked.discardStagedEngine.mockRejectedValue(new Error('offline'));
    renderInstaller();
    pick();

    fireEvent.click(await screen.findByRole('button', { name: 'Cancel' }));

    await waitFor(() =>
      expect(mocked.discardStagedEngine).toHaveBeenCalledWith('starnet2', 'abc123'),
    );
    expect(screen.queryByRole('button', { name: 'Install' })).not.toBeInTheDocument();
  });

  it('shows why a package was refused', async () => {
    mocked.stageEngine.mockRejectedValue(
      new ApiError(400, 'This StarNet2 build is for x86-64; this server is aarch64.', 'INVALID_ENGINE_ARCHIVE'),
    );
    renderInstaller();

    pick();

    expect(await screen.findByRole('alert')).toHaveTextContent(/this server is aarch64/);
  });

  it('shows an install failure', async () => {
    mocked.installEngine.mockRejectedValue(new ApiError(404, 'Unknown or expired staged engine package'));
    renderInstaller();
    pick();
    fireEvent.click(await screen.findByRole('checkbox', { name: /accept its licence/i }));

    fireEvent.click(screen.getByRole('button', { name: 'Install' }));

    expect(await screen.findByRole('alert')).toHaveTextContent(/expired/);
  });

  it('describes an installed package and removes it after a confirmation', async () => {
    const status: EngineStatus = {
      ...FOUND,
      installed: {
        version: null,
        archiveName: 'old.zip',
        licenseAcceptedAt: '2026-10-01T07:00:00Z',
        path: '/data/engines/starnet2/starnet2',
      },
    };
    const { onChanged } = renderInstaller(status);

    expect(screen.getByText(/Installed from old\.zip - version \?/)).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: 'Replace with another StarNet2 archive' }),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    expect(mocked.removeEngine).not.toHaveBeenCalled();
    fireEvent.blur(screen.getByRole('button', { name: 'Confirm removal' }));
    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm removal' }));

    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(''));
    expect(mocked.removeEngine).toHaveBeenCalledWith('starnet2');
  });

  it('shows a removal failure', async () => {
    mocked.removeEngine.mockRejectedValue('offline');
    renderInstaller({
      ...FOUND,
      installed: {
        version: '2.6.1',
        archiveName: 'a.zip',
        licenseAcceptedAt: '2026-10-01T07:00:00Z',
        path: '/x',
      },
    });

    fireEvent.click(screen.getByRole('button', { name: 'Remove' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm removal' }));

    expect(await screen.findByRole('alert')).toHaveTextContent('The engine operation failed');
  });
});
