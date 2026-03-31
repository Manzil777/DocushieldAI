import { type Href, router, useFocusEffect } from "expo-router";
import { CameraView, useCameraPermissions } from "expo-camera";
import * as ImageManipulator from "expo-image-manipulator";
import {
  startTransition,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import {
  ActivityIndicator,
  Alert,
  Pressable,
  StyleSheet,
  Text,
  View,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { CameraOverlay } from "../components/CameraOverlay";
import {
  analyzePreviewImage,
  getEmptyQualityResult,
  type ImageQualityResult,
} from "../utils/imageQuality";
import {
  DocumentServiceError,
  uploadDocumentImage,
  type UploadDocumentResponse,
} from "../lib/services/documentService";

const ANALYSIS_INTERVAL_MS = 450;
const PREVIEW_CAPTURE_QUALITY = 0.18;

function getUploadErrorMessage(error: unknown): string {
  if (error instanceof DocumentServiceError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong while uploading the document.";
}

async function maybeCropToGuide(
  uri: string,
  width: number,
  height: number,
  analysis: ImageQualityResult,
): Promise<{ height: number; type: string; uri: string; width: number }> {
  if (analysis.edgeConfidence < 0.45) {
    return {
      height,
      type: "image/jpeg",
      uri,
      width,
    };
  }

  const crop = {
    height: Math.floor(height * analysis.guideBox.height),
    originX: Math.floor(width * analysis.guideBox.x),
    originY: Math.floor(height * analysis.guideBox.y),
    width: Math.floor(width * analysis.guideBox.width),
  };

  const result = await ImageManipulator.manipulateAsync(
    uri,
    [{ crop }],
    {
      compress: 0.92,
      format: ImageManipulator.SaveFormat.JPEG,
    },
  );

  return {
    height: result.height,
    type: "image/jpeg",
    uri: result.uri,
    width: result.width,
  };
}

export default function CameraScreen() {
  const cameraRef = useRef<CameraView | null>(null);
  const analyzingRef = useRef(false);
  const capturingRef = useRef(false);
  const mountedRef = useRef(true);

  const [permission, requestPermission] = useCameraPermissions();
  const [cameraReady, setCameraReady] = useState(false);
  const [analysis, setAnalysis] = useState<ImageQualityResult>(getEmptyQualityResult());
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<UploadDocumentResponse | null>(null);

  const isCaptureEnabled = analysis.qualityLevel === "good" && !isUploading && cameraReady;

  useEffect(() => {
    return () => {
      mountedRef.current = false;
    };
  }, []);

  useFocusEffect(
    useCallback(() => {
      mountedRef.current = true;
      return () => {
        setCameraReady(false);
      };
    }, []),
  );

  const runPreviewAnalysis = useCallback(async () => {
    if (!cameraRef.current || analyzingRef.current || capturingRef.current || !cameraReady) {
      return;
    }

    analyzingRef.current = true;

    if (mountedRef.current) {
      setIsAnalyzing(true);
    }

    try {
      const snapshot = await cameraRef.current.takePictureAsync({
        base64: true,
        quality: PREVIEW_CAPTURE_QUALITY,
        shutterSound: false,
        skipProcessing: true,
      });

      const nextAnalysis = analyzePreviewImage(snapshot.base64);

      if (__DEV__) {
        console.debug("camera-quality", {
          blurVariance: Math.round(nextAnalysis.blurVariance),
          edgeConfidence: Number(nextAnalysis.edgeConfidence.toFixed(2)),
          glareRatio: Number(nextAnalysis.glareRatio.toFixed(2)),
          qualityScore: Number(nextAnalysis.qualityScore.toFixed(2)),
        });
      }

      if (mountedRef.current) {
        startTransition(() => {
          setAnalysis(nextAnalysis);
        });
      }
    } catch {
      if (mountedRef.current) {
        startTransition(() => {
          setAnalysis((current) => ({
            ...current,
            helperText: "Keep the card inside the frame",
          }));
        });
      }
    } finally {
      analyzingRef.current = false;

      if (mountedRef.current) {
        setIsAnalyzing(false);
      }
    }
  }, [cameraReady]);

  useEffect(() => {
    if (!permission?.granted || !cameraReady) {
      return;
    }

    const intervalId = setInterval(() => {
      void runPreviewAnalysis();
    }, ANALYSIS_INTERVAL_MS);

    return () => {
      clearInterval(intervalId);
    };
  }, [cameraReady, permission?.granted, runPreviewAnalysis]);

  const requestCameraAccess = useCallback(async () => {
    const result = await requestPermission();

    if (!result.granted) {
      Alert.alert(
        "Camera access needed",
        "Allow camera access to capture Aadhaar cards securely.",
      );
    }
  }, [requestPermission]);

  const handleCapture = useCallback(async () => {
    if (!cameraRef.current || capturingRef.current || !isCaptureEnabled) {
      return;
    }

    capturingRef.current = true;
    setIsUploading(true);
    setUploadResult(null);

    try {
      const picture = await cameraRef.current.takePictureAsync({
        quality: 0.9,
        shutterSound: false,
      });

      const preparedImage = await maybeCropToGuide(
        picture.uri,
        picture.width,
        picture.height,
        analysis,
      );
      const response = await uploadDocumentImage({
        name: "aadhaar-capture.jpg",
        type: preparedImage.type,
        uri: preparedImage.uri,
      });

      if (mountedRef.current) {
        setUploadResult(response);
        router.push(`/loader?documentId=${encodeURIComponent(response.document_id)}` as Href);
      }
    } catch (error: unknown) {
      Alert.alert("Upload failed", getUploadErrorMessage(error));
    } finally {
      capturingRef.current = false;
      if (mountedRef.current) {
        setIsUploading(false);
      }
    }
  }, [analysis, isCaptureEnabled]);

  const qualityText = useMemo(() => {
    if (uploadResult) {
      return `Uploaded document ${uploadResult.document_id.slice(0, 8)}...`;
    }

    return "Capture is enabled only when the card is sharp, centered, and glare is low.";
  }, [uploadResult]);

  if (!permission) {
    return (
      <View style={styles.centeredScreen}>
        <ActivityIndicator color="#0f172a" />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <SafeAreaView style={styles.permissionScreen}>
        <View style={styles.permissionCard}>
          <Text style={styles.permissionTitle}>Camera access required</Text>
          <Text style={styles.permissionBody}>
            DocuShieldAI uses the camera to capture Aadhaar cards with live quality checks before upload.
          </Text>

          <Pressable onPress={requestCameraAccess} style={styles.primaryButton}>
            <Text style={styles.primaryButtonText}>Allow camera</Text>
          </Pressable>

          <Pressable onPress={() => router.back()} style={styles.secondaryButton}>
            <Text style={styles.secondaryButtonText}>Back</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <View style={styles.container}>
      <CameraView
        active
        facing="back"
        onCameraReady={() => setCameraReady(true)}
        ref={cameraRef}
        style={StyleSheet.absoluteFill}
      />

      <CameraOverlay analysis={analysis} isAnalyzing={isAnalyzing} />

      <SafeAreaView pointerEvents="box-none" style={StyleSheet.absoluteFill}>
        <View style={styles.topActions}>
          <Pressable onPress={() => router.back()} style={styles.topButton}>
            <Text style={styles.topButtonText}>Back</Text>
          </Pressable>
        </View>

        <View style={styles.bottomDock}>
          <Text style={styles.bottomDockText}>{qualityText}</Text>

          {uploadResult ? (
            <Text style={styles.successText}>
              Upload complete. Document ID: {uploadResult.document_id}
            </Text>
          ) : null}

          <View style={styles.controlsRow}>
            <View style={styles.captureSpacer} />

            <Pressable
              disabled={!isCaptureEnabled}
              onPress={handleCapture}
              style={[
                styles.captureButton,
                isCaptureEnabled ? styles.captureButtonEnabled : styles.captureButtonDisabled,
              ]}
            >
              {isUploading ? (
                <ActivityIndicator color="#0f172a" />
              ) : (
                <View style={styles.captureButtonInner} />
              )}
            </Pressable>

            <View style={styles.captureSpacer}>
              <Text
                style={[
                  styles.captureStatus,
                  isCaptureEnabled ? styles.captureReadyText : styles.captureBlockedText,
                ]}
              >
                {isCaptureEnabled ? "Ready" : "Waiting"}
              </Text>
            </View>
          </View>
        </View>
      </SafeAreaView>
    </View>
  );
}

const styles = StyleSheet.create({
  bottomDock: {
    backgroundColor: "rgba(15, 23, 42, 0.84)",
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    marginTop: "auto",
    paddingBottom: 28,
    paddingHorizontal: 24,
    paddingTop: 18,
  },
  bottomDockText: {
    color: "#cbd5e1",
    fontSize: 14,
    lineHeight: 20,
  },
  captureBlockedText: {
    color: "#fca5a5",
  },
  captureButton: {
    alignItems: "center",
    borderRadius: 44,
    borderWidth: 4,
    height: 88,
    justifyContent: "center",
    width: 88,
  },
  captureButtonDisabled: {
    backgroundColor: "#475569",
    borderColor: "#64748b",
  },
  captureButtonEnabled: {
    backgroundColor: "#f8fafc",
    borderColor: "#22c55e",
  },
  captureButtonInner: {
    backgroundColor: "#0f172a",
    borderRadius: 28,
    height: 56,
    width: 56,
  },
  captureReadyText: {
    color: "#86efac",
  },
  captureSpacer: {
    alignItems: "center",
    flex: 1,
  },
  captureStatus: {
    fontSize: 14,
    fontWeight: "700",
  },
  centeredScreen: {
    alignItems: "center",
    backgroundColor: "#f8fafc",
    flex: 1,
    justifyContent: "center",
  },
  container: {
    backgroundColor: "#020617",
    flex: 1,
  },
  controlsRow: {
    alignItems: "center",
    flexDirection: "row",
    marginTop: 18,
  },
  permissionBody: {
    color: "#475569",
    fontSize: 16,
    lineHeight: 24,
    marginTop: 12,
    textAlign: "center",
  },
  permissionCard: {
    backgroundColor: "#ffffff",
    borderRadius: 28,
    marginHorizontal: 24,
    padding: 24,
  },
  permissionScreen: {
    backgroundColor: "#e2e8f0",
    flex: 1,
    justifyContent: "center",
  },
  permissionTitle: {
    color: "#0f172a",
    fontSize: 28,
    fontWeight: "700",
    textAlign: "center",
  },
  primaryButton: {
    alignItems: "center",
    backgroundColor: "#0f172a",
    borderRadius: 18,
    marginTop: 24,
    paddingVertical: 14,
  },
  primaryButtonText: {
    color: "#f8fafc",
    fontSize: 16,
    fontWeight: "700",
  },
  secondaryButton: {
    alignItems: "center",
    borderColor: "#cbd5e1",
    borderRadius: 18,
    borderWidth: 1,
    marginTop: 12,
    paddingVertical: 14,
  },
  secondaryButtonText: {
    color: "#0f172a",
    fontSize: 16,
    fontWeight: "600",
  },
  successText: {
    color: "#86efac",
    fontSize: 13,
    lineHeight: 18,
    marginTop: 8,
  },
  topActions: {
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 20,
    paddingTop: 8,
  },
  topButton: {
    backgroundColor: "rgba(15, 23, 42, 0.78)",
    borderRadius: 999,
    paddingHorizontal: 16,
    paddingVertical: 10,
  },
  topButtonText: {
    color: "#f8fafc",
    fontSize: 14,
    fontWeight: "700",
  },
});
