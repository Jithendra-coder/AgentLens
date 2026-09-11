# ADR-054: Same-origin dashboard mutations and defensive response headers

The Next.js BFF accepts mutations only when the browser `Origin` exactly
matches the request origin. It adds CSP and standard browser hardening headers
at the dashboard boundary while keeping the API credential server-side.
