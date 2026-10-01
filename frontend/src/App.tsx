import { useEffect, useRef, useState } from 'react';

import { EditorView } from '@/components/EditorView';
import { Footer } from '@/components/Footer';
import { ImageUpload } from '@/components/ImageUpload';
import { SettingsView } from '@/components/SettingsView';
import { ChevronIcon, GearIcon } from '@/components/icons';
import { StackUploadZone } from '@/components/stacking/StackUploadZone';
import { StackView } from '@/components/stacking/StackView';
import { useServerConfig } from '@/hooks/useServerConfig';
import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';
import type { EditorSession } from '@/types';

type Route = 'editor' | 'settings';

/** Single-image enhancement vs multi-frame stacking. */
type EditorMode = 'single' | 'stack';

function readRoute(): Route {
  return window.location.hash.replace(/^#\/?/, '') === 'settings' ? 'settings' : 'editor';
}

function navigate(route: Route): void {
  window.location.hash = route === 'settings' ? '#/settings' : '#/';
}

/**
 * The Astrodex handoff token, from either the query string (`?handoff=`) or the
 * hash (`#/?handoff=`) - the board builds the URL with hash routing, so the
 * token usually rides in the fragment where `location.search` never sees it.
 */
function readHandoffToken(): string | null {
  const fromSearch = new URLSearchParams(window.location.search).get('handoff');
  if (fromSearch) {
    return fromSearch;
  }
  const query = window.location.hash.slice(window.location.hash.indexOf('?') + 1);
  return window.location.hash.includes('?')
    ? new URLSearchParams(query).get('handoff')
    : null;
}

/** Minimal hash routing - no dependency, keeps the browser back button working. */
function useRoute(): Route {
  const [route, setRoute] = useState<Route>(readRoute);
  useEffect(() => {
    const onChange = () => setRoute(readRoute());
    window.addEventListener('hashchange', onChange);
    return () => window.removeEventListener('hashchange', onChange);
  }, []);
  return route;
}

/**
 * Root orchestrator.
 *
 * When opened from Astrodex the URL carries a single signed `handoff` token;
 * otherwise the app runs in standalone mode.
 */
export default function App() {
  const { t } = useTranslation();
  const route = useRoute();
  const serverConfig = useServerConfig();
  const [mode, setMode] = useState<EditorMode>('single');
  const [stackWorking, setStackWorking] = useState(false);
  // Frames dropped on the landing screen's stacking zone, handed to StackView.
  const [stackSeed, setStackSeed] = useState<File[]>([]);
  const [session, setSession] = useState<EditorSession | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  // 0-1 while the file bytes transfer; null once they're sent and the server is
  // decoding (indeterminate). Undefined/not-uploading between sessions.
  const [uploadProgress, setUploadProgress] = useState<number | null>(null);
  const [resumingHandoff, setResumingHandoff] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const handoffStarted = useRef(false);

  // Opened from MyAstroBoard: the URL carries a signed `handoff` token. The
  // backend verifies it and pulls the source image; we land straight in the
  // editor. The param is stripped once consumed (it is single-use anyway).
  useEffect(() => {
    const handoff = readHandoffToken();
    if (!handoff || handoffStarted.current) {
      return;
    }
    handoffStarted.current = true;
    // Drop the token from the URL (it is single-use) and land on the editor route.
    window.history.replaceState(null, '', `${window.location.pathname}#/`);
    setResumingHandoff(true);
    setError(null);
    apiClient
      .resumeAstrodexHandoff(handoff)
      .then((resumed) => {
        setSession({
          sessionId: resumed.sessionId,
          histogram: resumed.histogram,
          dimensions: resumed.dimensions,
          astrodex: { itemId: resumed.astrodexItemId, objectName: resumed.objectName },
        });
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : 'Could not open the Astrodex image');
      })
      .finally(() => setResumingHandoff(false));
  }, []);

  async function handleUpload(file: File): Promise<void> {
    setIsUploading(true);
    setUploadProgress(null);
    setError(null);
    try {
      const uploaded = await apiClient.uploadImage(file, (fraction) => {
        setUploadProgress(fraction < 1 ? fraction : null);
      });
      setSession({ ...uploaded, originalFilename: file.name });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
      setUploadProgress(null);
    }
  }

  function handleStackFiles(files: File[]): void {
    if (files.length === 0) {
      return;
    }
    setError(null);
    setStackSeed(files);
    setMode('stack');
  }

  function handleLeaveStack(): void {
    setStackSeed([]);
    setMode('single');
  }

  function handleEnhanceComposite(sessionId: string): void {
    setSession({ sessionId, isStack: true });
    setStackSeed([]);
    setMode('single');
    setStackWorking(false);
  }

  function handleExitEditor(): void {
    setSession(null);
    setError(null);
  }

  // The landing screen: nothing loaded yet, nothing in flight.
  const landing =
    route === 'editor' && mode === 'single' && !session && !resumingHandoff && !isUploading;

  return (
    // Below lg the editor's workflow rail is a fixed bottom tab bar - pad the
    // page so the footer isn't trapped behind it.
    <div className={`flex min-h-screen flex-col ${session && route === 'editor' ? 'max-lg:pb-16' : ''}`}>
      <header className="sticky top-0 z-40 border-b border-hairline bg-canvas/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1360px] items-center justify-between px-4 sm:px-6">
          <button
            type="button"
            className="flex items-center gap-2.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent"
            onClick={() => navigate('editor')}
          >
            <img
              src={`${import.meta.env.BASE_URL}logo.png`}
              alt=""
              width={28}
              height={28}
              className="h-7 w-7 shrink-0"
              draggable={false}
            />
            <span className="text-sm font-semibold tracking-tight text-ink">
              {import.meta.env.VITE_APP_NAME ?? 'MyAstroShine'}
            </span>
          </button>
          <button
            type="button"
            className={route === 'settings' ? 'btn btn-outline btn-sm' : 'btn btn-ghost btn-sm'}
            aria-current={route === 'settings' ? 'page' : undefined}
            onClick={() => navigate(route === 'settings' ? 'editor' : 'settings')}
          >
            <GearIcon className="h-4 w-4" />
            {t('app.nav_settings')}
          </button>
        </div>
      </header>

      <div className="relative flex-1">
        {landing && <div className="starfield pointer-events-none absolute inset-0" aria-hidden />}
        {route === 'settings' ? (
          <SettingsView onClose={() => navigate('editor')} />
        ) : (
          <main className="relative mx-auto flex max-w-[1360px] flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
            {error && (
              <p className="rounded-md border border-danger/30 bg-danger-wash px-4 py-2.5 text-sm text-danger">
                {error}
              </p>
            )}

            {mode === 'stack' && !stackWorking && (
              <button
                type="button"
                className="btn btn-ghost btn-sm self-start"
                onClick={handleLeaveStack}
              >
                <ChevronIcon className="h-3.5 w-3.5 rotate-180" />
                {t('app.back_to_single')}
              </button>
            )}

            {mode === 'stack' ? (
              <StackView
                initialFiles={stackSeed}
                onEnhanceComposite={handleEnhanceComposite}
                onWorkingChange={setStackWorking}
              />
            ) : session ? (
              <EditorView session={session} onExit={handleExitEditor} />
            ) : resumingHandoff ? (
              <p className="panel text-sm text-muted">{t('app.opening_from_astrodex')}</p>
            ) : isUploading ? (
              <div className="mx-auto w-full max-w-xl">
                <ImageUpload
                  onUpload={handleUpload}
                  isLoading
                  progress={uploadProgress}
                  maxSizeMb={serverConfig.maxImageSizeMb}
                />
              </div>
            ) : (
              // Two ways in, side by side: what you have decides where you drop it.
              <div className="mx-auto grid w-full max-w-4xl gap-5 pt-2 md:grid-cols-2 md:pt-8">
                <ImageUpload
                  onUpload={handleUpload}
                  isLoading={false}
                  progress={uploadProgress}
                  maxSizeMb={serverConfig.maxImageSizeMb}
                />
                <StackUploadZone
                  compact={false}
                  maxSizeMb={serverConfig.maxImageSizeMb}
                  onAddFiles={handleStackFiles}
                />
              </div>
            )}
          </main>
        )}
      </div>

      <Footer />
    </div>
  );
}
