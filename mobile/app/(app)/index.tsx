import { router } from "expo-router";
import { Pressable, Text, View } from "react-native";

export default function HomeScreen() {
  return (
    <View className="flex-1 items-center justify-center bg-slate-950 px-6">
      <View className="w-full max-w-md rounded-[32px] bg-slate-900 p-6">
        <Text className="text-3xl font-bold text-white">DocuShieldAI</Text>
        <Text className="mt-3 text-base leading-6 text-slate-300">
          Capture an Aadhaar card with live sharpness and glare validation before upload.
        </Text>

        <Pressable
          className="mt-8 min-h-14 items-center justify-center rounded-2xl bg-emerald-400"
          onPress={() => router.push("/camera")}
        >
          <Text className="text-base font-semibold text-slate-950">Open camera</Text>
        </Pressable>
      </View>
    </View>
  );
}
