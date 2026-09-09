# Third-party components

MyAstroShine is licensed under AGPL-3.0-or-later. Its Python and JavaScript
dependencies are declared in `backend/requirements*.txt` and
`frontend/package.json` and carry their own (OSI-approved) licenses.

## Optional external ML engines - NOT bundled

MyAstroShine can *invoke* the following tools when an operator installs them, but
**ships none of them** - no binary, no model weights, no vendored code. They are
run at arm's length as a subprocess (write a file, run the process, read a file
back). See `initial_plan/13_EXTERNAL_ML_ENGINES.md` and
`docs/DEPLOYMENT.md` "External ML engines".

### StarNet2 and DeepSNR (`starnetastro.com`, (c) Mikita Misiura)

- Optional backends for star removal (`star_removal_engine = "starnet2"`) and,
  later, denoise.
- Free of charge but **not open source and not redistributable**: "all rights
  reserved", and the underlying models are non-commercial. The historical
  `nekitmm/starnet` weights are CC BY-NC-SA 4.0.
- The operator downloads the tool directly from `starnetastro.com`, accepts its
  bundled `LICENSE.txt`, and is solely responsible for staying within its terms
  (in particular the non-commercial restriction). MyAstroShine's own AGPL grant
  does not extend to it, and calling it does not make it part of MyAstroShine.
- If no path is configured (the default), these tools play no part and the
  classical, fully-AGPL code path is the only one that runs.
