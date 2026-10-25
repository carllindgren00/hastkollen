// Lösenordsskydd framför appen. Lösenordet ligger som hemligheten APP_PASSWORD i Cloudflare,
// aldrig i koden. Rätt lösenord ger en signerad cookie som gäller i 30 dagar; byts lösenordet
// blir alla gamla inloggningar ogiltiga.
const COOKIE = "v85_session";
const MAX_AGE = 30 * 24 * 3600;
const enc = new TextEncoder();

async function hmac(secret, msg) {
  const key = await crypto.subtle.importKey("raw", enc.encode(secret), {name: "HMAC", hash: "SHA-256"}, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, enc.encode(msg));
  return btoa(String.fromCharCode(...new Uint8Array(sig))).replace(/[+/=]/g, c => ({"+": "-", "/": "_", "=": ""})[c]);
}

// jämför i konstant tid, så att svarstiden inte avslöjar hur nära en gissning var
async function same(a, b) {
  const [x, y] = await Promise.all([a, b].map(s => crypto.subtle.digest("SHA-256", enc.encode(s))));
  return crypto.subtle.timingSafeEqual(x, y);
}

async function validSession(req, secret) {
  const m = (req.headers.get("Cookie") || "").match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`));
  if (!m) return false;
  const [exp, sig] = m[1].split(".");
  if (!exp || !sig || Number(exp) < Date.now() / 1000) return false;
  return same(sig, await hmac(secret, exp));
}

function loginPage(error) {
  const html = `<!doctype html><html lang="sv"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>V85-kollen</title><meta name="robots" content="noindex">
<style>
:root{--bg:#f6f7f5;--surface:#fff;--fg:#17201a;--muted:#6b776e;--line:#e3e7e2;--accent:#1e6a46;--accent-ink:#fff;--warn:#a33b2b}
@media (prefers-color-scheme:dark){:root{--bg:#101411;--surface:#171d19;--fg:#e8ede9;--muted:#8e9b92;--line:#252e28;--accent:#56c28a;--accent-ink:#0b1810;--warn:#ef8a78}}
*{box-sizing:border-box}
body{margin:0;min-height:100vh;display:grid;place-items:center;background:var(--bg);color:var(--fg);font:16px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif;padding:16px}
form{width:100%;max-width:340px;background:var(--surface);border:1px solid var(--line);border-radius:16px;padding:24px;display:flex;flex-direction:column;gap:14px}
h1{margin:0;font-size:1.6rem;letter-spacing:-.015em}
p{margin:0;color:var(--muted);font-size:.9rem}
input{font:inherit;padding:12px;border:1px solid var(--line);border-radius:10px;background:var(--bg);color:var(--fg);width:100%}
button{font:inherit;font-weight:600;border:0;border-radius:10px;padding:12px;background:var(--accent);color:var(--accent-ink);cursor:pointer}
.err{color:var(--warn);font-size:.88rem}
</style></head><body>
<form method="post" action="/login">
<h1>V85-kollen</h1>
<p>Skriv lösenordet för att öppna appen.</p>
<input type="password" name="password" autocomplete="current-password" aria-label="Lösenord" required autofocus>
${error ? `<p class="err" role="alert">${error}</p>` : ""}
<button type="submit">Logga in</button>
</form></body></html>`;
  return new Response(html, {status: 401, headers: {"Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}});
}

export default {
  async fetch(req, env) {
    const secret = env.APP_PASSWORD;
    // utan lösenord inställt släpps ingen in
    if (!secret) return new Response("Lösenordet är inte inställt i Cloudflare (APP_PASSWORD).", {status: 503});
    const url = new URL(req.url);

    if (url.pathname === "/login" && req.method === "POST") {
      const form = await req.formData().catch(() => null);
      const pw = form ? String(form.get("password") || "") : "";
      if (!(await same(pw, secret))) {
        await new Promise(r => setTimeout(r, 1000)); // bromsar den som gissar
        return loginPage("Fel lösenord.");
      }
      const exp = String(Math.floor(Date.now() / 1000) + MAX_AGE);
      return new Response(null, {status: 303, headers: {
        "Location": "/",
        "Set-Cookie": `${COOKIE}=${exp}.${await hmac(secret, exp)}; Max-Age=${MAX_AGE}; Path=/; HttpOnly; Secure; SameSite=Lax`,
      }});
    }

    if (url.pathname === "/logout") {
      return new Response(null, {status: 303, headers: {"Location": "/", "Set-Cookie": `${COOKIE}=; Max-Age=0; Path=/; HttpOnly; Secure; SameSite=Lax`}});
    }

    if (await validSession(req, secret)) {
      const res = await env.ASSETS.fetch(req);
      const out = new Response(res.body, res);
      out.headers.set("Cache-Control", "private, no-cache");
      out.headers.set("X-Robots-Tag", "noindex");
      return out;
    }

    const html = req.method === "GET" && (req.headers.get("Accept") || "").includes("text/html");
    return html ? loginPage("") : new Response("Inloggning krävs", {status: 401, headers: {"Cache-Control": "no-store"}});
  },
};
