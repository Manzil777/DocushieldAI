import { zodResolver } from "@hookform/resolvers/zod";
import { router } from "expo-router";
import { useState } from "react";
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  Text,
  TextInput,
  View,
} from "react-native";
import { Controller, useForm } from "react-hook-form";
import { z } from "zod";

import { AuthServiceError, authService } from "../../lib/services/authService";

const registerSchema = z
  .object({
    email: z.email("Enter a valid email address."),
    password: z.string().min(6, "Password must be at least 6 characters."),
    confirmPassword: z.string().min(6, "Confirm your password."),
  })
  .refine((data) => data.password === data.confirmPassword, {
    message: "Passwords do not match.",
    path: ["confirmPassword"],
  });

type RegisterFormValues = z.infer<typeof registerSchema>;

function getErrorMessage(error: unknown): string {
  if (error instanceof AuthServiceError) {
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "Something went wrong. Please try again.";
}

type FormInputProps = {
  autoCapitalize?: "none" | "sentences" | "words" | "characters";
  autoComplete?:
    | "email"
    | "current-password"
    | "password"
    | "new-password"
    | "off";
  error?: string;
  keyboardType?: "default" | "email-address";
  label: string;
  onBlur: () => void;
  onChangeText: (value: string) => void;
  placeholder: string;
  secureTextEntry?: boolean;
  value: string;
};

function FormInput({
  autoCapitalize = "none",
  autoComplete,
  error,
  keyboardType = "default",
  label,
  onBlur,
  onChangeText,
  placeholder,
  secureTextEntry = false,
  value,
}: FormInputProps) {
  return (
    <View className="mb-4">
      <Text className="mb-2 text-sm font-medium text-slate-700">{label}</Text>
      <TextInput
        autoCapitalize={autoCapitalize}
        autoComplete={autoComplete}
        className={`rounded-2xl border bg-white px-4 py-3 text-base text-slate-900 ${
          error ? "border-red-500" : "border-slate-200"
        }`}
        keyboardType={keyboardType}
        onBlur={onBlur}
        onChangeText={onChangeText}
        placeholder={placeholder}
        placeholderTextColor="#94a3b8"
        secureTextEntry={secureTextEntry}
        value={value}
      />
      {error ? <Text className="mt-2 text-sm text-red-600">{error}</Text> : null}
    </View>
  );
}

export default function RegisterScreen() {
  const [apiError, setApiError] = useState<string | null>(null);

  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<RegisterFormValues>({
    defaultValues: {
      confirmPassword: "",
      email: "",
      password: "",
    },
    resolver: zodResolver(registerSchema),
  });

  const onSubmit = handleSubmit(async (values) => {
    try {
      setApiError(null);
      await authService.register(values.email, values.password);
      router.replace("/login");
    } catch (error: unknown) {
      setApiError(getErrorMessage(error));
    }
  });

  return (
    <KeyboardAvoidingView
      behavior={Platform.OS === "ios" ? "padding" : undefined}
      className="flex-1 bg-slate-50"
    >
      <View className="flex-1 items-center justify-center px-6">
        <View className="w-full max-w-md rounded-3xl bg-white p-6 shadow-sm">
          <Text className="text-3xl font-bold text-slate-900">Create account</Text>
          <Text className="mt-2 text-base text-slate-500">
            Register to start using DocuShieldAI.
          </Text>

          <View className="mt-8">
            <Controller
              control={control}
              name="email"
              render={({ field: { onBlur, onChange, value } }) => (
                <FormInput
                  autoComplete="email"
                  error={errors.email?.message}
                  keyboardType="email-address"
                  label="Email"
                  onBlur={onBlur}
                  onChangeText={onChange}
                  placeholder="you@example.com"
                  value={value}
                />
              )}
            />

            <Controller
              control={control}
              name="password"
              render={({ field: { onBlur, onChange, value } }) => (
                <FormInput
                  autoComplete="new-password"
                  error={errors.password?.message}
                  label="Password"
                  onBlur={onBlur}
                  onChangeText={onChange}
                  placeholder="Create a password"
                  secureTextEntry
                  value={value}
                />
              )}
            />

            <Controller
              control={control}
              name="confirmPassword"
              render={({ field: { onBlur, onChange, value } }) => (
                <FormInput
                  autoComplete="new-password"
                  error={errors.confirmPassword?.message}
                  label="Confirm password"
                  onBlur={onBlur}
                  onChangeText={onChange}
                  placeholder="Re-enter your password"
                  secureTextEntry
                  value={value}
                />
              )}
            />

            {apiError ? (
              <Text className="mb-4 text-sm text-red-600">{apiError}</Text>
            ) : null}

            <Pressable
              accessibilityRole="button"
              className={`mt-2 min-h-12 flex-row items-center justify-center rounded-2xl ${
                isSubmitting ? "bg-slate-400" : "bg-slate-900"
              }`}
              disabled={isSubmitting}
              onPress={onSubmit}
            >
              {isSubmitting ? (
                <ActivityIndicator color="#ffffff" />
              ) : (
                <Text className="text-base font-semibold text-white">Register</Text>
              )}
            </Pressable>

            <Pressable
              accessibilityRole="button"
              className="mt-4 items-center"
              disabled={isSubmitting}
              onPress={() => router.replace("/login")}
            >
              <Text className="text-sm text-slate-600">
                Already have an account? Log in
              </Text>
            </Pressable>
          </View>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}
