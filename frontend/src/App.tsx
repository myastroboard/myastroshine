import { useEffect, useMemo, useState } from 'react';

import { EditorView } from '@/components/EditorView';
import { ImageUpload } from '@/components/ImageUpload';
import { SettingsView } from '@/components/SettingsView';
import { StackMode, type EditorMode } from '@/components/stacking/StackMode';
import { StackView } from '@/components/stacking/StackView';
import { apiClient } from '@/services/api';
import type { EditorSession } from '@/types';

type Route = 'editor' | 'settings';

function readRoute(): Route {
  return window.location.hash.replace(/^#\/?/, '') === 'settings' ? 'settings' : 'editor';
}

function navigate(route: Route): void {
  window.location.hash = route === 'settings' ? '#/settings' : '#/';
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
 * When opened from AstroDex the URL carries `image_id`, `astrodex_url` and
 * `token` query params; otherwise the app runs in standalone mode.
 */
export default function App() {
  const route = useRoute();
  const [mode, setMode] = useState<EditorMode>('single');
  const [session, setSession] = useState<EditorSession | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const astrodexContext = useMemo(() => {
    const params = new URLSearchParams(window.location.search);
    const imageId = params.get('image_id');
    if (!imageId) {
      return null;
    }
    return {
      imageId,
      callbackUrl: params.get('astrodex_url') ?? '',
      token: params.get('token') ?? '',
    };
  }, []);

  async function handleUpload(file: File): Promise<void> {
    setIsUploading(true);
    setError(null);
    try {
      setSession(await apiClient.uploadImage(file));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  }

  function handleEnhanceComposite(sessionId: string): void {
    setSession({ sessionId });
    setMode('single');
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-hairline bg-canvas/80 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-[1200px] items-center justify-between px-4 sm:px-6">
          <button
            type="button"
            className="flex items-center gap-2.5 rounded-md outline-none focus-visible:ring-2 focus-visible:ring-accent"
            onClick={() => navigate('editor')}
          >
            <BrandMark />
            <span className="text-sm font-semibold tracking-tight text-ink">
              {import.meta.env.VITE_APP_NAME ?? 'MyAstroShine'}
            </span>
          </button>
          <div className="flex items-center gap-3">
            <button
              type="button"
              className={route === 'settings' ? 'btn btn-outline btn-sm' : 'btn btn-ghost btn-sm'}
              aria-current={route === 'settings' ? 'page' : undefined}
              onClick={() => navigate(route === 'settings' ? 'editor' : 'settings')}
            >
              Settings
            </button>
            <span className="text-xs tabular-nums text-ghost">
              v{import.meta.env.VITE_APP_VERSION ?? '0.1.0'}
            </span>
          </div>
        </div>
      </header>

      {route === 'settings' ? (
        <SettingsView onClose={() => navigate('editor')} />
      ) : (
        <main className="mx-auto flex max-w-[1200px] flex-col gap-6 px-4 py-6 sm:px-6 sm:py-8">
          {error && (
            <p className="rounded-md border border-danger/30 bg-danger-wash px-4 py-2.5 text-sm text-danger">
              {error}
            </p>
          )}

          <StackMode mode={mode} onModeChange={setMode} />

          {mode === 'stack' ? (
            <StackView onEnhanceComposite={handleEnhanceComposite} />
          ) : session ? (
            <EditorView session={session} astrodexContext={astrodexContext} />
          ) : (
            <ImageUpload onUpload={handleUpload} isLoading={isUploading} />
          )}
        </main>
      )}
    </div>
  );
}

/** Compact aperture mark used in the header. */
function BrandMark() {
  return (
    <svg viewBox="0 0 24 24" className="h-6 w-6" role="img" aria-label="MyAstroShine" fill="none">
      <circle cx="12" cy="12" r="9" className="stroke-line-strong" strokeWidth="1.5" />
      <circle cx="12" cy="12" r="3.25" className="fill-accent" />
      <path
        d="M12 1.5v3M12 19.5v3M1.5 12h3M19.5 12h3"
        className="stroke-accent"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}
