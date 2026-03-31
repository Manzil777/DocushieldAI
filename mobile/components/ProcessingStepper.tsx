import { Text, View } from "react-native";
import Animated, {
  Easing,
  FadeIn,
  useAnimatedStyle,
  useSharedValue,
  withTiming,
} from "react-native-reanimated";
import { useEffect } from "react";

import { PROCESSING_STEPS, type ProcessingStep } from "../services/statusPoller";

const STEP_LABELS: Record<ProcessingStep, string> = {
  completed: "Done!",
  field_detection: "Detecting fields...",
  fraud_check: "Checking authenticity...",
  ocr: "Running OCR...",
  pii_masking: "Masking sensitive data...",
  preprocessing: "Preparing document...",
  uploaded: "Uploading...",
};

type ProcessingStepperProps = {
  currentStep: ProcessingStep;
};

export function getProcessingStepLabel(step: ProcessingStep): string {
  return STEP_LABELS[step];
}

export function ProcessingStepper({ currentStep }: ProcessingStepperProps) {
  const currentIndex = PROCESSING_STEPS.indexOf(currentStep);
  const shiftY = useSharedValue(12);
  const opacity = useSharedValue(0);

  useEffect(() => {
    shiftY.value = 12;
    opacity.value = 0;

    shiftY.value = withTiming(0, {
      duration: 260,
      easing: Easing.out(Easing.cubic),
    });
    opacity.value = withTiming(1, {
      duration: 260,
      easing: Easing.out(Easing.cubic),
    });
  }, [currentStep, opacity, shiftY]);

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: shiftY.value }],
  }));

  return (
    <View className="w-full max-w-md items-center">
      <Animated.View
        className="w-full rounded-[28px] border border-slate-200 bg-white px-6 py-5"
        style={animatedStyle}
      >
        <Text className="text-center text-xs font-semibold uppercase tracking-[2px] text-slate-500">
          AI Processing
        </Text>
        <Text className="mt-3 text-center text-2xl font-bold text-slate-950">
          {getProcessingStepLabel(currentStep)}
        </Text>
      </Animated.View>

      <View className="mt-8 w-full gap-3">
        {PROCESSING_STEPS.map((step, index) => {
          const isActive = step === currentStep;
          const isComplete = index < currentIndex;

          return (
            <Animated.View
              entering={FadeIn.duration(220)}
              key={step}
              className="flex-row items-center rounded-2xl border border-slate-200 bg-white/90 px-4 py-3"
            >
              <View
                className={[
                  "h-3 w-3 rounded-full",
                  isActive
                    ? "bg-emerald-500"
                    : isComplete
                      ? "bg-slate-950"
                      : "bg-slate-300",
                ].join(" ")}
              />
              <Text
                className={[
                  "ml-3 flex-1 text-sm",
                  isActive || isComplete
                    ? "font-semibold text-slate-950"
                    : "text-slate-500",
                ].join(" ")}
              >
                {STEP_LABELS[step]}
              </Text>
              <Text
                className={[
                  "text-xs uppercase tracking-[1.5px]",
                  isActive
                    ? "text-emerald-600"
                    : isComplete
                      ? "text-slate-700"
                      : "text-slate-400",
                ].join(" ")}
              >
                {isActive ? "Now" : isComplete ? "Done" : "Pending"}
              </Text>
            </Animated.View>
          );
        })}
      </View>
    </View>
  );
}
