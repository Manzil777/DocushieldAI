import { getTokens } from "../storage/tokenStorage";

type UploadDocumentPayload = {
  name?: string;
  type?: string;
  uri: string;
};

type ApiErrorPayload = {
  detail?: string | Array<{ msg?: string }>;
  message?: string;
};

export const DOCUMENT_FIELD_TYPES = ["uid", "dob", "name", "gender", "address"] as const;

export type DocumentFieldType = (typeof DOCUMENT_FIELD_TYPES)[number];

export type NormalizedBoundingBox = {
  height: number;
  width: number;
  x: number;
  y: number;
};

export type DetectedDocumentField = {
  bbox: NormalizedBoundingBox;
  type: DocumentFieldType;
};

export type MaskConfig = Partial<Record<DocumentFieldType, boolean>>;

type MaskDocumentPayload = {
  documentId: string;
  fields: DocumentFieldType[];
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

export type MaskDocumentResponse = {
  masked_document_id: string;
  preview_url: string;
};

export type ShareDocumentResponse = {
  document_id: string;
  expires_at: string;
  share_token: string;
  share_url: string;
};

type RegenerateShareResponse = Partial<ShareDocumentResponse> & {
  expires_at: string;
  share_token: string;
};

type MaskedPdfResponse = {
  pdf_url?: string;
  share_token?: string;
  url?: string;
};

type CursorPaginatedVaultPayload = {
  items?: unknown[];
  next_cursor?: string | null;
};

type RawVaultItem = {
  created_at?: string;
  document_type?: string;
  filename?: string;
  id?: string;
  thumbnail_url?: string | null;
};

type RawDocumentDetail = {
  created_at?: string;
  extracted_fields?: Record<string, unknown> | null;
  fields?: Record<string, unknown> | null;
  id?: string;
  is_masked?: boolean;
  masked?: boolean;
  parent_document_id?: string | null;
};

type RawShareActivity = {
  expires_at?: string;
  share_token?: string;
  token?: string;
  view_count?: number;
  views?: number;
};

type CreateShareResponse = Partial<ShareDocumentResponse> & {
  share_token?: string;
  token?: string;
  expires_at?: string;
};

export type VaultItem = {
  created_at: string;
  document_type: string;
  id: string;
  thumbnail_url?: string;
};

export type VaultListResponse = {
  items: VaultItem[];
  next_cursor?: string;
};

export type DocumentDetailResponse = {
  created_at: string;
  extracted_fields: Record<string, string>;
  id: string;
  is_masked: boolean;
};

export type ShareActivityEntry = {
  expires_at: string;
  share_token: string;
  view_count?: number;
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

function getShareBaseUrl(): string {
  const shareBaseUrl = process.env.EXPO_PUBLIC_SHARE_BASE_URL;

  if (shareBaseUrl && shareBaseUrl.trim().length > 0) {
    return shareBaseUrl.replace(/\/+$/, "");
  }

  return getApiBaseUrl();
}

function buildShareUrl(shareToken: string, shareUrl?: string): string {
  if (shareUrl && shareUrl.trim().length > 0) {
    return shareUrl;
  }

  return `${getShareBaseUrl()}/share/${encodeURIComponent(shareToken)}`;
}

function normalizeObjectRecord(value: Record<string, unknown> | null | undefined): Record<string, string> {
  if (!value) {
    return {};
  }

  return Object.entries(value).reduce<Record<string, string>>((accumulator, [key, rawValue]) => {
    if (typeof rawValue === "string") {
      accumulator[key] = rawValue;
      return accumulator;
    }

    if (typeof rawValue === "number" || typeof rawValue === "boolean") {
      accumulator[key] = String(rawValue);
      return accumulator;
    }

    if (rawValue == null) {
      accumulator[key] = "";
      return accumulator;
    }

    accumulator[key] = JSON.stringify(rawValue);
    return accumulator;
  }, {});
}

function normalizeVaultItem(payload: RawVaultItem): VaultItem | null {
  if (typeof payload.id !== "string" || payload.id.trim().length === 0) {
    return null;
  }

  const documentType =
    typeof payload.document_type === "string" && payload.document_type.trim().length > 0
      ? payload.document_type
      : typeof payload.filename === "string" && payload.filename.trim().length > 0
        ? payload.filename
        : "Document";

  return {
    created_at:
      typeof payload.created_at === "string" && payload.created_at.trim().length > 0
        ? payload.created_at
        : new Date(0).toISOString(),
    document_type: documentType,
    id: payload.id,
    thumbnail_url:
      typeof payload.thumbnail_url === "string" && payload.thumbnail_url.trim().length > 0
        ? payload.thumbnail_url
        : undefined,
  };
}

function normalizeVaultListResponse(payload: unknown): VaultListResponse {
  if (Array.isArray(payload)) {
    return {
      items: payload
        .map((item) => (item && typeof item === "object" ? normalizeVaultItem(item as RawVaultItem) : null))
        .filter((item): item is VaultItem => Boolean(item)),
    };
  }

  if (!payload || typeof payload !== "object") {
    throw new DocumentServiceError("Vault response is malformed.", {
      code: "HTTP_ERROR",
      status: 500,
    });
  }

  const typedPayload = payload as CursorPaginatedVaultPayload;
  const rawItems = Array.isArray(typedPayload.items) ? typedPayload.items : [];

  return {
    items: rawItems
      .map((item) => (item && typeof item === "object" ? normalizeVaultItem(item as RawVaultItem) : null))
      .filter((item): item is VaultItem => Boolean(item)),
    next_cursor:
      typeof typedPayload.next_cursor === "string" && typedPayload.next_cursor.trim().length > 0
        ? typedPayload.next_cursor
        : undefined,
  };
}

function normalizeDocumentDetailResponse(payload: unknown, fallbackDocumentId: string): DocumentDetailResponse {
  if (!payload || typeof payload !== "object") {
    throw new DocumentServiceError("Document detail response is malformed.", {
      code: "HTTP_ERROR",
      status: 500,
    });
  }

  const typedPayload = payload as RawDocumentDetail;
  const extractedFieldsSource =
    typedPayload.extracted_fields && typeof typedPayload.extracted_fields === "object"
      ? typedPayload.extracted_fields
      : typedPayload.fields && typeof typedPayload.fields === "object"
        ? typedPayload.fields
        : {};

  return {
    created_at:
      typeof typedPayload.created_at === "string" && typedPayload.created_at.trim().length > 0
        ? typedPayload.created_at
        : new Date(0).toISOString(),
    extracted_fields: normalizeObjectRecord(extractedFieldsSource),
    id:
      typeof typedPayload.id === "string" && typedPayload.id.trim().length > 0
        ? typedPayload.id
        : fallbackDocumentId,
    is_masked:
      typeof typedPayload.is_masked === "boolean"
        ? typedPayload.is_masked
        : typeof typedPayload.masked === "boolean"
          ? typedPayload.masked
          : Boolean(typedPayload.parent_document_id),
  };
}

function normalizeShareActivityEntry(payload: RawShareActivity): ShareActivityEntry | null {
  const shareToken =
    typeof payload.share_token === "string" && payload.share_token.trim().length > 0
      ? payload.share_token
      : typeof payload.token === "string" && payload.token.trim().length > 0
        ? payload.token
        : null;

  if (!shareToken || typeof payload.expires_at !== "string" || payload.expires_at.trim().length === 0) {
    return null;
  }

  const viewCount =
    typeof payload.view_count === "number"
      ? payload.view_count
      : typeof payload.views === "number"
        ? payload.views
        : undefined;

  return {
    expires_at: payload.expires_at,
    share_token: shareToken,
    view_count: viewCount,
  };
}

function normalizeShareActivityResponse(payload: unknown): ShareActivityEntry[] {
  if (!Array.isArray(payload)) {
    throw new DocumentServiceError("Share activity response is malformed.", {
      code: "HTTP_ERROR",
      status: 500,
    });
  }

  return payload
    .map((item) =>
      item && typeof item === "object" ? normalizeShareActivityEntry(item as RawShareActivity) : null,
    )
    .filter((item): item is ShareActivityEntry => Boolean(item));
}

async function authorizedJsonRequest<TResponse>(
  path: string,
  init: RequestInit,
  fallbackMessage: string,
): Promise<TResponse> {
  const { accessToken } = await getTokens();

  if (!accessToken) {
    throw new DocumentServiceError("You need to sign in before accessing shared documents.", {
      code: "UNAUTHORIZED_ERROR",
      status: 401,
    });
  }

  let response: Response;

  try {
    response = await fetch(`${getApiBaseUrl()}${path}`, {
      ...init,
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
        ...(init.body ? { "Content-Type": "application/json" } : {}),
        ...(init.headers ?? {}),
      },
    });
  } catch {
    throw new DocumentServiceError("Unable to reach the document service right now.", {
      code: "NETWORK_ERROR",
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
    const errorPayload =
      parsedBody && typeof parsedBody === "object" ? (parsedBody as ApiErrorPayload) : null;

    throw new DocumentServiceError(getErrorMessage(errorPayload, fallbackMessage), {
      code: response.status === 401 ? "UNAUTHORIZED_ERROR" : "HTTP_ERROR",
      status: response.status,
    });
  }

  return parsedBody as TResponse;
}

function normalizeShareDocumentResponse(
  payload: Partial<ShareDocumentResponse>,
  fallbackShareToken: string,
  fallbackDocumentId?: string,
): ShareDocumentResponse {
  const shareToken =
    typeof payload.share_token === "string" && payload.share_token.trim().length > 0
      ? payload.share_token
      : fallbackShareToken;

  if (typeof payload.expires_at !== "string" || payload.expires_at.trim().length === 0) {
    throw new DocumentServiceError("Share link is missing an expiration timestamp.", {
      code: "HTTP_ERROR",
      status: 500,
    });
  }

  const documentId =
    typeof payload.document_id === "string" && payload.document_id.trim().length > 0
      ? payload.document_id
      : fallbackDocumentId;

  if (!documentId) {
    throw new DocumentServiceError("Share link is missing a document reference.", {
      code: "HTTP_ERROR",
      status: 500,
    });
  }

  return {
    document_id: documentId,
    expires_at: payload.expires_at,
    share_token: shareToken,
    share_url: buildShareUrl(shareToken, payload.share_url),
  };
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

export async function maskDocument(
  payload: MaskDocumentPayload,
): Promise<MaskDocumentResponse> {
  const { accessToken } = await getTokens();

  if (!accessToken) {
    throw new DocumentServiceError("You need to sign in before masking documents.", {
      code: "UNAUTHORIZED_ERROR",
      status: 401,
    });
  }

  let response: Response;

  try {
    response = await fetch(`${getApiBaseUrl()}/documents/${payload.documentId}/mask`, {
      body: JSON.stringify({
        fields: payload.fields,
        mask_fields: payload.fields,
      }),
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
        "Content-Type": "application/json",
      },
      method: "POST",
    });
  } catch {
    throw new DocumentServiceError("Unable to apply masking right now.", {
      code: "NETWORK_ERROR",
    });
  }

  const rawBody = await response.text();
  const parsedBody = rawBody.length > 0 ? (JSON.parse(rawBody) as unknown) : null;

  if (!response.ok) {
    const errorPayload =
      parsedBody && typeof parsedBody === "object" ? (parsedBody as UploadErrorPayload) : null;

    throw new DocumentServiceError(
      getErrorMessage(errorPayload, "Masking failed. Please try again."),
      {
        code: response.status === 401 ? "UNAUTHORIZED_ERROR" : "HTTP_ERROR",
        status: response.status,
      },
    );
  }

  return parsedBody as MaskDocumentResponse;
}

export async function fetchShareDocument(
  shareToken: string,
): Promise<ShareDocumentResponse> {
  const normalizedToken = shareToken.trim();
  const candidatePaths = [
    `/documents/share/${encodeURIComponent(normalizedToken)}`,
    `/documents/shares/${encodeURIComponent(normalizedToken)}`,
    `/shares/${encodeURIComponent(normalizedToken)}`,
    `/share/${encodeURIComponent(normalizedToken)}/metadata`,
  ];

  let lastNotFoundError: DocumentServiceError | null = null;

  for (const path of candidatePaths) {
    try {
      const payload = await authorizedJsonRequest<Partial<ShareDocumentResponse>>(
        path,
        { method: "GET" },
        "Unable to load this share link.",
      );

      return normalizeShareDocumentResponse(payload, normalizedToken);
    } catch (error: unknown) {
      if (error instanceof DocumentServiceError && error.status === 404) {
        lastNotFoundError = error;
        continue;
      }

      throw error;
    }
  }

  throw (
    lastNotFoundError ??
    new DocumentServiceError("Share link not found.", {
      code: "HTTP_ERROR",
      status: 404,
    })
  );
}

export async function getMaskedPdfUrl(documentId: string): Promise<string> {
  const payload = await authorizedJsonRequest<MaskedPdfResponse>(
    `/documents/${encodeURIComponent(documentId)}/masked-pdf`,
    { method: "GET" },
    "Unable to fetch the masked PDF.",
  );

  const pdfUrl =
    typeof payload.pdf_url === "string" && payload.pdf_url.trim().length > 0
      ? payload.pdf_url
      : typeof payload.url === "string" && payload.url.trim().length > 0
        ? payload.url
        : null;

  if (!pdfUrl) {
    throw new DocumentServiceError("Masked PDF URL is missing from the response.", {
      code: "HTTP_ERROR",
      status: 500,
    });
  }

  return pdfUrl;
}

export async function regenerateShareLink(
  documentId: string,
  currentShareToken: string,
): Promise<ShareDocumentResponse> {
  const payload = await authorizedJsonRequest<RegenerateShareResponse>(
    `/documents/${encodeURIComponent(documentId)}/regenerate-share`,
    { method: "POST" },
    "Unable to regenerate the share link.",
  );

  return normalizeShareDocumentResponse(payload, currentShareToken, documentId);
}

export async function fetchVaultItems(cursor?: string): Promise<VaultListResponse> {
  const normalizedCursor = cursor?.trim();
  const querySuffix = normalizedCursor
    ? `?cursor=${encodeURIComponent(normalizedCursor)}`
    : "";
  const candidatePaths = [
    `/documents/vault${querySuffix}`,
    `/documents${querySuffix ? `${querySuffix}&scope=vault` : "?scope=vault"}`,
    `/vault/${querySuffix}`,
  ];

  let lastNotFoundError: DocumentServiceError | null = null;

  for (const path of candidatePaths) {
    try {
      const payload = await authorizedJsonRequest<unknown>(
        path.replace(/\/\?/, "?"),
        { method: "GET" },
        "Unable to load your vault.",
      );

      return normalizeVaultListResponse(payload);
    } catch (error: unknown) {
      if (error instanceof DocumentServiceError && error.status === 404) {
        lastNotFoundError = error;
        continue;
      }

      throw error;
    }
  }

  throw (
    lastNotFoundError ??
    new DocumentServiceError("Vault list not found.", {
      code: "HTTP_ERROR",
      status: 404,
    })
  );
}

export async function fetchDocumentDetail(documentId: string): Promise<DocumentDetailResponse> {
  const normalizedDocumentId = documentId.trim();
  const candidatePaths = [
    `/documents/${encodeURIComponent(normalizedDocumentId)}`,
    `/documents/${encodeURIComponent(normalizedDocumentId)}/detail`,
    `/vault/documents/${encodeURIComponent(normalizedDocumentId)}`,
  ];

  let lastNotFoundError: DocumentServiceError | null = null;

  for (const path of candidatePaths) {
    try {
      const payload = await authorizedJsonRequest<unknown>(
        path,
        { method: "GET" },
        "Unable to load this document.",
      );

      return normalizeDocumentDetailResponse(payload, normalizedDocumentId);
    } catch (error: unknown) {
      if (error instanceof DocumentServiceError && error.status === 404) {
        lastNotFoundError = error;
        continue;
      }

      throw error;
    }
  }

  throw (
    lastNotFoundError ??
    new DocumentServiceError("Document not found.", {
      code: "HTTP_ERROR",
      status: 404,
    })
  );
}

export async function fetchDocumentShareActivity(documentId: string): Promise<ShareActivityEntry[]> {
  const normalizedDocumentId = documentId.trim();
  const candidatePaths = [
    `/documents/${encodeURIComponent(normalizedDocumentId)}/shares`,
    `/documents/${encodeURIComponent(normalizedDocumentId)}/share-activity`,
    `/documents/${encodeURIComponent(normalizedDocumentId)}/share-log`,
  ];

  let lastNotFoundError: DocumentServiceError | null = null;

  for (const path of candidatePaths) {
    try {
      const payload = await authorizedJsonRequest<unknown>(
        path,
        { method: "GET" },
        "Unable to load share activity.",
      );

      return normalizeShareActivityResponse(payload);
    } catch (error: unknown) {
      if (error instanceof DocumentServiceError && error.status === 404) {
        lastNotFoundError = error;
        continue;
      }

      throw error;
    }
  }

  if (lastNotFoundError) {
    return [];
  }

  return [];
}

export async function createDocumentShare(documentId: string): Promise<ShareDocumentResponse> {
  const normalizedDocumentId = documentId.trim();
  const candidatePaths = [
    `/documents/${encodeURIComponent(normalizedDocumentId)}/share`,
    `/documents/${encodeURIComponent(normalizedDocumentId)}/regenerate-share`,
  ];

  let lastNotFoundError: DocumentServiceError | null = null;

  for (const path of candidatePaths) {
    try {
      const payload = await authorizedJsonRequest<CreateShareResponse>(
        path,
        {
          body: JSON.stringify({}),
          method: "POST",
        },
        "Unable to create a share link.",
      );

      const nextShareToken =
        typeof payload.share_token === "string" && payload.share_token.trim().length > 0
          ? payload.share_token
          : typeof payload.token === "string" && payload.token.trim().length > 0
            ? payload.token
            : "";

      return normalizeShareDocumentResponse(
        {
          ...payload,
          document_id: payload.document_id ?? normalizedDocumentId,
          share_token: nextShareToken,
        },
        nextShareToken,
        normalizedDocumentId,
      );
    } catch (error: unknown) {
      if (error instanceof DocumentServiceError && error.status === 404) {
        lastNotFoundError = error;
        continue;
      }

      throw error;
    }
  }

  throw (
    lastNotFoundError ??
    new DocumentServiceError("Unable to create a share link.", {
      code: "HTTP_ERROR",
      status: 404,
    })
  );
}

export async function ensureDocumentShare(
  documentId: string,
  existingShares: ShareActivityEntry[],
): Promise<ShareDocumentResponse> {
  const activeShare = existingShares.find((entry) => Date.parse(entry.expires_at) > Date.now());

  if (activeShare) {
    return fetchShareDocument(activeShare.share_token);
  }

  return createDocumentShare(documentId);
}

export async function deleteDocument(documentId: string): Promise<void> {
  const normalizedDocumentId = documentId.trim();
  const candidatePaths = [
    `/documents/${encodeURIComponent(normalizedDocumentId)}`,
    `/vault/${encodeURIComponent(normalizedDocumentId)}`,
  ];

  let lastNotFoundError: DocumentServiceError | null = null;

  for (const path of candidatePaths) {
    try {
      await authorizedJsonRequest<unknown>(
        path,
        { method: "DELETE" },
        "Unable to delete this document.",
      );
      return;
    } catch (error: unknown) {
      if (error instanceof DocumentServiceError && error.status === 404) {
        lastNotFoundError = error;
        continue;
      }

      throw error;
    }
  }

  throw (
    lastNotFoundError ??
    new DocumentServiceError("Document not found.", {
      code: "HTTP_ERROR",
      status: 404,
    })
  );
}
