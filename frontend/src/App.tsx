import { useMemo, useState } from 'react';

import { EditorView } from '@/components/EditorView';
import { ImageUpload } from '@/components/ImageUpload';
import { apiClient } from '@/services/api';
import type { UploadResponse } from '@/types';

/**
 * Root orchestrator.
 *
 * When opened from AstroDex the URL carries `image_id`, `astrodex_url` and
 * `token` query params; otherwise the app runs in standalone mode.
 */
export default function App() {
  const [session, setSession] = useState<UploadResponse | null>(null);
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

  return (
    <div className="min-h-screen">
      <header className="flex items-center justify-between border-b border-white/10 px-6 py-4">
        <h1 className="text-lg font-semibold">{import.meta.env.VITE_APP_NAME ?? 'MyAstroShine'}</h1>
        <span className="text-xs text-gray-400">v{import.meta.env.VITE_APP_VERSION ?? '0.1.0'}</span>
      </header>

      <main className="p-6">
        {error && <p className="mb-4 rounded bg-red-500/20 px-4 py-2 text-sm text-red-200">{error}</p>}
        {session ? (
          <EditorView session={session} astrodexContext={astrodexContext} />
        ) : (
          <ImageUpload onUpload={handleUpload} isLoading={isUploading} />
        )}
      </main>
    </div>
  );
}
