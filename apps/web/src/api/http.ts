export class ApiError extends Error {
  status: number;
  code?: string;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    const structured =
      typeof detail === "object" && detail !== null
        ? (detail as { message?: string; code?: string })
        : null;
    const message =
      structured?.message ??
      (typeof detail === "string" ? detail : `Request failed (${status})`);
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = structured?.code;
    this.detail = detail;
  }
}

function resolveBaseUrl(): string {
  if (import.meta.env.DEV) {
    // Vite dev server proxies API routes to the backend (see vite.config.ts).
    return "";
  }
  return import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8010";
}

export function formatApiError(error: unknown, fallback = "Request failed."): string {
  if (error instanceof ApiError) {
    if (error.code) {
      return `${error.message} (${error.code})`;
    }
    return error.message;
  }
  if (error instanceof TypeError) {
    return "Cannot reach the API. Start the backend with: make dev-api";
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}

export async function apiFetch<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const baseUrl = resolveBaseUrl();
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...init?.headers,
      },
    });
  } catch (error) {
    if (error instanceof TypeError) {
      throw new ApiError(0, "Cannot reach the API. Start the backend with: make dev-api");
    }
    throw error;
  }

  if (!response.ok) {
    const contentType = response.headers.get("content-type") ?? "";
    let detail: unknown;
    if (contentType.includes("application/json")) {
      detail = await response.json();
    } else {
      detail = await response.text();
    }
    throw new ApiError(response.status, detail);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    const preview = (await response.text()).slice(0, 120);
    throw new ApiError(
      response.status,
      `Expected JSON from API but received ${contentType || "unknown content type"} (${preview})`,
    );
  }

  return response.json() as Promise<T>;
}

export function artifactFileUrl(promptId: string, filename: string): string {
  const baseUrl = resolveBaseUrl() || window.location.origin;
  return `${baseUrl}/registry/prompts/${encodeURIComponent(promptId)}/artifacts/${encodeURIComponent(filename)}`;
}

export const baseUrl = resolveBaseUrl() || "http://127.0.0.1:8010";
