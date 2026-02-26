/**
 * Backend API base URL.
 * - Development: defaults to http://localhost:5000 so API calls hit the backend.
 * - Production: defaults to '' (same origin) so /api and /auth are used on the same host (e.g. Cloudflare tunnel).
 * Set VITE_API_URL in frontend/.env to override (e.g. another backend host/port).
 */
export const API_BASE =
  import.meta.env.VITE_API_URL !== undefined && import.meta.env.VITE_API_URL !== ''
    ? import.meta.env.VITE_API_URL
    : import.meta.env.DEV
      ? 'http://localhost:5000'
      : '';
