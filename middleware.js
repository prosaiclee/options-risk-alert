// HTTP Basic Auth for the Options Risk Dashboard.
//
// Credentials come ONLY from Vercel project environment variables — never hardcode them:
//   BASIC_AUTH_USER, BASIC_AUTH_PASSWORD
//
// Fail-closed: if the env vars are unset, every request is rejected with 401.
// This protects the personal/experimental market data from public exposure.

export const config = {
  matcher: "/(.*)",
};

function timingSafeEqual(a, b) {
  // Length-independent comparison to avoid trivial timing leaks.
  if (typeof a !== "string" || typeof b !== "string") return false;
  let mismatch = a.length === b.length ? 0 : 1;
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i++) {
    mismatch |= a.charCodeAt(i) ^ b.charCodeAt(i);
  }
  return mismatch === 0;
}

export default function middleware(request) {
  const expectedUser = process.env.BASIC_AUTH_USER;
  const expectedPass = process.env.BASIC_AUTH_PASSWORD;

  const unauthorized = () =>
    new Response("Authentication required.", {
      status: 401,
      headers: {
        "WWW-Authenticate": 'Basic realm="Options Risk Dashboard", charset="UTF-8"',
      },
    });

  // Fail closed when credentials are not configured.
  if (!expectedUser || !expectedPass) {
    return unauthorized();
  }

  const header = request.headers.get("authorization") || "";
  if (!header.startsWith("Basic ")) {
    return unauthorized();
  }

  let decoded = "";
  try {
    decoded = atob(header.slice(6));
  } catch {
    return unauthorized();
  }

  const separator = decoded.indexOf(":");
  if (separator === -1) {
    return unauthorized();
  }
  const user = decoded.slice(0, separator);
  const pass = decoded.slice(separator + 1);

  const ok =
    timingSafeEqual(user, expectedUser) && timingSafeEqual(pass, expectedPass);
  if (!ok) {
    return unauthorized();
  }

  // Authorized: returning undefined continues to the static asset.
  return undefined;
}
