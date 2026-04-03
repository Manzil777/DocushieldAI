import * as Clipboard from "expo-clipboard";
import * as Linking from "expo-linking";
import * as Sharing from "expo-sharing";
import { type Href, router, useLocalSearchParams } from "expo-router";
import { useEffect, useState } from "react";
import QRCode from "react-native-qrcode-svg";
import {
  ActivityIndicator,
  Alert,
  Modal,
  Pressable,
  ScrollView,
  Share,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  DocumentServiceError,
  fetchShareDocument,
  getMaskedPdfUrl,
  regenerateShareLink,
  type ShareDocumentResponse,
} from "../../../lib/services/documentService";

type ShareRouteParams = {
  id?: string | string[];
};

type ShareControllerState = {
  copyFeedback: string | null;
  errorMessage: string | null;
  isDownloadingPdf: boolean;
  isLoading: boolean;
  isQrModalVisible: boolean;
  isRegenerating: boolean;
  isSharing: boolean;
  remainingSeconds: number;
  shareData: ShareDocumentResponse | null;
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

function getShareErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof DocumentServiceError) {
    return error.message;
  }

  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return fallback;
}

function formatRemainingTime(totalSeconds: number): string {
  const safeSeconds = Math.max(0, totalSeconds);
  const hours = Math.floor(safeSeconds / 3600);
  const minutes = Math.floor((safeSeconds % 3600) / 60);
  const seconds = safeSeconds % 60;

  if (hours > 0) {
    return [hours, minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
  }

  return [minutes, seconds].map((value) => String(value).padStart(2, "0")).join(":");
}

function useShareController(shareToken: string | null) {
  const [state, setState] = useState<ShareControllerState>({
    copyFeedback: null,
    errorMessage: null,
    isDownloadingPdf: false,
    isLoading: true,
    isQrModalVisible: false,
    isRegenerating: false,
    isSharing: false,
    remainingSeconds: 0,
    shareData: null,
  });

  useEffect(() => {
    let isMounted = true;

    async function loadShareData() {
      if (!shareToken) {
        if (!isMounted) {
          return;
        }

        setState((current) => ({
          ...current,
          errorMessage: "Invalid share link.",
          isLoading: false,
          shareData: null,
        }));
        return;
      }

        setState((current) => ({
          ...current,
          copyFeedback: null,
          errorMessage: null,
          isLoading: true,
          isQrModalVisible: false,
        }));

      try {
        const nextShareData = await fetchShareDocument(shareToken);

        if (!isMounted) {
          return;
        }

        setState((current) => ({
          ...current,
          copyFeedback: null,
          errorMessage: null,
          isLoading: false,
          shareData: nextShareData,
        }));
      } catch (error: unknown) {
        if (!isMounted) {
          return;
        }

        setState((current) => ({
          ...current,
          errorMessage: getShareErrorMessage(error, "Unable to load this share link."),
          isLoading: false,
          shareData: null,
        }));
      }
    }

    void loadShareData();

    return () => {
      isMounted = false;
    };
  }, [shareToken]);

  useEffect(() => {
    const intervalId = setInterval(() => {
      setState((current) => {
        if (!current.shareData) {
          return current.remainingSeconds === 0
            ? current
            : {
                ...current,
                remainingSeconds: 0,
              };
        }

        const expiresAtMs = Date.parse(current.shareData.expires_at);
        const nextRemainingSeconds = Number.isNaN(expiresAtMs)
          ? 0
          : Math.max(0, Math.floor((expiresAtMs - Date.now()) / 1000));

        return current.remainingSeconds === nextRemainingSeconds
          ? current
          : {
              ...current,
              remainingSeconds: nextRemainingSeconds,
            };
      });
    }, 1000);

    return () => {
      clearInterval(intervalId);
    };
  }, []);

  useEffect(() => {
    if (!state.copyFeedback) {
      return;
    }

    const timeoutId = setTimeout(() => {
      setState((current) =>
        current.copyFeedback
          ? {
              ...current,
              copyFeedback: null,
            }
          : current,
      );
    }, 1800);

    return () => {
      clearTimeout(timeoutId);
    };
  }, [state.copyFeedback]);

  useEffect(() => {
    const expiresAtMs = state.shareData ? Date.parse(state.shareData.expires_at) : NaN;
    const nextRemainingSeconds = Number.isNaN(expiresAtMs)
      ? 0
      : Math.max(0, Math.floor((expiresAtMs - Date.now()) / 1000));

    setState((current) =>
      current.remainingSeconds === nextRemainingSeconds
        ? current
        : {
            ...current,
            remainingSeconds: nextRemainingSeconds,
          },
    );
  }, [state.shareData]);

  async function handleCopy() {
    if (!state.shareData || state.remainingSeconds <= 0) {
      return;
    }

    try {
      await Clipboard.setStringAsync(state.shareData.share_url);
      setState((current) => ({
        ...current,
        copyFeedback: "Copied!",
      }));
    } catch {
      Alert.alert("Copy failed", "Unable to copy the share link right now.");
    }
  }

  async function handleDownloadPdf() {
    if (!state.shareData || state.remainingSeconds <= 0 || state.isDownloadingPdf) {
      return;
    }

    setState((current) => ({
      ...current,
      errorMessage: null,
      isDownloadingPdf: true,
    }));

    try {
      const pdfUrl = await getMaskedPdfUrl(state.shareData.document_id);
      const sharingAvailable = await Sharing.isAvailableAsync();

      if (sharingAvailable && pdfUrl.startsWith("file://")) {
        await Sharing.shareAsync(pdfUrl);
      } else {
        const canOpen = await Linking.canOpenURL(pdfUrl);

        if (!canOpen) {
          throw new Error("The PDF URL cannot be opened on this device.");
        }

        await Linking.openURL(pdfUrl);
      }
    } catch (error: unknown) {
      Alert.alert("PDF unavailable", getShareErrorMessage(error, "Unable to open the masked PDF."));
    } finally {
      setState((current) => ({
        ...current,
        isDownloadingPdf: false,
      }));
    }
  }

  async function handleNativeShare() {
    if (!state.shareData || state.remainingSeconds <= 0 || state.isSharing) {
      return;
    }

    setState((current) => ({
      ...current,
      isSharing: true,
    }));

    try {
      await Share.share({
        message: state.shareData.share_url,
        title: "DocuShield AI secure share link",
        url: state.shareData.share_url,
      });
    } catch (error: unknown) {
      Alert.alert("Share failed", getShareErrorMessage(error, "Unable to open the share sheet."));
    } finally {
      setState((current) => ({
        ...current,
        isSharing: false,
      }));
    }
  }

  async function handleRegenerate() {
    if (!state.shareData || state.isRegenerating) {
      return;
    }

    setState((current) => ({
      ...current,
      errorMessage: null,
      isRegenerating: true,
    }));

    try {
      const nextShareData = await regenerateShareLink(
        state.shareData.document_id,
        state.shareData.share_token,
      );

      setState((current) => ({
        ...current,
        copyFeedback: null,
        isRegenerating: false,
        isQrModalVisible: false,
        shareData: nextShareData,
      }));

      if (nextShareData.share_token !== state.shareData.share_token) {
        router.replace(`/share/${encodeURIComponent(nextShareData.share_token)}` as Href);
      }
    } catch (error: unknown) {
      setState((current) => ({
        ...current,
        errorMessage: getShareErrorMessage(error, "Unable to regenerate the share link."),
        isRegenerating: false,
      }));
    }
  }

  function toggleQrModal(isVisible: boolean) {
    setState((current) => ({
      ...current,
      isQrModalVisible: isVisible,
    }));
  }

  return {
    ...state,
    handleCopy,
    handleDownloadPdf,
    handleNativeShare,
    handleRegenerate,
    reload: () => {
      if (!shareToken) {
        setState((current) => ({
          ...current,
          errorMessage: "Invalid share link.",
          isLoading: false,
          shareData: null,
        }));
        return;
      }

      setState((current) => ({
        ...current,
        copyFeedback: null,
        errorMessage: null,
        isLoading: true,
        isQrModalVisible: false,
      }));

      void fetchShareDocument(shareToken)
        .then((nextShareData) => {
          setState((current) => ({
            ...current,
            copyFeedback: null,
            errorMessage: null,
            isLoading: false,
            shareData: nextShareData,
          }));
        })
        .catch((error: unknown) => {
          setState((current) => ({
            ...current,
            errorMessage: getShareErrorMessage(error, "Unable to load this share link."),
            isLoading: false,
          }));
        });
    },
    setQrModalVisible: toggleQrModal,
  };
}

export default function ShareScreen() {
  const params = useLocalSearchParams<ShareRouteParams>();
  const shareToken = getParamValue(params.id);
  const {
    copyFeedback,
    errorMessage,
    handleCopy,
    handleDownloadPdf,
    handleNativeShare,
    handleRegenerate,
    isDownloadingPdf,
    isLoading,
    isQrModalVisible,
    isRegenerating,
    isSharing,
    reload,
    remainingSeconds,
    setQrModalVisible,
    shareData,
  } = useShareController(shareToken);

  const isExpired = Boolean(shareData) && remainingSeconds <= 0;
  const actionsDisabled = !shareData || isExpired;

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.headerButton}>
          <Text style={styles.headerButtonText}>Back</Text>
        </Pressable>

        <Text style={styles.headerTitle}>Share document</Text>

        <Pressable onPress={() => router.replace("/(app)")} style={styles.headerButton}>
          <Text style={styles.headerButtonText}>Home</Text>
        </Pressable>
      </View>

      <ScrollView
        bounces={false}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        {isLoading ? (
          <View style={styles.centerCard}>
            <ActivityIndicator color="#e2e8f0" size="large" />
            <Text style={styles.loadingTitle}>Preparing your share link</Text>
            <Text style={styles.loadingCopy}>Pulling the latest token, QR, and expiry window.</Text>
          </View>
        ) : null}

        {!isLoading && !shareData ? (
          <View style={styles.centerCard}>
            <Text style={styles.errorTitle}>Share link unavailable</Text>
            <Text style={styles.errorCopy}>{errorMessage ?? "This share link could not be loaded."}</Text>
            <Pressable onPress={reload} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Retry</Text>
            </Pressable>
          </View>
        ) : null}

        {!isLoading && shareData ? (
          <>
            <View style={styles.heroCard}>
              <View style={styles.statusRow}>
                <View style={styles.tokenPill}>
                  <Text style={styles.tokenPillText}>Token {shareData.share_token.slice(0, 8)}</Text>
                </View>

                <View style={[styles.expiryPill, isExpired ? styles.expiryPillExpired : null]}>
                  <Text style={[styles.expiryPillText, isExpired ? styles.expiryPillTextExpired : null]}>
                    {isExpired ? "Expired" : `Expires in ${formatRemainingTime(remainingSeconds)}`}
                  </Text>
                </View>
              </View>

              <Text style={styles.heroTitle}>Secure verification link</Text>
              <Text style={styles.heroCopy}>
                Send the QR or link below. The recipient can verify the masked document without
                seeing the original file.
              </Text>

              <Pressable
                disabled={!shareData.share_url}
                onPress={() => setQrModalVisible(true)}
                style={styles.qrCard}
              >
                <QRCode
                  backgroundColor="#ffffff"
                  color="#0f172a"
                  quietZone={14}
                  size={208}
                  value={shareData.share_url}
                />
                <Text style={styles.qrHint}>Tap to expand QR</Text>
              </Pressable>
            </View>

            <View style={styles.linkCard}>
              <Text style={styles.sectionLabel}>Share link</Text>
              <Text selectable style={styles.shareUrl}>
                {shareData.share_url}
              </Text>

              <View style={styles.linkActionsRow}>
                <Pressable
                  disabled={actionsDisabled}
                  onPress={() => {
                    void handleCopy();
                  }}
                  style={[styles.secondaryButton, actionsDisabled ? styles.buttonDisabled : null]}
                >
                  <Text style={styles.secondaryButtonText}>{copyFeedback ?? "Copy"}</Text>
                </Pressable>

                <Text style={styles.expiresAtText}>
                  Expires at {new Date(shareData.expires_at).toLocaleString()}
                </Text>
              </View>
            </View>

            {errorMessage ? (
              <View style={styles.inlineErrorCard}>
                <Text style={styles.inlineErrorText}>{errorMessage}</Text>
              </View>
            ) : null}

            <View style={styles.actionsGrid}>
              <Pressable
                disabled={actionsDisabled || isDownloadingPdf}
                onPress={() => {
                  void handleDownloadPdf();
                }}
                style={[styles.actionTile, actionsDisabled || isDownloadingPdf ? styles.buttonDisabled : null]}
              >
                <Text style={styles.actionTitle}>
                  {isDownloadingPdf ? "Opening PDF..." : "Download PDF"}
                </Text>
                <Text style={styles.actionCopy}>Open the signed masked PDF in the native viewer.</Text>
              </Pressable>

              <Pressable
                disabled={actionsDisabled || isSharing}
                onPress={() => {
                  void handleNativeShare();
                }}
                style={[styles.actionTile, actionsDisabled || isSharing ? styles.buttonDisabled : null]}
              >
                <Text style={styles.actionTitle}>{isSharing ? "Opening share sheet..." : "Share"}</Text>
                <Text style={styles.actionCopy}>Send the secure link through the device share sheet.</Text>
              </Pressable>
            </View>

            <Pressable
              disabled={isRegenerating}
              onPress={() => {
                void handleRegenerate();
              }}
              style={[styles.primaryButton, isRegenerating ? styles.buttonDisabled : null]}
            >
              <Text style={styles.primaryButtonText}>
                {isRegenerating ? "Regenerating..." : "Regenerate link"}
              </Text>
            </Pressable>
          </>
        ) : null}
      </ScrollView>

      <Modal
        animationType="fade"
        onRequestClose={() => setQrModalVisible(false)}
        transparent
        visible={isQrModalVisible && Boolean(shareData)}
      >
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Scan to verify</Text>
            {shareData ? (
              <QRCode
                backgroundColor="#ffffff"
                color="#0f172a"
                quietZone={18}
                size={280}
                value={shareData.share_url}
              />
            ) : null}
            <Text style={styles.modalCopy}>The QR encodes the full share URL, not just the token.</Text>

            <Pressable onPress={() => setQrModalVisible(false)} style={styles.modalButton}>
              <Text style={styles.modalButtonText}>Close</Text>
            </Pressable>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  actionCopy: {
    color: "#94a3b8",
    fontSize: 13,
    lineHeight: 18,
    marginTop: 8,
  },
  actionTile: {
    backgroundColor: "#111c2f",
    borderColor: "#25324a",
    borderRadius: 24,
    borderWidth: 1,
    flex: 1,
    minHeight: 124,
    paddingHorizontal: 18,
    paddingVertical: 18,
  },
  actionTitle: {
    color: "#f8fafc",
    fontSize: 17,
    fontWeight: "700",
  },
  actionsGrid: {
    flexDirection: "row",
    gap: 12,
    marginTop: 16,
  },
  buttonDisabled: {
    opacity: 0.45,
  },
  centerCard: {
    alignItems: "center",
    backgroundColor: "#0f172a",
    borderColor: "#1e293b",
    borderRadius: 32,
    borderWidth: 1,
    marginTop: 28,
    paddingHorizontal: 24,
    paddingVertical: 36,
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
  expiresAtText: {
    color: "#94a3b8",
    flex: 1,
    fontSize: 13,
    lineHeight: 18,
    textAlign: "right",
  },
  expiryPill: {
    backgroundColor: "#1d3a2d",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  expiryPillExpired: {
    backgroundColor: "#482125",
  },
  expiryPillText: {
    color: "#bbf7d0",
    fontSize: 12,
    fontWeight: "700",
  },
  expiryPillTextExpired: {
    color: "#fecdd3",
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 10,
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
  headerTitle: {
    color: "#f8fafc",
    fontSize: 18,
    fontWeight: "800",
  },
  heroCard: {
    backgroundColor: "#0f172a",
    borderColor: "#1e293b",
    borderRadius: 32,
    borderWidth: 1,
    marginTop: 24,
    paddingHorizontal: 20,
    paddingVertical: 22,
  },
  heroCopy: {
    color: "#94a3b8",
    fontSize: 15,
    lineHeight: 22,
    marginTop: 10,
  },
  heroTitle: {
    color: "#f8fafc",
    fontSize: 28,
    fontWeight: "800",
    marginTop: 16,
  },
  inlineErrorCard: {
    backgroundColor: "#3f1d24",
    borderColor: "#7f1d1d",
    borderRadius: 20,
    borderWidth: 1,
    marginTop: 14,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  inlineErrorText: {
    color: "#fecdd3",
    fontSize: 14,
    lineHeight: 20,
  },
  linkActionsRow: {
    alignItems: "center",
    flexDirection: "row",
    gap: 12,
    marginTop: 18,
  },
  linkCard: {
    backgroundColor: "#0b1220",
    borderColor: "#1e293b",
    borderRadius: 28,
    borderWidth: 1,
    marginTop: 16,
    paddingHorizontal: 18,
    paddingVertical: 18,
  },
  loadingCopy: {
    color: "#94a3b8",
    fontSize: 15,
    lineHeight: 22,
    marginTop: 10,
    textAlign: "center",
  },
  loadingTitle: {
    color: "#f8fafc",
    fontSize: 22,
    fontWeight: "700",
    marginTop: 16,
    textAlign: "center",
  },
  modalBackdrop: {
    alignItems: "center",
    backgroundColor: "rgba(2, 6, 23, 0.88)",
    flex: 1,
    justifyContent: "center",
    padding: 24,
  },
  modalCard: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderRadius: 32,
    paddingHorizontal: 22,
    paddingVertical: 28,
    width: "100%",
  },
  modalButton: {
    alignItems: "center",
    borderColor: "#cbd5e1",
    borderRadius: 18,
    borderWidth: 1,
    justifyContent: "center",
    marginTop: 20,
    minHeight: 48,
    minWidth: 92,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  modalButtonText: {
    color: "#0f172a",
    fontSize: 14,
    fontWeight: "700",
  },
  modalCopy: {
    color: "#475569",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 18,
    textAlign: "center",
  },
  modalTitle: {
    color: "#0f172a",
    fontSize: 24,
    fontWeight: "800",
    marginBottom: 22,
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
  qrCard: {
    alignItems: "center",
    backgroundColor: "#f8fafc",
    borderRadius: 28,
    marginTop: 20,
    paddingHorizontal: 18,
    paddingVertical: 18,
  },
  qrHint: {
    color: "#475569",
    fontSize: 13,
    fontWeight: "600",
    marginTop: 14,
  },
  safeArea: {
    backgroundColor: "#020617",
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 30,
    paddingHorizontal: 20,
  },
  secondaryButton: {
    alignItems: "center",
    borderColor: "#334155",
    borderRadius: 18,
    borderWidth: 1,
    justifyContent: "center",
    minHeight: 48,
    minWidth: 92,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  secondaryButtonText: {
    color: "#e2e8f0",
    fontSize: 14,
    fontWeight: "700",
  },
  sectionLabel: {
    color: "#94a3b8",
    fontSize: 13,
    fontWeight: "700",
    letterSpacing: 0.8,
    textTransform: "uppercase",
  },
  shareUrl: {
    color: "#f8fafc",
    fontSize: 16,
    lineHeight: 23,
    marginTop: 12,
  },
  statusRow: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  tokenPill: {
    backgroundColor: "#172036",
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  tokenPillText: {
    color: "#cbd5e1",
    fontSize: 12,
    fontWeight: "700",
  },
});
