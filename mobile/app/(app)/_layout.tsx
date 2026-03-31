import { Tabs } from "expo-router";

export default function AppLayout() {
  return (
    <Tabs>
      <Tabs.Screen
        name="index"
        options={{
          title: "Home",
          headerTitle: "Home",
        }}
      />
      <Tabs.Screen
        name="camera"
        options={{
          href: null,
          title: "Capture",
          headerShown: false,
        }}
      />
    </Tabs>
  );
}
