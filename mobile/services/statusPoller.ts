import { getTokens } from "../lib/storage/tokenStorage";

export const PROCESSING_STEPS = [
  "uploaded",
  "preprocessing",
  "field_detection",
  "ocr",
  "pii_masking",
  "fraud_check",
  "completed",
] as const;

export type ProcessingStep = (typeof PROCESSING_STEPS)[number];
export type ProcessingStatus = "processing" | "completed" | "failed";

export type DocumentStatusResponse = {
  current_step: ProcessingStep;
  status: ProcessingStatus;
};

type StatusErrorPayload = {
  detail?: string | Array<{ msg?: string }>;
  message?: string;
};

type PollingCallbacks = {
  documentId: string;
  intervalMs?: number;
  onFailed?: (response: DocumentStatusResponse) => void;
  onStatusChange: (response: DocumentStatusResponse) => void;
  onTimeout?: () => void;
  onError?: (error: StatusPollerError) => void;
  onCompleted?: (response: DocumentStatusResponse) => void;
  timeoutMs?: number;
};

export class StatusPollerError extends Error {
  status: number | null;

  code:
    | "CONFIG_ERROR"
    | "HTTP_ERROR"
    | "NETWORK_ERROR"
    | "TIMEOUT_ERROR"
    | "UNAUTHORIZED_ERROR";

  constructor(
    message: string,
    options: {
      code:
        | "CONFIG_ERROR"
        | "HTTP_ERROR"
        | "NETWORK_ERROR"
        | "TIMEOUT_ERROR"
        | "UNAUTHORIZED_ERROR";
      status?: number | null;
    },
  ) {
    super(message);
    this.name = "StatusPollerError";
    this.code = options.code;
    this.status = options.status ?? null;
  }
}

function getApiBaseUrl(): string {
  const baseUrl = process.env.EXPO_PUBLIC_API_URL;

  if (!baseUrl) {
    throw new StatusPollerError("Missing EXPO_PUBLIC_API_URL configuration.", {
      code: "CONFIG_ERROR",
    });
  }

  return baseUrl.replace(/\/+$/, "");
}

function parseErrorMessage(payload: StatusErrorPayload | null, fallback: string): string {
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

export async function fetchDocumentStatus(
  documentId: string,
  signal?: AbortSignal,
): Promise<DocumentStatusResponse> {
  const { accessToken } = await getTokens();

  if (!accessToken) {
    throw new StatusPollerError("You need to sign in before checking document status.", {
      code: "UNAUTHORIZED_ERROR",
      status: 401,
    });
  }

  let response: Response;

  try {
    response = await fetch(`${getApiBaseUrl()}/documents/${documentId}/status`, {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      method: "GET",
      signal,
    });
  } catch {
    throw new StatusPollerError("Unable to refresh processing status right now.", {
      code: "NETWORK_ERROR",
    });
  }

  const rawBody = await response.text();
  const parsedBody = rawBody.length > 0 ? (JSON.parse(rawBody) as unknown) : null;

  if (!response.ok) {
    const errorPayload =
      parsedBody && typeof parsedBody === "object" ? (parsedBody as StatusErrorPayload) : null;

    throw new StatusPollerError(
      parseErrorMessage(errorPayload, "Failed to fetch processing status."),
      {
        code: response.status === 401 ? "UNAUTHORIZED_ERROR" : "HTTP_ERROR",
        status: response.status,
      },
    );
  }

  return parsedBody as DocumentStatusResponse;
}

export function startStatusPolling({
  documentId,
  intervalMs = 1500,
  onCompleted,
  onError,
  onFailed,
  onStatusChange,
  onTimeout,
  timeoutMs = 90_000,
}: PollingCallbacks): () => void {
  let timeoutHandle: ReturnType<typeof setTimeout> | null = null;
  let cancelled = false;
  let activeController: AbortController | null = null;

  const stop = () => {
    cancelled = true;

    if (timeoutHandle) {
      clearTimeout(timeoutHandle);
      timeoutHandle = null;
    }

    activeController?.abort();
    activeController = null;
  };

  const scheduleNext = () => {
    if (cancelled) {
      return;
    }

    timeoutHandle = setTimeout(() => {
      void tick();
    }, intervalMs);
  };

  const tick = async () => {
    if (cancelled) {
      return;
    }

    activeController = new AbortController();

    try {
      const response = await fetchDocumentStatus(documentId, activeController.signal);

      if (cancelled) {
        return;
      }

      onStatusChange(response);

      if (response.status === "completed") {
        stop();
        onCompleted?.(response);
        return;
      }

      if (response.status === "failed") {
        stop();
        onFailed?.(response);
        return;
      }

      scheduleNext();
    } catch (error) {
      if (cancelled || (error instanceof Error && error.name === "AbortError")) {
        return;
      }

      stop();
      onError?.(
        error instanceof StatusPollerError
          ? error
          : new StatusPollerError("Failed to fetch processing status.", {
              code: "HTTP_ERROR",
            }),
      );
    }
  };

  void tick();

  const timeoutId = setTimeout(() => {
    if (cancelled) {
      return;
    }

    stop();
    onTimeout?.();
    onError?.(
      new StatusPollerError("Processing timed out. Please try again.", {
        code: "TIMEOUT_ERROR",
      }),
    );
  }, timeoutMs);

  return () => {
    clearTimeout(timeoutId);
    stop();
  };
}
