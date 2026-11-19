# Pinned dependencies

Holds that keep a dependency below its latest release, or that force a transitive version. Each
entry is rechecked at every dependency update (`maj-dependances` routine).

Every backend requirement is pinned with `==` on purpose: the pins track the latest release and
`scripts/check_deps_fresh.py` enforces it. Only the holds below are deliberate exceptions; the
freshness check skips them through `scripts/deps_fresh_ignore.txt`.

## typescript (npm, frontend/package.json)

- **Held at**: `~6.0.3` (also listed in `scripts/deps_fresh_ignore.txt`)
- **Latest release when held**: 7.0.2 (rechecked 2026-11-19)
- **Reason**: `typescript-eslint` 8.73.0 (latest) declares the peer dependency
  `typescript >=4.8.4 <6.1.0`. TypeScript 6.1+ or 7.x would break `npm run lint`.
- **Reference**: `npm view typescript-eslint@latest peerDependencies`
- **Lift when**: a `typescript-eslint` release whose `typescript` peer range includes 7.x is
  published on the `latest` dist-tag (the v8 line ships as `rc-v8` for now). Then bump both
  together.
- **How to recheck**: `npm view typescript-eslint@latest peerDependencies`, then
  `npm run lint && npm run typecheck && npm test && npm run build` in `frontend/`.
- **Held on**: before 2026-11-19 (date not recorded)
- **Last check**: 2026-11-19, still valid (peer range unchanged at `<6.1.0`).

## minimatch (npm, frontend/package.json `overrides`)

- **Held at**: `"overrides": { "minimatch": "^11.0.5" }` (a floor, not a ceiling)
- **Latest release when checked**: 11.0.9
- **Reason**: forces every transitive copy to 11.0.5 or later. Added in commit e5a1637
  (2026-11-07) without a stated reason. Most likely a security floor: GHSA-g3hv-75wg-m249
  (denial of service, fixed in 11.0.1) and older ReDoS advisories affect earlier versions.
  `@typescript-eslint/typescript-estree` 8.73.0 still accepts `^11.0.1`.
- **Reference**: https://github.com/advisories/GHSA-g3hv-75wg-m249
- **Lift when**: every consumer in `npm ls minimatch` (`eslint`, `@eslint/config-array`,
  `@typescript-eslint/typescript-estree`) declares a range whose minimum is at least 11.0.5,
  or the maintainer confirms the override was added for a different reason.
- **How to recheck**: `npm ls minimatch`, then `npm view <consumer>@<version> dependencies.minimatch`
  for each consumer.
- **Held on**: 2026-11-07
- **Last check**: 2026-11-19, uncertain: the original reason is not recorded. Today it changes
  nothing (every copy resolves to 11.0.5), so it is harmless to keep.
