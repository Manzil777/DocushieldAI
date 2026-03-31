import { StyleSheet, Text, View } from "react-native";

import type { ImageQualityResult } from "../utils/imageQuality";

type CameraOverlayProps = {
  analysis: ImageQualityResult;
  isAnalyzing: boolean;
};

const QUALITY_STYLES = {
  bad: {
    color: "#ef4444",
    label: "Bad",
  },
  good: {
    color: "#22c55e",
    label: "Good",
  },
  medium: {
    color: "#f59e0b",
    label: "Medium",
  },
} as const;

export function CameraOverlay({ analysis, isAnalyzing }: CameraOverlayProps) {
  const qualityStyle = QUALITY_STYLES[analysis.qualityLevel];

  return (
    <View pointerEvents="none" style={StyleSheet.absoluteFill}>
      <View style={styles.header}>
        <View style={[styles.qualityPill, { borderColor: qualityStyle.color }]}>
          <View style={[styles.qualityDot, { backgroundColor: qualityStyle.color }]} />
          <Text style={styles.qualityText}>
            {qualityStyle.label} {Math.round(analysis.qualityScore * 100)}%
          </Text>
        </View>
        <Text style={styles.helperText}>{analysis.helperText}</Text>
        <Text style={styles.secondaryText}>
          {isAnalyzing ? "Checking sharpness and glare..." : "Align the Aadhaar card in the frame"}
        </Text>
      </View>

      <View style={styles.maskLayer}>
        <View style={styles.maskTop} />
        <View style={styles.maskMiddle}>
          <View style={styles.maskSide} />
          <View
            style={[
              styles.guideBox,
              {
                borderColor: qualityStyle.color,
                height: `${analysis.guideBox.height * 100}%`,
                width: `${analysis.guideBox.width * 100}%`,
              },
            ]}
          >
            <View style={[styles.corner, styles.cornerTopLeft, { borderColor: qualityStyle.color }]} />
            <View style={[styles.corner, styles.cornerTopRight, { borderColor: qualityStyle.color }]} />
            <View style={[styles.corner, styles.cornerBottomLeft, { borderColor: qualityStyle.color }]} />
            <View style={[styles.corner, styles.cornerBottomRight, { borderColor: qualityStyle.color }]} />
          </View>
          <View style={styles.maskSide} />
        </View>
        <View style={styles.maskBottom} />
      </View>

      <View style={styles.metricsPanel}>
        <Text style={styles.metricText}>Blur {Math.round(analysis.blurVariance)}</Text>
        <Text style={styles.metricText}>Glare {Math.round(analysis.glareRatio * 100)}%</Text>
        <Text style={styles.metricText}>Edges {Math.round(analysis.edgeConfidence * 100)}%</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  corner: {
    height: 28,
    position: "absolute",
    width: 28,
  },
  cornerBottomLeft: {
    borderBottomWidth: 4,
    borderLeftWidth: 4,
    borderRadius: 12,
    bottom: -2,
    left: -2,
  },
  cornerBottomRight: {
    borderBottomWidth: 4,
    borderRadius: 12,
    borderRightWidth: 4,
    bottom: -2,
    right: -2,
  },
  cornerTopLeft: {
    borderLeftWidth: 4,
    borderRadius: 12,
    borderTopWidth: 4,
    left: -2,
    top: -2,
  },
  cornerTopRight: {
    borderRadius: 12,
    borderRightWidth: 4,
    borderTopWidth: 4,
    right: -2,
    top: -2,
  },
  guideBox: {
    alignItems: "center",
    borderRadius: 24,
    borderStyle: "dashed",
    borderWidth: 2,
    justifyContent: "center",
  },
  header: {
    left: 0,
    paddingHorizontal: 24,
    position: "absolute",
    right: 0,
    top: 64,
  },
  helperText: {
    color: "#f8fafc",
    fontSize: 28,
    fontWeight: "700",
    marginTop: 16,
  },
  maskBottom: {
    backgroundColor: "rgba(15, 23, 42, 0.52)",
    flex: 1,
  },
  maskLayer: {
    flex: 1,
  },
  maskMiddle: {
    alignItems: "center",
    flexDirection: "row",
    justifyContent: "center",
  },
  maskSide: {
    backgroundColor: "rgba(15, 23, 42, 0.52)",
    flex: 1,
  },
  maskTop: {
    backgroundColor: "rgba(15, 23, 42, 0.52)",
    flex: 1,
  },
  metricText: {
    color: "#e2e8f0",
    fontSize: 12,
    fontWeight: "600",
  },
  metricsPanel: {
    alignItems: "center",
    backgroundColor: "rgba(15, 23, 42, 0.78)",
    borderRadius: 20,
    bottom: 154,
    flexDirection: "row",
    gap: 12,
    left: 24,
    paddingHorizontal: 16,
    paddingVertical: 10,
    position: "absolute",
  },
  qualityDot: {
    borderRadius: 5,
    height: 10,
    width: 10,
  },
  qualityPill: {
    alignSelf: "flex-start",
    alignItems: "center",
    backgroundColor: "rgba(15, 23, 42, 0.72)",
    borderRadius: 999,
    borderWidth: 1,
    flexDirection: "row",
    gap: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  qualityText: {
    color: "#f8fafc",
    fontSize: 14,
    fontWeight: "700",
  },
  secondaryText: {
    color: "#cbd5e1",
    fontSize: 15,
    marginTop: 8,
  },
});

