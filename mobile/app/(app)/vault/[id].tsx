import { type Href, router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  createDocumentShare,
  deleteDocument,
  DocumentServiceError,
  ensureDocumentShare,
  fetchDocumentDetail,
  fetchDocumentShareActivity,
  type DocumentDetailResponse,
  type ShareActivityEntry,
} from "../../../lib/services/documentService";

type DetailRouteParams = {
  id?: string | string[];
};

type DetailState = {
  detail: DocumentDetailResponse | null;
  errorMessage: string | null;
  isDeleting: boolean;
  isLoading: boolean;
  isPreparingShare: boolean;
  shareActivity: ShareActivityEntry[];
  shareLogError: string | null;
};

function getParamValue(value: string | string[] | undefined): string | null {
  if (typeof value === "string" && value.trim().length > 0) {
    return value;
  }

  if (Array.isArray(value) && typeof value[0] === "string" && value[0].trim().length > 0) {
    return value[0];
  }

  return null;
}

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof DocumentServiceError) {
    return error.message;
  }

  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return fallback;
}

function formatDate(value: string): string {
  const timestamp = Date.parse(value);

  if (Number.isNaN(timestamp)) {
    return "Unknown date";
  }

  return new Date(timestamp).toLocaleString();
}

function shortenToken(token: string): string {
  if (token.length <= 12) {
    return token;
  }

  return `${token.slice(0, 6)}...${token.slice(-4)}`;
}

function isShareExpired(expiresAt: string): boolean {
  const timestamp = Date.parse(expiresAt);

  if (Number.isNaN(timestamp)) {
    return true;
  }

  return timestamp <= Date.now();
}

export default function VaultDocumentDetailScreen() {
  const params = useLocalSearchParams<DetailRouteParams>();
  const documentId = getParamValue(params.id);
  const [state, setState] = useState<DetailState>({
    detail: null,
    errorMessage: null,
    isDeleting: false,
    isLoading: true,
    isPreparingShare: false,
    shareActivity: [],
    shareLogError: null,
  });

  useEffect(() => {
    let isMounted = true;

    async function loadDocument() {
      if (!documentId) {
        if (!isMounted) {
          return;
        }

        setState((current) => ({
          ...current,
          errorMessage: "Invalid document ID.",
          isLoading: false,
        }));
        return;
      }

      setState((current) => ({
        ...current,
        errorMessage: null,
        isLoading: true,
        shareLogError: null,
      }));

      try {
        const [detail, shareActivity] = await Promise.all([
          fetchDocumentDetail(documentId),
          fetchDocumentShareActivity(documentId),
        ]);

        if (!isMounted) {
          return;
        }

        setState((current) => ({
          ...current,
          detail,
          errorMessage: null,
          isLoading: false,
          shareActivity,
          shareLogError: null,
        }));
      } catch (error: unknown) {
        if (!isMounted) {
          return;
        }

        setState((current) => ({
          ...current,
          detail: null,
          errorMessage: getErrorMessage(error, "Unable to load this document."),
          isLoading: false,
        }));
      }
    }

    void loadDocument();

    return () => {
      isMounted = false;
    };
  }, [documentId]);

  async function handleShareDocument() {
    if (!documentId || state.isPreparingShare) {
      return;
    }

    setState((current) => ({
      ...current,
      isPreparingShare: true,
      shareLogError: null,
    }));

    try {
      const shareResponse =
        state.shareActivity.length > 0
          ? await ensureDocumentShare(documentId, state.shareActivity)
          : await createDocumentShare(documentId);

      setState((current) => ({
        ...current,
        isPreparingShare: false,
      }));

      router.push(`/share/${encodeURIComponent(shareResponse.share_token)}` as Href);
    } catch (error: unknown) {
      setState((current) => ({
        ...current,
        isPreparingShare: false,
        shareLogError: getErrorMessage(error, "Unable to prepare a share link."),
      }));
    }
  }

  function handleDeleteDocument() {
    if (!documentId || state.isDeleting) {
      return;
    }

    Alert.alert(
      "Delete document",
      "This will remove the document from your vault. This action cannot be undone.",
      [
        {
          style: "cancel",
          text: "Cancel",
        },
        {
          style: "destructive",
          text: "Delete",
          onPress: () => {
            setState((current) => ({
              ...current,
              isDeleting: true,
            }));

            void deleteDocument(documentId)
              .then(() => {
                router.replace("/vault" as Href);
              })
              .catch((error: unknown) => {
                setState((current) => ({
                  ...current,
                  errorMessage: getErrorMessage(error, "Unable to delete this document."),
                  isDeleting: false,
                }));
              });
          },
        },
      ],
      { cancelable: true },
    );
  }

  if (state.isLoading) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <View style={styles.centerState}>
          <ActivityIndicator color="#e2e8f0" size="large" />
          <Text style={styles.centerTitle}>Loading document</Text>
          <Text style={styles.centerCopy}>Fetching extracted fields and recent share activity.</Text>
        </View>
      </SafeAreaView>
    );
  }

  if (!state.detail || !documentId) {
    return (
      <SafeAreaView style={styles.safeArea}>
        <View style={styles.centerState}>
          <Text style={styles.errorTitle}>Document unavailable</Text>
          <Text style={styles.errorCopy}>{state.errorMessage ?? "This document could not be loaded."}</Text>
          <Pressable onPress={() => router.replace("/vault" as Href)} style={styles.primaryButton}>
            <Text style={styles.primaryButtonText}>Back to vault</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  const fieldEntries = Object.entries(state.detail.extracted_fields);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.headerButton}>
          <Text style={styles.headerButtonText}>Back</Text>
        </Pressable>

        <Text style={styles.headerTitle}>Document detail</Text>

        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        bounces={false}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.heroCard}>
          <View style={styles.statusRow}>
            <View style={[styles.statusPill, state.detail.is_masked ? styles.maskedPill : styles.unmaskedPill]}>
              <Text style={[styles.statusPillText, state.detail.is_masked ? styles.maskedPillText : styles.unmaskedPillText]}>
                {state.detail.is_masked ? "Masked" : "Unmasked"}
              </Text>
            </View>

            <Text style={styles.createdAtText}>{formatDate(state.detail.created_at)}</Text>
          </View>

          <Text style={styles.documentIdLabel}>Document ID</Text>
          <Text selectable style={styles.documentIdValue}>
            {state.detail.id}
          </Text>
        </View>

        <View style={styles.sectionCard}>
          <Text style={styles.sectionTitle}>Extracted fields</Text>

          {fieldEntries.length > 0 ? (
            fieldEntries.map(([key, value]) => (
              <View key={key} style={styles.fieldRow}>
                <Text style={styles.fieldKey}>{key.replace(/_/g, " ")}</Text>
                <Text style={styles.fieldValue}>{value || "Not available"}</Text>
              </View>
            ))
          ) : (
            <Text style={styles.emptyCopy}>No extracted fields are available for this document.</Text>
          )}
        </View>

        <View style={styles.sectionCard}>
          <View style={styles.sectionHeaderRow}>
            <Text style={styles.sectionTitle}>Share activity</Text>
            <Text style={styles.sectionMeta}>{state.shareActivity.length} entries</Text>
          </View>

          {state.shareActivity.length > 0 ? (
            state.shareActivity.map((entry) => {
              const expired = isShareExpired(entry.expires_at);

              return (
                <Pressable
                  key={entry.share_token}
                  onPress={() => router.push(`/share/${encodeURIComponent(entry.share_token)}` as Href)}
                  style={styles.shareRow}
                >
                  <View style={styles.shareRowHeader}>
                    <Text style={styles.shareToken}>{shortenToken(entry.share_token)}</Text>
                    <View style={[styles.shareStatusPill, expired ? styles.expiredPill : styles.activePill]}>
                      <Text style={[styles.shareStatusText, expired ? styles.expiredText : styles.activeText]}>
                        {expired ? "Expired" : "Active"}
                      </Text>
                    </View>
                  </View>

                  <Text style={styles.shareMeta}>Expires {formatDate(entry.expires_at)}</Text>
                  {typeof entry.view_count === "number" ? (
                    <Text style={styles.shareMeta}>Views: {entry.view_count}</Text>
                  ) : null}
                </Pressable>
              );
            })
          ) : (
            <Text style={styles.emptyCopy}>No share activity yet for this document.</Text>
          )}

          {state.shareLogError ? <Text style={styles.inlineErrorText}>{state.shareLogError}</Text> : null}
        </View>

        {state.errorMessage ? (
          <View style={styles.inlineErrorCard}>
            <Text style={styles.inlineErrorText}>{state.errorMessage}</Text>
          </View>
        ) : null}

        <Pressable
          disabled={state.isPreparingShare}
          onPress={() => {
            void handleShareDocument();
          }}
          style={[styles.primaryButton, state.isPreparingShare ? styles.buttonDisabled : null]}
        >
          <Text style={styles.primaryButtonText}>
            {state.isPreparingShare ? "Preparing share link..." : "Share Document"}
          </Text>
        </Pressable>

        <Pressable
          disabled={state.isDeleting}
          onPress={handleDeleteDocument}
          style={[styles.deleteButton, state.isDeleting ? styles.buttonDisabled : null]}
        >
          <Text style={styles.deleteButtonText}>
            {state.isDeleting ? "Deleting..." : "Delete Document"}
          </Text>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  activePill: {
    backgroundColor: "#1d3a2d",
  },
  activeText: {
    color: "#bbf7d0",
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  centerCopy: {
    color: "#94a3b8",
    fontSize: 15,
    lineHeight: 22,
    marginTop: 10,
    textAlign: "center",
  },
  centerState: {
    alignItems: "center",
    flex: 1,
    justifyContent: "center",
    paddingHorizontal: 24,
  },
  centerTitle: {
    color: "#f8fafc",
    fontSize: 22,
    fontWeight: "700",
    marginTop: 16,
  },
  createdAtText: {
    color: "#94a3b8",
    fontSize: 13,
  },
  deleteButton: {
    alignItems: "center",
    borderColor: "#7f1d1d",
    borderRadius: 22,
    borderWidth: 1,
    justifyContent: "center",
    marginTop: 12,
    minHeight: 56,
    paddingHorizontal: 18,
  },
  deleteButtonText: {
    color: "#fecaca",
    fontSize: 16,
    fontWeight: "800",
  },
  documentIdLabel: {
    color: "#94a3b8",
    fontSize: 12,
    fontWeight: "700",
    letterSpacing: 0.8,
    marginTop: 18,
    textTransform: "uppercase",
  },
  documentIdValue: {
    color: "#f8fafc",
    fontSize: 16,
    lineHeight: 23,
    marginTop: 8,
  },
  emptyCopy: {
    color: "#94a3b8",
    fontSize: 15,
    lineHeight: 22,
    marginTop: 10,
  },
  errorCopy: {
    color: "#cbd5e1",
    fontSize: 15,
    lineHeight: 22,
    marginTop: 12,
    textAlign: "center",
  },
  errorTitle: {
    color: "#f8fafc",
    fontSize: 24,
    fontWeight: "700",
    textAlign: "center",
  },
  expiredPill: {
    backgroundColor: "#482125",
  },
  expiredText: {
    color: "#fecdd3",
  },
  fieldKey: {
    color: "#94a3b8",
    fontSize: 13,
    fontWeight: "700",
    textTransform: "capitalize",
  },
  fieldRow: {
    borderTopColor: "#1e293b",
    borderTopWidth: 1,
    paddingVertical: 14,
  },
  fieldValue: {
    color: "#f8fafc",
    fontSize: 15,
    lineHeight: 22,
    marginTop: 8,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 8,
  },
  headerButton: {
    borderColor: "#334155",
    borderRadius: 999,
    borderWidth: 1,
    minWidth: 72,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  headerButtonText: {
    color: "#e2e8f0",
    fontSize: 14,
    fontWeight: "600",
    textAlign: "center",
  },
  headerSpacer: {
    minWidth: 72,
  },
  headerTitle: {
    color: "#f8fafc",
    fontSize: 20,
    fontWeight: "800",
  },
  heroCard: {
    backgroundColor: "#0f172a",
    borderColor: "#1e293b",
    borderRadius: 28,
    borderWidth: 1,
    paddingHorizontal: 18,
    paddingVertical: 18,
  },
  inlineErrorCard: {
    backgroundColor: "#3f1d24",
    borderColor: "#7f1d1d",
    borderRadius: 18,
    borderWidth: 1,
    marginTop: 16,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  inlineErrorText: {
    color: "#fecdd3",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 10,
  },
  maskedPill: {
    backgroundColor: "#122c3e",
  },
  maskedPillText: {
    color: "#bae6fd",
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#f8fafc",
    borderRadius: 22,
    justifyContent: "center",
    marginTop: 18,
    minHeight: 56,
    paddingHorizontal: 18,
  },
  primaryButtonText: {
    color: "#020617",
    fontSize: 16,
    fontWeight: "800",
  },
  safeArea: {
    backgroundColor: "#020617",
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 32,
    paddingHorizontal: 20,
    paddingTop: 20,
  },
  sectionCard: {
    backgroundColor: "#0f172a",
    borderColor: "#1e293b",
    borderRadius: 24,
    borderWidth: 1,
    marginTop: 16,
    paddingHorizontal: 18,
    paddingVertical: 16,
  },
  sectionHeaderRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  sectionMeta: {
    color: "#94a3b8",
    fontSize: 13,
  },
  sectionTitle: {
    color: "#f8fafc",
    fontSize: 20,
    fontWeight: "700",
  },
  shareMeta: {
    color: "#94a3b8",
    fontSize: 13,
    marginTop: 6,
  },
  shareRow: {
    backgroundColor: "#111c2f",
    borderColor: "#25324a",
    borderRadius: 18,
    borderWidth: 1,
    marginTop: 14,
    paddingHorizontal: 14,
    paddingVertical: 14,
  },
  shareRowHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  shareStatusPill: {
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  shareStatusText: {
    fontSize: 12,
    fontWeight: "700",
  },
  shareToken: {
    color: "#f8fafc",
    fontSize: 15,
    fontWeight: "700",
  },
  statusPill: {
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  statusPillText: {
    fontSize: 12,
    fontWeight: "700",
  },
  statusRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  unmaskedPill: {
    backgroundColor: "#3f2f12",
  },
  unmaskedPillText: {
    color: "#fde68a",
  },
});
