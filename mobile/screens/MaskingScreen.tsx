import { type Href, router } from "expo-router";
import { memo, useCallback, useMemo, useState } from "react";
import {
  ActivityIndicator,
  Alert,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
  type ImageLoadEventData,
  type LayoutChangeEvent,
  type NativeSyntheticEvent,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { BoundingBoxOverlay } from "../components/BoundingBoxOverlay";
import { ToggleRow } from "../components/ToggleRow";
import {
  DOCUMENT_FIELD_TYPES,
  DocumentServiceError,
  maskDocument,
  type DetectedDocumentField,
  type DocumentFieldType,
  type MaskConfig,
} from "../lib/services/documentService";

type MaskingRouteParams = {
  documentId: string;
  fields: DetectedDocumentField[];
  imageUrl: string;
};

type Size = {
  height: number;
  width: number;
};

type Rect = Size & {
  left: number;
  top: number;
};

const EMPTY_SIZE: Size = {
  height: 0,
  width: 0,
};

const EMPTY_FRAME: Rect = {
  height: 0,
  left: 0,
  top: 0,
  width: 0,
};

function getErrorMessage(error: unknown): string {
  if (error instanceof DocumentServiceError) {
    return error.message;
  }

  if (error instanceof Error && error.message.trim().length > 0) {
    return error.message;
  }

  return "Unable to apply masking right now.";
}

function buildInitialMaskConfig(): MaskConfig {
  return DOCUMENT_FIELD_TYPES.reduce<MaskConfig>((config, fieldType) => {
    config[fieldType] = false;
    return config;
  }, {});
}

function getUniqueDetectedFieldTypes(fields: DetectedDocumentField[]): DocumentFieldType[] {
  const detected = new Set<DocumentFieldType>();

  fields.forEach((field) => {
    detected.add(field.type);
  });

  return DOCUMENT_FIELD_TYPES.filter((fieldType) => detected.has(fieldType));
}

function getImageFrame(containerSize: Size, imageSize: Size): Rect {
  if (containerSize.width === 0 || containerSize.height === 0) {
    return EMPTY_FRAME;
  }

  if (imageSize.width === 0 || imageSize.height === 0) {
    return {
      ...containerSize,
      left: 0,
      top: 0,
    };
  }

  const containerRatio = containerSize.width / containerSize.height;
  const imageRatio = imageSize.width / imageSize.height;

  if (imageRatio > containerRatio) {
    const width = containerSize.width;
    const height = width / imageRatio;

    return {
      height,
      left: 0,
      top: (containerSize.height - height) / 2,
      width,
    };
  }

  const height = containerSize.height;
  const width = height * imageRatio;

  return {
    height,
    left: (containerSize.width - width) / 2,
    top: 0,
    width,
  };
}

function MaskingScreenComponent({ documentId, fields, imageUrl }: MaskingRouteParams) {
  const [maskConfig, setMaskConfig] = useState<MaskConfig>(() => buildInitialMaskConfig());
  const [containerSize, setContainerSize] = useState<Size>(EMPTY_SIZE);
  const [imageSize, setImageSize] = useState<Size>(EMPTY_SIZE);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const availableFieldTypes = useMemo(() => getUniqueDetectedFieldTypes(fields), [fields]);
  const selectedFields = useMemo(
    () => availableFieldTypes.filter((fieldType) => maskConfig[fieldType]),
    [availableFieldTypes, maskConfig],
  );
  const imageFrame = useMemo(
    () => getImageFrame(containerSize, imageSize),
    [containerSize, imageSize],
  );

  const handleContainerLayout = useCallback((event: LayoutChangeEvent) => {
    const { height, width } = event.nativeEvent.layout;
    setContainerSize((current) =>
      current.height === height && current.width === width ? current : { height, width },
    );
  }, []);

  const handleImageLoad = useCallback(
    (event: NativeSyntheticEvent<ImageLoadEventData>) => {
      const { height, width } = event.nativeEvent.source;

      if (height > 0 && width > 0) {
        setImageSize((current) =>
          current.height === height && current.width === width ? current : { height, width },
        );
      }
    },
    [],
  );

  const handleToggleChange = useCallback((fieldType: DocumentFieldType, value: boolean) => {
    setMaskConfig((current) => {
      if (current[fieldType] === value) {
        return current;
      }

      return {
        ...current,
        [fieldType]: value,
      };
    });
    setErrorMessage(null);
  }, []);

  const submitMasking = useCallback(async () => {
    if (selectedFields.length === 0 || isSubmitting) {
      return;
    }

    setIsSubmitting(true);
    setErrorMessage(null);

    try {
      const response = await maskDocument({
        documentId,
        fields: selectedFields,
      });

      router.replace(
        `/masked-result?maskedDocumentId=${encodeURIComponent(response.masked_document_id)}&previewUrl=${encodeURIComponent(response.preview_url)}&sourceDocumentId=${encodeURIComponent(documentId)}` as Href,
      );
    } catch (error: unknown) {
      setErrorMessage(getErrorMessage(error));
    } finally {
      setIsSubmitting(false);
    }
  }, [documentId, isSubmitting, selectedFields]);

  const handleApplyPress = useCallback(() => {
    if (selectedFields.length === 0 || isSubmitting) {
      return;
    }

    Alert.alert(
      "Apply masking",
      "This action is permanent. Do you want to proceed?",
      [
        {
          style: "cancel",
          text: "Cancel",
        },
        {
          onPress: () => {
            void submitMasking();
          },
          style: "destructive",
          text: "Proceed",
        },
      ],
      { cancelable: true },
    );
  }, [isSubmitting, selectedFields.length, submitMasking]);

  return (
    <SafeAreaView style={styles.safeArea}>
      <View style={styles.header}>
        <Pressable onPress={() => router.back()} style={styles.backButton}>
          <Text style={styles.backButtonText}>Back</Text>
        </Pressable>
        <Text style={styles.headerTitle}>Configure masking</Text>
        <View style={styles.headerSpacer} />
      </View>

      <ScrollView
        bounces={false}
        contentContainerStyle={styles.scrollContent}
        showsVerticalScrollIndicator={false}
      >
        <View style={styles.previewCard}>
          <Text style={styles.sectionTitle}>Document preview</Text>
          <Text style={styles.sectionCopy}>
            Select fields below to preview masked regions before export.
          </Text>

          <View onLayout={handleContainerLayout} style={styles.previewFrame}>
            <Image
              onLoad={handleImageLoad}
              resizeMode="contain"
              source={{ uri: imageUrl }}
              style={styles.previewImage}
            />

            <BoundingBoxOverlay fields={fields} imageFrame={imageFrame} maskConfig={maskConfig} />
          </View>
        </View>

        <View style={styles.controlsCard}>
          <View style={styles.controlsHeader}>
            <Text style={styles.sectionTitle}>Sensitive fields</Text>
            <Text style={styles.selectionBadge}>{selectedFields.length} selected</Text>
          </View>

          {availableFieldTypes.length > 0 ? (
            <View style={styles.toggleList}>
              {availableFieldTypes.map((fieldType) => (
                <ToggleRow
                  disabled={isSubmitting}
                  fieldType={fieldType}
                  key={fieldType}
                  onValueChange={(value) => {
                    handleToggleChange(fieldType, value);
                  }}
                  value={Boolean(maskConfig[fieldType])}
                />
              ))}
            </View>
          ) : (
            <View style={styles.emptyState}>
              <Text style={styles.emptyTitle}>No maskable fields found</Text>
              <Text style={styles.emptyCopy}>
                This document does not include supported sensitive field detections.
              </Text>
            </View>
          )}

          {errorMessage ? <Text style={styles.errorText}>{errorMessage}</Text> : null}

          <Pressable
            disabled={isSubmitting || selectedFields.length === 0}
            onPress={handleApplyPress}
            style={[
              styles.applyButton,
              isSubmitting || selectedFields.length === 0
                ? styles.applyButtonDisabled
                : styles.applyButtonEnabled,
            ]}
          >
            {isSubmitting ? (
              <ActivityIndicator color="#ffffff" />
            ) : (
              <Text style={styles.applyButtonText}>Apply Masking</Text>
            )}
          </Pressable>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

export const MaskingScreen = memo(MaskingScreenComponent);

const styles = StyleSheet.create({
  applyButton: {
    alignItems: "center",
    borderRadius: 22,
    justifyContent: "center",
    minHeight: 56,
    marginTop: 20,
  },
  applyButtonDisabled: {
    backgroundColor: "#94a3b8",
  },
  applyButtonEnabled: {
    backgroundColor: "#0f172a",
  },
  applyButtonText: {
    color: "#ffffff",
    fontSize: 16,
    fontWeight: "800",
    letterSpacing: 0.2,
  },
  backButton: {
    borderColor: "#cbd5e1",
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  backButtonText: {
    color: "#0f172a",
    fontSize: 14,
    fontWeight: "700",
  },
  controlsCard: {
    backgroundColor: "#f8fafc",
    borderColor: "#e2e8f0",
    borderRadius: 28,
    borderWidth: 1,
    padding: 20,
  },
  controlsHeader: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
  },
  emptyCopy: {
    color: "#64748b",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 6,
    textAlign: "center",
  },
  emptyState: {
    alignItems: "center",
    borderColor: "#cbd5e1",
    borderRadius: 22,
    borderStyle: "dashed",
    borderWidth: 1,
    marginTop: 18,
    paddingHorizontal: 20,
    paddingVertical: 28,
  },
  emptyTitle: {
    color: "#0f172a",
    fontSize: 16,
    fontWeight: "700",
  },
  errorText: {
    color: "#b91c1c",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 16,
  },
  header: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 6,
  },
  headerSpacer: {
    width: 60,
  },
  headerTitle: {
    color: "#0f172a",
    fontSize: 18,
    fontWeight: "800",
  },
  previewCard: {
    backgroundColor: "#0f172a",
    borderRadius: 32,
    overflow: "hidden",
    padding: 20,
  },
  previewFrame: {
    backgroundColor: "#020617",
    borderRadius: 24,
    height: 420,
    marginTop: 18,
    overflow: "hidden",
    position: "relative",
  },
  previewImage: {
    height: "100%",
    width: "100%",
  },
  safeArea: {
    backgroundColor: "#e2e8f0",
    flex: 1,
  },
  scrollContent: {
    gap: 18,
    padding: 20,
    paddingBottom: 28,
  },
  sectionCopy: {
    color: "#94a3b8",
    fontSize: 14,
    lineHeight: 20,
    marginTop: 6,
  },
  sectionTitle: {
    color: "#ffffff",
    fontSize: 18,
    fontWeight: "800",
  },
  selectionBadge: {
    backgroundColor: "#e2e8f0",
    borderRadius: 999,
    color: "#0f172a",
    fontSize: 12,
    fontWeight: "800",
    overflow: "hidden",
    paddingHorizontal: 10,
    paddingVertical: 6,
  },
  toggleList: {
    gap: 12,
    marginTop: 18,
  },
});
