import { saveTokens } from "../storage/tokenStorage";

const API_BASE_URL = process.env.EXPO_PUBLIC_API_URL;

type ApiErrorPayload = {
  detail?: string | { msg?: string } | Array<{ msg?: string }>;
  message?: string;
};

export type LoginResponse = {
  access_token: string;
  refresh_token: string;
};

export type RegisterResponse = {
  message: string;
};

export class AuthServiceError extends Error {
  status: number | null;

  code: "CONFIG_ERROR" | "HTTP_ERROR" | "NETWORK_ERROR" | "UNKNOWN_ERROR";

  details?: unknown;

  constructor(
    message: string,
    options: {
      code: "CONFIG_ERROR" | "HTTP_ERROR" | "NETWORK_ERROR" | "UNKNOWN_ERROR";
      details?: unknown;
      status?: number | null;
    },
  ) {
    super(message);
    this.name = "AuthServiceError";
    this.code = options.code;
    this.details = options.details;
    this.status = options.status ?? null;
  }
}

function getApiBaseUrl(): string {
  if (!API_BASE_URL) {
    throw new AuthServiceError("Missing EXPO_PUBLIC_API_URL configuration.", {
      code: "CONFIG_ERROR",
    });
  }

  return API_BASE_URL.replace(/\/+$/, "");
}

function parseErrorMessage(payload: ApiErrorPayload | null, fallback: string): string {
  if (!payload) {
    return fallback;
  }

  if (typeof payload.message === "string" && payload.message.trim().length > 0) {
    return payload.message;
  }

  if (typeof payload.detail === "string" && payload.detail.trim().length > 0) {
    return payload.detail;
  }

  if (Array.isArray(payload.detail)) {
    const messages = payload.detail
      .map((item) => item.msg)
      .filter((value): value is string => typeof value === "string" && value.length > 0);

    if (messages.length > 0) {
      return messages.join(", ");
    }
  }

  if (
    payload.detail &&
    typeof payload.detail === "object" &&
    "msg" in payload.detail &&
    typeof payload.detail.msg === "string" &&
    payload.detail.msg.length > 0
  ) {
    return payload.detail.msg;
  }

  return fallback;
}

async function request<TResponse>(
  path: string,
  init: RequestInit,
  fallbackMessage: string,
): Promise<TResponse> {
  const url = `${getApiBaseUrl()}${path}`;

  let response: Response;

  try {
    response = await fetch(url, {
      ...init,
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        ...(init.headers ?? {}),
      },
    });
  } catch (error: unknown) {
    throw new AuthServiceError("Unable to reach the server. Check your connection.", {
      code: "NETWORK_ERROR",
      details: error,
    });
  }

  const rawBody = await response.text();
  let parsedBody: unknown = null;

  if (rawBody.length > 0) {
    try {
      parsedBody = JSON.parse(rawBody) as unknown;
    } catch {
      parsedBody = rawBody;
    }
  }

  if (!response.ok) {
    const payload =
      parsedBody && typeof parsedBody === "object" ? (parsedBody as ApiErrorPayload) : null;

    throw new AuthServiceError(parseErrorMessage(payload, fallbackMessage), {
      code: "HTTP_ERROR",
      details: parsedBody,
      status: response.status,
    });
  }

  return parsedBody as TResponse;
}

async function login(email: string, password: string): Promise<LoginResponse> {
  const response = await request<LoginResponse>(
    "/auth/login",
    {
      body: JSON.stringify({ email, password }),
      method: "POST",
    },
    "Login failed. Please try again.",
  );

  await saveTokens(response.access_token, response.refresh_token);

  return response;
}

async function register(email: string, password: string): Promise<RegisterResponse> {
  return request<RegisterResponse>(
    "/auth/register",
    {
      body: JSON.stringify({ email, password }),
      method: "POST",
    },
    "Registration failed. Please try again.",
  );
}

export const authService = {
  login,
  register,
};
