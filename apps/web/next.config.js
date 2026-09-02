/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // three.js ships ESM that Next's server bundler needs to transpile; drei pulls it in.
  transpilePackages: ["three"],
  // Cloudflare Pages deployment: static export. `rewrites()` (removed below)
  // and Edge Middleware (see src/middleware.ts.disabled-for-static-export)
  // both require a live request-time server, which `output: 'export'`
  // explicitly does not provide — Next.js hard-fails the build if either is
  // present alongside it. Neither is actually load-bearing here:
  // apps/web/src/lib/api.ts's fetcher already calls the backend via the
  // ABSOLUTE NEXT_PUBLIC_API_URL, never a relative /api/v1/... path, so the
  // removed rewrite was dead configuration, not a behavior change.
  output: "export",
};

module.exports = nextConfig;
