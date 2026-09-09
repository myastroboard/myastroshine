# Third-party components

MyAstroShine is licensed under AGPL-3.0-or-later. Its Python and JavaScript
dependencies are declared in `backend/requirements*.txt` and
`frontend/package.json` and carry their own (OSI-approved) licenses.

## Optional external ML engines - NOT bundled

MyAstroShine can *invoke* the following tools when an operator installs them, but
**ships none of them** - no binary, no model weights, no vendored code. They are
run at arm's length as a subprocess (write a file, run the process, read a file
back). Setup: `docs/DEPLOYMENT.md` "External ML engines"; how the integration
works: `docs/ALGORITHMS.md` "Quality path".

### StarNet2 and DeepSNR (`starnetastro.com`, (c) 2026 Mikita (Nikita) Misiura)

Optional backends for star removal (`star_removal_engine = "starnet2"`) and
denoise (`denoise_engine = "deepsnr"`).
Free of charge, closed source, **not redistributable**. Both ship an identical
`LICENSE.txt` ("STARNET2 / DEEPSNR SOFTWARE LICENSE AGREEMENT"); the terms that
bear on this integration:

- **Grant**: "a non-exclusive, non-transferable license to use \[the software\]
  solely for astrophotography image processing." MyAstroShine's use - shelling
  out to it to remove stars from / denoise an astrophoto - is squarely within
  this grant. Nothing in the licence restricts invocation from other software or
  use on a server.
- **Non-transferable** is why MyAstroShine bundles nothing: the operator must
  obtain their own copy from `starnetastro.com`. We ship no binary, no
  `*_weights.onnx`, no vendored code; `engines/` is git-ignored.
- **"shall not be used to create any commercial software"** (restriction 2a).
  MyAstroShine is AGPL-3.0, free, and is not *created using* these tools - it is
  an independent program that optionally calls them. The reference deployment is
  self-hosted and non-monetised, which keeps it clear of this clause. **An
  operator who monetises their instance takes on that clause themselves.**
- **"shall not share full-scale raw input images ... that ... aid in developing
  competitive products"** (restriction 2b): do not commit or publish full-
  resolution before/after images produced with these tools.
- The operator accepts `LICENSE.txt` on download and is responsible for staying
  within it. MyAstroShine's AGPL grant does not extend to these tools, and
  calling them does not make them part of MyAstroShine.

If no path is configured (the default), these tools play no part and the
classical, fully-AGPL code path is the only one that runs.

The historical `nekitmm/starnet` lineage (MIT code, **CC BY-NC-SA 4.0** weights)
is not used.
