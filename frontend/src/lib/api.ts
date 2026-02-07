/**
 * Base URL for backend API. Set VITE_API_URL in .env to override.
 * In dev, defaults to http://localhost:8001 so requests hit the backend instead of the Vite server.
 */
export function getApiBaseUrl(): string {
  const env = import.meta.env.VITE_API_URL as string | undefined;
  if (env !== undefined && env !== '') return env;
  if (import.meta.env.DEV) return 'http://localhost:8001';
  return '';
}

export async function apiFetch<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const base = getApiBaseUrl().replace(/\/$/, '');
  const url = path.startsWith('http') ? path : `${base}${path.startsWith('/') ? path : `/${path}`}`;
  const res = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}
