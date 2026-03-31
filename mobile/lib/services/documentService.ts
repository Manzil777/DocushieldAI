import { getTokens } from "../storage/tokenStorage";

type UploadDocumentPayload = {
  name?: string;
  type?: string;
  uri: string;
};

type UploadErrorPayload = {
  detail?: string | Array<{ msg?: string }>;
  message?: string;
};

export type UploadDocumentResponse = {
  document_id: string;
  fields: Record<string, unknown>;
  forgery: Record<string, unknown>;
  qr: Record<string, unknown>;
};

export class DocumentServiceError extends Error {
  status: number | null;

  code: "CONFIG_ERROR" | "HTTP_ERROR" | "NETWORK_ERROR" | "UNAUTHORIZED_ERROR";

  constructor(
    message: string,
    options: {
      code: "CONFIG_ERROR" | "HTTP_ERROR" | "NETWORK_ERROR" | "UNAUTHORIZED_ERROR";
      status?: number | null;
    },
  ) {
    super(message);
    this.name = "DocumentServiceError";
    this.code = options.code;
    this.status = options.status ?? null;
  }
}

function getApiBaseUrl(): string {
  const baseUrl = process.env.EXPO_PUBLIC_API_URL;

  if (!baseUrl) {
    throw new DocumentServiceError("Missing EXPO_PUBLIC_API_URL configuration.", {
      code: "CONFIG_ERROR",
    });
  }

  return baseUrl.replace(/\/+$/, "");
}

function getErrorMessage(payload: UploadErrorPayload | null, fallback: string): string {
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
    const firstMessage = payload.detail.find((item) => typeof item.msg === "string")?.msg;

    if (firstMessage) {
      return firstMessage;
    }
  }

  return fallback;
}

export async function uploadDocumentImage(
  payload: UploadDocumentPayload,
): Promise<UploadDocumentResponse> {
  const { accessToken } = await getTokens();

  if (!accessToken) {
    throw new DocumentServiceError("You need to sign in before uploading documents.", {
      code: "UNAUTHORIZED_ERROR",
      status: 401,
    });
  }

  const formData = new FormData();
  formData.append("file", {
    name: payload.name ?? "aadhaar-capture.jpg",
    type: payload.type ?? "image/jpeg",
    uri: payload.uri,
  } as never);

  let response: Response;

  try {
    response = await fetch(`${getApiBaseUrl()}/documents/upload`, {
      body: formData,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      method: "POST",
    });
  } catch {
    throw new DocumentServiceError("Unable to upload the document right now.", {
      code: "NETWORK_ERROR",
    });
  }

  const rawBody = await response.text();
  const parsedBody = rawBody.length > 0 ? (JSON.parse(rawBody) as unknown) : null;

  if (!response.ok) {
    const errorPayload =
      parsedBody && typeof parsedBody === "object" ? (parsedBody as UploadErrorPayload) : null;

    throw new DocumentServiceError(
      getErrorMessage(errorPayload, "Upload failed. Please try again."),
      {
        code: response.status === 401 ? "UNAUTHORIZED_ERROR" : "HTTP_ERROR",
        status: response.status,
      },
    );
  }

  return parsedBody as UploadDocumentResponse;
}

