// Where the app lives on its server - so every URL it builds stays inside it.
//
// MyAstroShine is usually served at the root of its host, but it can also sit
// under a path prefix (a reverse proxy, or a Home Assistant ingress:
// /api/hassio_ingress/<token>/). Routing is hash-based (#/settings), so the page
// path is always the app's own root directory; every server URL is built from
// it instead of from "/", which would escape the prefix.

/** The directory of the current page: `/` at the root, `/<prefix>/` under one. */
export function pageDirectory(pathname: string = window.location.pathname): string {
  return pathname.slice(0, pathname.lastIndexOf('/') + 1) || '/';
}

/** A path on the app's own server (`api`, `ws`, ...) under the page directory. */
export function appPath(path: string, pathname?: string): string {
  return pageDirectory(pathname) + path.replace(/^\/+/, '');
}
