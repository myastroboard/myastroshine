import { useEffect, useRef, useState } from 'react';

import { EditorView } from '@/components/EditorView';
import { Footer } from '@/components/Footer';
import { ImageUpload } from '@/components/ImageUpload';
import { SettingsView } from '@/components/SettingsView';
import { StackMode, type EditorMode } from '@/components/stacking/StackMode';
import { StackView } from '@/components/stacking/StackView';
import { useServerConfig } from '@/hooks/useServerConfig';
import { useTranslation } from '@/hooks/useTranslation';
import { apiClient } from '@/services/api';
import type { EditorSession } from '@/types';

type Route = 'editor' | 'settings';

function readRoute(): Route {
  return window.location.hash.replace(/^#\/?/, '') === 'settings' ? 'settings' : 'editor';
}

function navigate(route: Route): void {
  window.location.hash = route === 'settings' ? '#/settings' : '#/';
}

/**
 * The AstroDex handoff token, from either the query string (`?handoff=`) or the
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
 * When opened from AstroDex the URL carries a single signed `handoff` token;
 * otherwise the app runs in standalone mode.
 */
export default function App() {
  const { t } = useTranslation();
  const route = useRoute();
  const serverConfig = useServerConfig();
  const [mode, setMode] = useState<EditorMode>('single');
  const [stackWorking, setStackWorking] = useState(false);
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
        setError(err instanceof Error ? err.message : 'Could not open the AstroDex image');
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
      setSession(uploaded);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
      setUploadProgress(null);
    }
  }

  function handleEnhanceComposite(sessionId: string): void {
    setSession({ sessionId, isStack: true });
    setMode('single');
    setStackWorking(false);
  }

  function handleExitEditor(): void {
    setSession(null);
    setError(null);
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-40 border-b border-hairline bg-canvas/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1360px] items-center justify-between px-4 sm:px-6">
          <button
            type="button"
            className="flex items-center gap-2.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent"
            onClick={() => navigate('editor')}
          >
            <img
              src="/logo.png"
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
            {t('app.nav_settings')}
          </button>
        </div>
      </header>

      <div className="flex-1">
        {route === 'settings' ? (
          <SettingsView onClose={() => navigate('editor')} />
        ) : (
          <main className="mx-auto flex max-w-[1360px] flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
            {error && (
              <p className="rounded-md border border-danger/30 bg-danger-wash px-4 py-2.5 text-sm text-danger">
                {error}
              </p>
            )}

            {(mode === 'stack' ? !stackWorking : !session) && !resumingHandoff && (
              <StackMode mode={mode} onModeChange={setMode} />
            )}

            {mode === 'stack' ? (
              <StackView
                onEnhanceComposite={handleEnhanceComposite}
                onWorkingChange={setStackWorking}
              />
            ) : session ? (
              <EditorView session={session} onExit={handleExitEditor} />
            ) : resumingHandoff ? (
              <p className="panel text-sm text-muted">{t('app.opening_from_astrodex')}</p>
            ) : (
              <ImageUpload
                onUpload={handleUpload}
                isLoading={isUploading}
                progress={uploadProgress}
                maxSizeMb={serverConfig.maxImageSizeMb}
              />
            )}
          </main>
        )}
      </div>

      <Footer />
    </div>
  );
}
