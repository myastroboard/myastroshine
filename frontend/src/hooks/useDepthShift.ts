import { useCallback, useState } from 'react';

const API_URL = import.meta.env.VITE_API_URL ?? '/api';

/** Requests depth-map generation and exposes the resulting layer URLs. */
export function useDepthShift(sessionId: string) {
  const [layerUrls, setLayerUrls] = useState<string[]>([]);
  const [intensity, setIntensity] = useState(50);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const generate = useCallback(
    async (numLayers = 7) => {
      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(`${API_URL}/depth-shift/${sessionId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ intensity, num_layers: numLayers }),
        });
        if (!response.ok) {
          throw new Error(`Depth shift failed: ${response.status}`);
        }
        const data = (await response.json()) as { depth_layers: Array<{ image_url: string }> };
        setLayerUrls(data.depth_layers.map((layer) => `${API_URL}${layer.image_url}`));
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Depth shift failed');
      } finally {
        setIsLoading(false);
      }
    },
    [sessionId, intensity],
  );

  return { layerUrls, intensity, setIntensity, generate, isLoading, error };
}
