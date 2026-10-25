// Nätet först, så att färsk ATG-data alltid vinner. Cachen används bara när hämtningen
// misslyckas: offline, eller när Cloudflare-inloggningen gått ut och skickar till inloggningssidan.
const CACHE = "v85-kollen-v2";
const SHELL = ["./", "index.html", "manifest.webmanifest", "icons/icon-192.png", "data/v85.json"];

self.addEventListener("install", e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(SHELL)).catch(() => {}).then(() => self.skipWaiting()));
});
self.addEventListener("activate", e => {
  e.waitUntil(caches.keys().then(ks => Promise.all(ks.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim()));
});
self.addEventListener("fetch", e => {
  const req = e.request, url = new URL(req.url);
  if (req.method !== "GET" || url.origin !== location.origin) return;
  // sidladdningar går rakt till nätet, så att Cloudflare kan visa inloggningen när den behövs
  if (req.mode === "navigate") {
    e.respondWith(fetch(req).catch(() => caches.match("index.html")));
    return;
  }
  e.respondWith(fetch(req).then(res => {
    if (res.ok && !res.redirected) { const copy = res.clone(); caches.open(CACHE).then(c => c.put(req, copy)); }
    return res;
  }).catch(() => caches.match(req, {ignoreSearch: true}).then(hit => {
    if (!hit) return Response.error();
    const h = new Headers(hit.headers); h.set("x-v85-cache", "1");
    return hit.blob().then(b => new Response(b, {status: hit.status, headers: h}));
  })));
});
