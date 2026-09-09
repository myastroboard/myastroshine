# External ML engines

This directory is **bind-mounted read-only into the `api` and `worker` containers
at `/opt/engines`** (see `docker-compose.yml` / `docker-compose.dev.yml`). It is
empty by default and has no effect until you point a setting at a binary in it.

MyAstroShine **bundles no models or binaries** - see `../THIRD_PARTY.md`. Anything
you put here you install yourself and use under its own licence terms.

## Adding StarNet2 (optional star-removal engine)

1. Download the **linux-x64** CLI build from <https://starnetastro.com/> and read
   its bundled `LICENSE.txt` - it grants use "solely for astrophotography image
   processing"; the model is non-commercial. Tested against **StarNet2 2.6.1**.
2. Unpack it here, keeping the package layout, e.g. `engines/starnet2/starnet2`
   next to `StarNet2_weights.onnx` and `lib/`.
3. `docker compose up -d` (the mount is already active).
4. In **Settings → Advanced → External ML engines**, set
   `starnet2_path` to `/opt/engines/starnet2/starnet2`, save, and click
   **Re-check engines**.

DeepSNR (denoise) works the same way via `deepsnr_path`.

Everything except this README is git-ignored.
