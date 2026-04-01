import { memo } from "react";
import { Pressable, StyleSheet, Switch, Text, View } from "react-native";

import type { DocumentFieldType } from "../lib/services/documentService";

type ToggleRowProps = {
  disabled?: boolean;
  fieldType: DocumentFieldType;
  onValueChange: (value: boolean) => void;
  value: boolean;
};

const FIELD_LABELS: Record<DocumentFieldType, string> = {
  address: "Address",
  dob: "Date of Birth",
  gender: "Gender",
  name: "Name",
  uid: "Aadhaar Number",
};

function ToggleRowComponent({
  disabled = false,
  fieldType,
  onValueChange,
  value,
}: ToggleRowProps) {
  return (
    <Pressable
      disabled={disabled}
      onPress={() => {
        onValueChange(!value);
      }}
      style={({ pressed }) => [
        styles.row,
        disabled ? styles.rowDisabled : null,
        pressed && !disabled ? styles.rowPressed : null,
      ]}
    >
      <View style={styles.copyBlock}>
        <Text style={styles.label}>{FIELD_LABELS[fieldType]}</Text>
        <Text style={styles.caption}>
          {value ? "Preview mask enabled" : "Leave visible in exported document"}
        </Text>
      </View>

      <Switch
        disabled={disabled}
        onValueChange={onValueChange}
        trackColor={{ false: "#cbd5e1", true: "#0f172a" }}
        thumbColor={value ? "#ffffff" : "#f8fafc"}
        value={value}
      />
    </Pressable>
  );
}

export const ToggleRow = memo(ToggleRowComponent);

const styles = StyleSheet.create({
  caption: {
    color: "#64748b",
    fontSize: 13,
    lineHeight: 18,
    marginTop: 4,
  },
  copyBlock: {
    flex: 1,
    paddingRight: 16,
  },
  label: {
    color: "#0f172a",
    fontSize: 16,
    fontWeight: "700",
  },
  row: {
    alignItems: "center",
    backgroundColor: "#ffffff",
    borderColor: "#e2e8f0",
    borderRadius: 20,
    borderWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingHorizontal: 18,
    paddingVertical: 16,
  },
  rowDisabled: {
    opacity: 0.65,
  },
  rowPressed: {
    backgroundColor: "#f8fafc",
  },
});
