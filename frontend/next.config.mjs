/** @type {import('next').NextConfig} */

// Proxy /api/* to the FastAPI backend so the browser calls a same-origin path
// (no CORS) and the token travels in the Authorization header. Configure the
// backend origin with API_URL (server-side env), defaulting to local dev.
const API_URL = process.env.API_URL ?? "http://localhost:8000";

const nextConfig = {
  reactStrictMode: true,
  // Emit a self-contained server bundle for a small production Docker image.
  output: "standalone",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${API_URL}/api/:path*` }];
  },
};

export default nextConfig;
