import { router, useLocalSearchParams } from "expo-router";
import { Image, Pressable, Text, View } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

type ResultParams = {
  maskedDocumentId?: string | string[];
  previewUrl?: string | string[];
  sourceDocumentId?: string | string[];
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

export default function MaskedResultScreen() {
  const params = useLocalSearchParams<ResultParams>();
  const previewUrl = getParamValue(params.previewUrl);
  const maskedDocumentId = getParamValue(params.maskedDocumentId);

  return (
    <SafeAreaView className="flex-1 bg-slate-950">
      <View className="flex-1 px-5 pb-6 pt-3">
        <View className="flex-row items-center justify-between">
          <Pressable
            className="rounded-full border border-slate-700 px-4 py-2"
            onPress={() => router.replace("/")}
          >
            <Text className="text-sm font-semibold text-white">Home</Text>
          </Pressable>

          <Text className="text-lg font-extrabold text-white">Masked result</Text>
          <View className="w-16" />
        </View>

        <View className="mt-6 flex-1 rounded-[28px] bg-slate-900 p-4">
          <Text className="text-base font-semibold text-emerald-300">Masking applied</Text>
          {maskedDocumentId ? (
            <Text className="mt-2 text-sm text-slate-400">
              Masked document ID: {maskedDocumentId}
            </Text>
          ) : null}

          <View className="mt-4 flex-1 overflow-hidden rounded-[24px] bg-slate-950">
            {previewUrl ? (
              <Image
                resizeMode="contain"
                source={{ uri: previewUrl }}
                style={{ width: "100%", height: "100%" }}
              />
            ) : (
              <View className="flex-1 items-center justify-center px-6">
                <Text className="text-center text-base text-slate-400">
                  Preview unavailable for this masked document.
                </Text>
              </View>
            )}
          </View>

          <Pressable
            className="mt-5 min-h-14 items-center justify-center rounded-2xl bg-white"
            onPress={() => router.replace("/")}
          >
            <Text className="text-base font-bold text-slate-950">Done</Text>
          </Pressable>
        </View>
      </View>
    </SafeAreaView>
  );
}
