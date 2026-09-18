const base = (process.env.NEXT_PUBLIC_API_BASE ?? "").replace(/\/$/, "");
export class ApiError extends Error { constructor(message:string, public status:number, public code:string) { super(message); } }
export function apiUrl(path:string) { return `${base}${path}`; }
export async function request<T>(path:string, init?:RequestInit):Promise<T> {
  const response = await fetch(apiUrl(path), { ...init, cache:"no-store" });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new ApiError(body?.detail?.message ?? `The local service returned ${response.status}. Please try again.`, response.status, body?.detail?.code ?? "request_failed");
  }
  return response.json() as Promise<T>;
}
export function errorMessage(error:unknown) { return error instanceof Error ? error.message : "The local service could not complete the request."; }
