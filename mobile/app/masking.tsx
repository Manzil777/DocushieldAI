import { useLocalSearchParams } from "expo-router";
import { Text, View } from "react-native";

import { MaskingScreen } from "../screens/MaskingScreen";
import {
  DOCUMENT_FIELD_TYPES,
  type DetectedDocumentField,
  type DocumentFieldType,
} from "../lib/services/documentService";

type MaskingSearchParams = {
  documentId?: string | string[];
  fields?: string | string[];
  imageUrl?: string | string[];
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

function isFieldType(value: string): value is DocumentFieldType {
  return (DOCUMENT_FIELD_TYPES as readonly string[]).includes(value);
}

function parseFieldsParam(value: string | null): DetectedDocumentField[] | null {
  if (!value) {
    return null;
  }

  try {
    const parsed = JSON.parse(value) as unknown;

    if (!Array.isArray(parsed)) {
      return null;
    }

    return parsed.flatMap((item) => {
      if (!item || typeof item !== "object") {
        return [];
      }

      const nextField = item as Partial<DetectedDocumentField>;

      if (
        typeof nextField.type !== "string" ||
        !isFieldType(nextField.type) ||
        !nextField.bbox ||
        typeof nextField.bbox !== "object"
      ) {
        return [];
      }

      const bbox = nextField.bbox as Partial<DetectedDocumentField["bbox"]>;

      if (
        typeof bbox.x !== "number" ||
        typeof bbox.y !== "number" ||
        typeof bbox.width !== "number" ||
        typeof bbox.height !== "number"
      ) {
        return [];
      }

      return [
        {
          bbox: {
            height: bbox.height,
            width: bbox.width,
            x: bbox.x,
            y: bbox.y,
          },
          type: nextField.type,
        },
      ];
    });
  } catch {
    return null;
  }
}

export default function MaskingRoute() {
  const params = useLocalSearchParams<MaskingSearchParams>();
  const documentId = getParamValue(params.documentId);
  const imageUrl = getParamValue(params.imageUrl);
  const fields = parseFieldsParam(getParamValue(params.fields));

  if (!documentId || !imageUrl || !fields) {
    return (
      <View className="flex-1 items-center justify-center bg-slate-100 px-6">
        <View className="w-full max-w-md rounded-[28px] border border-slate-200 bg-white p-6">
          <Text className="text-xl font-bold text-slate-950">Missing masking data</Text>
          <Text className="mt-3 text-base leading-6 text-slate-600">
            Open this screen with `documentId`, `imageUrl`, and serialized `fields` params.
          </Text>
        </View>
      </View>
    );
  }

  return <MaskingScreen documentId={documentId} fields={fields} imageUrl={imageUrl} />;
}
