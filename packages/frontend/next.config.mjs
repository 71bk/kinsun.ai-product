import { fileURLToPath } from 'node:url';

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  // The frontend imports the shared workspace package, so standalone tracing
  // must start at the monorepo root rather than the frontend package directory.
  outputFileTracingRoot: fileURLToPath(new URL('../..', import.meta.url)),
  reactStrictMode: true,
  transpilePackages: ['@elderly-care/shared'],
  /* The care workspace moved from /dashboard to /staff and elder consent from
     /consent to /elder/consent, so every role now lives under its own prefix.
     These keep existing bookmarks and any link already sent out working.
     Temporary (307/308-free) on purpose: `permanent: true` is cached by the
     browser indefinitely, which is painful to undo while the information
     architecture is still settling. Revisit once the URLs are stable. */
  redirects: async () => [
    { source: '/dashboard', destination: '/staff', permanent: false },
    { source: '/dashboard/assignments', destination: '/staff/assignments', permanent: false },
    { source: '/dashboard/:elderId', destination: '/staff/elders/:elderId', permanent: false },
    { source: '/consent', destination: '/elder/consent', permanent: false },
  ],
  headers: async () => [
    {
      source: '/sw.js',
      headers: [
        { key: 'Content-Type', value: 'application/javascript; charset=utf-8' },
        { key: 'Cache-Control', value: 'no-cache, no-store, must-revalidate' },
        { key: 'Service-Worker-Allowed', value: '/' },
      ],
    },
  ],
};

export default nextConfig;
