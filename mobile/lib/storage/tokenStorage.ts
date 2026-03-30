import * as SecureStore from "expo-secure-store";

const ACCESS_TOKEN_KEY = "docushield_access_token";
const REFRESH_TOKEN_KEY = "docushield_refresh_token";

export type StoredTokens = {
  accessToken: string | null;
  refreshToken: string | null;
};

export async function saveTokens(accessToken: string, refreshToken: string): Promise<void> {
  await Promise.all([
    SecureStore.setItemAsync(ACCESS_TOKEN_KEY, accessToken),
    SecureStore.setItemAsync(REFRESH_TOKEN_KEY, refreshToken),
  ]);
}

export async function getTokens(): Promise<StoredTokens> {
  const [accessToken, refreshToken] = await Promise.all([
    SecureStore.getItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.getItemAsync(REFRESH_TOKEN_KEY),
  ]);

  return {
    accessToken,
    refreshToken,
  };
}

export async function clearTokens(): Promise<void> {
  await Promise.all([
    SecureStore.deleteItemAsync(ACCESS_TOKEN_KEY),
    SecureStore.deleteItemAsync(REFRESH_TOKEN_KEY),
  ]);
}
