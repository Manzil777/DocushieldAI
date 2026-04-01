import { memo, useMemo } from "react";
import { StyleSheet, View } from "react-native";

import type {
  DetectedDocumentField,
  DocumentFieldType,
  MaskConfig,
} from "../lib/services/documentService";

type Size = {
  height: number;
  width: number;
};

type Rect = Size & {
  left: number;
  top: number;
};

type BoundingBoxOverlayProps = {
  fields: DetectedDocumentField[];
  imageFrame: Rect;
  maskConfig: MaskConfig;
};

function BoundingBoxOverlayComponent({
  fields,
  imageFrame,
  maskConfig,
}: BoundingBoxOverlayProps) {
  const overlays = useMemo(
    () =>
      fields
        .filter((field) => maskConfig[field.type])
        .map((field, index) => {
          const rect = getAbsoluteRect(field, imageFrame);

          return (
            <View
              key={getOverlayKey(field.type, index)}
              pointerEvents="none"
              style={[
                styles.maskOverlay,
                {
                  height: rect.height,
                  left: rect.left,
                  top: rect.top,
                  width: rect.width,
                },
              ]}
            />
          );
        }),
    [fields, imageFrame, maskConfig],
  );

  return <>{overlays}</>;
}

function getOverlayKey(fieldType: DocumentFieldType, index: number): string {
  return `${fieldType}-${index}`;
}

function getAbsoluteRect(field: DetectedDocumentField, imageFrame: Rect): Rect {
  return {
    height: field.bbox.height * imageFrame.height,
    left: imageFrame.left + field.bbox.x * imageFrame.width,
    top: imageFrame.top + field.bbox.y * imageFrame.height,
    width: field.bbox.width * imageFrame.width,
  };
}

export const BoundingBoxOverlay = memo(BoundingBoxOverlayComponent);

const styles = StyleSheet.create({
  maskOverlay: {
    backgroundColor: "#000000",
    position: "absolute",
  },
});
