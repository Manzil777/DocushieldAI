import { type Href, router } from "expo-router";
import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  FlatList,
  Image,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import {
  DocumentServiceError,
  fetchVaultItems,
  type VaultItem,
} from "../../../lib/services/documentService";

type VaultState = {
  errorMessage: string | null;
  isInitialLoading: boolean;
  isLoadingMore: boolean;
  isRefreshing: boolean;
  items: VaultItem[];
  nextCursor?: string;
};

function getVaultErrorMessage(error: unknown): string {
  if (error instanceof DocumentServiceError) {
    return error.message;
  }

  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return "Unable to load your vault right now.";
}

function formatCreatedAt(value: string): string {
  const timestamp = Date.parse(value);

  if (Number.isNaN(timestamp)) {
    return "Unknown date";
  }

  return new Date(timestamp).toLocaleString();
}

export default function VaultListScreen() {
  const [state, setState] = useState<VaultState>({
    errorMessage: null,
    isInitialLoading: true,
    isLoadingMore: false,
    isRefreshing: false,
    items: [],
    nextCursor: undefined,
  });

  async function loadVaultPage(options?: { cursor?: string; mode?: "append" | "refresh" | "replace" }) {
    const mode = options?.mode ?? "replace";

    setState((current) => ({
      ...current,
      errorMessage: null,
      isInitialLoading: mode === "replace",
      isLoadingMore: mode === "append",
      isRefreshing: mode === "refresh",
    }));

    try {
      const response = await fetchVaultItems(options?.cursor);

      setState((current) => ({
        ...current,
        errorMessage: null,
        isInitialLoading: false,
        isLoadingMore: false,
        isRefreshing: false,
        items: mode === "append" ? [...current.items, ...response.items] : response.items,
        nextCursor: response.next_cursor,
      }));
    } catch (error: unknown) {
      setState((current) => ({
        ...current,
        errorMessage: getVaultErrorMessage(error),
        isInitialLoading: false,
        isLoadingMore: false,
        isRefreshing: false,
      }));
    }
  }

  useEffect(() => {
    void loadVaultPage();
  }, []);

  const renderItem = ({ item }: { item: VaultItem }) => (
    <Pressable
      onPress={() => router.push(`/vault/${encodeURIComponent(item.id)}` as Href)}
      style={styles.card}
    >
      {item.thumbnail_url ? (
        <Image resizeMode="cover" source={{ uri: item.thumbnail_url }} style={styles.thumbnail} />
      ) : (
        <View style={[styles.thumbnail, styles.thumbnailPlaceholder]}>
          <Text style={styles.thumbnailPlaceholderText}>
            {item.document_type.slice(0, 2).toUpperCase()}
          </Text>
        </View>
      )}

      <View style={styles.cardBody}>
        <Text numberOfLines={1} style={styles.cardTitle}>
          {item.document_type}
        </Text>
        <Text style={styles.cardMeta}>{formatCreatedAt(item.created_at)}</Text>
      </View>
    </Pressable>
  );

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.header}>
        <Pressable onPress={() => router.replace("/(app)")} style={styles.headerButton}>
          <Text style={styles.headerButtonText}>Home</Text>
        </Pressable>

        <Text style={styles.headerTitle}>Vault</Text>

        <View style={styles.headerSpacer} />
      </View>

      {state.isInitialLoading ? (
        <View style={styles.centerState}>
          <ActivityIndicator color="#e2e8f0" size="large" />
          <Text style={styles.centerTitle}>Loading your vault</Text>
          <Text style={styles.centerCopy}>Fetching masked documents and recent uploads.</Text>
        </View>
      ) : (
        <FlatList
          contentContainerStyle={styles.listContent}
          data={state.items}
          keyExtractor={(item) => item.id}
          ListEmptyComponent={
            <View style={styles.emptyCard}>
              <View style={styles.emptyIllustration} />
              <Text style={styles.emptyTitle}>No documents in vault</Text>
              <Text style={styles.emptyCopy}>
                Captured and stored masked documents will appear here once they are available.
              </Text>
            </View>
          }
          ListFooterComponent={
            state.isLoadingMore ? (
              <View style={styles.footerLoader}>
                <ActivityIndicator color="#94a3b8" />
              </View>
            ) : null
          }
          onEndReached={() => {
            if (!state.nextCursor || state.isLoadingMore || state.isRefreshing || state.isInitialLoading) {
              return;
            }

            void loadVaultPage({
              cursor: state.nextCursor,
              mode: "append",
            });
          }}
          onEndReachedThreshold={0.45}
          onRefresh={() => {
            void loadVaultPage({ mode: "refresh" });
          }}
          refreshing={state.isRefreshing}
          renderItem={renderItem}
          showsVerticalScrollIndicator={false}
        />
      )}

      {state.errorMessage ? (
        <View style={styles.errorBanner}>
          <Text style={styles.errorText}>{state.errorMessage}</Text>
          <Pressable
            onPress={() => {
              void loadVaultPage();
            }}
            style={styles.retryButton}
          >
            <Text style={styles.retryButtonText}>Retry</Text>
          </Pressable>
        </View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  card: {
    alignItems: "center",
    backgroundColor: "#0f172a",
    borderColor: "#1e293b",
    borderRadius: 24,
    borderWidth: 1,
    flexDirection: "row",
    marginBottom: 14,
    padding: 14,
  },
  cardBody: {
    flex: 1,
    marginLeft: 14,
  },
  cardMeta: {
    color: "#94a3b8",
    fontSize: 13,
    marginTop: 8,
  },
  cardTitle: {
    color: "#f8fafc",
    fontSize: 17,
    fontWeight: "700",
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
    marginTop: 18,
  },
  emptyCard: {
    alignItems: "center",
    backgroundColor: "#0f172a",
    borderColor: "#1e293b",
    borderRadius: 28,
    borderWidth: 1,
    marginTop: 24,
    paddingHorizontal: 24,
    paddingVertical: 36,
  },
  emptyCopy: {
    color: "#94a3b8",
    fontSize: 15,
    lineHeight: 22,
    marginTop: 12,
    textAlign: "center",
  },
  emptyIllustration: {
    backgroundColor: "#1e293b",
    borderRadius: 24,
    height: 72,
    marginBottom: 18,
    width: 72,
  },
  emptyTitle: {
    color: "#f8fafc",
    fontSize: 22,
    fontWeight: "700",
  },
  errorBanner: {
    backgroundColor: "#3f1d24",
    borderColor: "#7f1d1d",
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    borderWidth: 1,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  errorText: {
    color: "#fecdd3",
    fontSize: 14,
    lineHeight: 20,
  },
  footerLoader: {
    paddingBottom: 16,
    paddingTop: 4,
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
  listContent: {
    flexGrow: 1,
    paddingHorizontal: 20,
    paddingTop: 22,
  },
  retryButton: {
    alignSelf: "flex-start",
    borderColor: "#fecdd3",
    borderRadius: 999,
    borderWidth: 1,
    marginTop: 10,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  retryButtonText: {
    color: "#fecdd3",
    fontSize: 13,
    fontWeight: "700",
  },
  safeArea: {
    backgroundColor: "#020617",
    flex: 1,
  },
  thumbnail: {
    backgroundColor: "#111827",
    borderRadius: 18,
    height: 68,
    width: 68,
  },
  thumbnailPlaceholder: {
    alignItems: "center",
    borderColor: "#334155",
    borderWidth: 1,
    justifyContent: "center",
  },
  thumbnailPlaceholderText: {
    color: "#cbd5e1",
    fontSize: 18,
    fontWeight: "800",
  },
});
