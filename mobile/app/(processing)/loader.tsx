import { type Href, router, useLocalSearchParams } from "expo-router";
import { useEffect, useMemo, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  ProcessingStepper,
  getProcessingStepLabel,
} from "../../components/ProcessingStepper";
import {
  startStatusPolling,
  StatusPollerError,
  type DocumentStatusResponse,
  type ProcessingStep,
} from "../../services/statusPoller";

const INITIAL_STEP: ProcessingStep = "uploaded";

function getSearchParam(value: string | string[] | undefined): string | null {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }

  if (Array.isArray(value) && typeof value[0] === "string" && value[0].trim().length > 0) {
    return value[0];
  }

  return null;
}

function getErrorMessage(error: StatusPollerError | null): string {
  if (!error) {
    return "Processing failed. Try again.";
  }

  if (error.code === "TIMEOUT_ERROR") {
    return "Processing took too long. Try again.";
  }

  return error.message || "Processing failed. Try again.";
}

export default function LoaderScreen() {
  const params = useLocalSearchParams<{ documentId?: string | string[]; id?: string | string[] }>();
  const documentId = useMemo(
    () => getSearchParam(params.documentId) ?? getSearchParam(params.id),
    [params.documentId, params.id],
  );

  const [currentStep, setCurrentStep] = useState<ProcessingStep>(INITIAL_STEP);
  const [error, setError] = useState<StatusPollerError | null>(null);
  const [isFailed, setIsFailed] = useState(false);
  const [retryKey, setRetryKey] = useState(0);

  useEffect(() => {
    if (!documentId) {
      setIsFailed(true);
      setError(
        new StatusPollerError("Missing document id for processing status.", {
          code: "HTTP_ERROR",
        }),
      );
      return;
    }

    setCurrentStep(INITIAL_STEP);
    setError(null);
    setIsFailed(false);

    return startStatusPolling({
      documentId,
      onCompleted: () => {
        router.replace(`/masking?id=${encodeURIComponent(documentId)}` as Href);
      },
      onError: (nextError) => {
        setError(nextError);
        setIsFailed(true);
      },
      onFailed: (response: DocumentStatusResponse) => {
        setCurrentStep(response.current_step);
        setError(
          new StatusPollerError("Processing failed. Try again.", {
            code: "HTTP_ERROR",
          }),
        );
        setIsFailed(true);
      },
      onStatusChange: (response: DocumentStatusResponse) => {
        setCurrentStep(response.current_step);
      },
      onTimeout: () => {
        setIsFailed(true);
      },
    });
  }, [documentId, retryKey]);

  const helperText = useMemo(() => {
    if (isFailed) {
      return getErrorMessage(error);
    }

    return `${getProcessingStepLabel(currentStep)} Please keep this screen open.`;
  }, [currentStep, error, isFailed]);

  return (
    <SafeAreaView className="flex-1 bg-slate-100">
      <View className="flex-1 items-center justify-center px-6">
        <View className="w-full max-w-md items-center">
          <View className="mb-8 h-16 w-16 items-center justify-center rounded-full bg-slate-950">
            {isFailed ? (
              <Text className="text-2xl font-bold text-white">!</Text>
            ) : (
              <ActivityIndicator color="#ffffff" />
            )}
          </View>

          <Text className="text-center text-3xl font-bold text-slate-950">
            {isFailed ? "Processing failed" : "Processing document"}
          </Text>
          <Text className="mt-3 max-w-sm text-center text-base leading-6 text-slate-600">
            {helperText}
          </Text>

          {!isFailed ? <ProcessingStepper currentStep={currentStep} /> : null}

          {isFailed ? (
            <View className="mt-8 w-full gap-3">
              <Pressable
                className="min-h-14 items-center justify-center rounded-2xl bg-slate-950"
                onPress={() => {
                  setRetryKey((value) => value + 1);
                }}
              >
                <Text className="text-base font-semibold text-white">Retry</Text>
              </Pressable>

              <Pressable
                className="min-h-14 items-center justify-center rounded-2xl border border-slate-300 bg-white"
                onPress={() => router.back()}
              >
                <Text className="text-base font-semibold text-slate-900">Go back</Text>
              </Pressable>
            </View>
          ) : (
            <Text className="mt-8 text-sm text-slate-500">
              Document ID: {documentId?.slice(0, 8)}...
            </Text>
          )}
        </View>
      </View>
    </SafeAreaView>
  );
}
