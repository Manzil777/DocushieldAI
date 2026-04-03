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
        name="vault/index"
        options={{
          title: "Vault",
          headerShown: false,
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
      <Tabs.Screen
        name="share/[id]"
        options={{
          href: null,
          title: "Share",
          headerShown: false,
        }}
      />
      <Tabs.Screen
        name="vault/[id]"
        options={{
          href: null,
          title: "Document",
          headerShown: false,
        }}
      />
    </Tabs>
  );
}
