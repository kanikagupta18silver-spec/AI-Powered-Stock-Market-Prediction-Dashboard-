import * as SecureStore from 'expo-secure-store';
import {
  createContext,
  PropsWithChildren,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { Platform } from 'react-native';

import { Account, api } from './api';

const TOKEN_KEY = 'stock-dashboard-access-token';

type SessionContextValue = {
  account: Account | null;
  token: string | null;
  loading: boolean;
  error: string;
  authenticate: (email: string, password: string, register: boolean) => Promise<void>;
  signOut: () => Promise<void>;
  clearError: () => void;
};

const SessionContext = createContext<SessionContextValue | null>(null);

async function readToken(): Promise<string | null> {
  if (Platform.OS === 'web') {
    return typeof localStorage === 'undefined'
      ? null
      : localStorage.getItem(TOKEN_KEY);
  }
  return SecureStore.getItemAsync(TOKEN_KEY);
}

async function writeToken(token: string | null): Promise<void> {
  if (Platform.OS === 'web') {
    if (typeof localStorage === 'undefined') return;
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
    return;
  }
  if (token) await SecureStore.setItemAsync(TOKEN_KEY, token);
  else await SecureStore.deleteItemAsync(TOKEN_KEY);
}

export function SessionProvider({ children }: PropsWithChildren) {
  const [account, setAccount] = useState<Account | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    async function restoreSession() {
      try {
        const savedToken = await readToken();
        if (savedToken && active) {
          setToken(savedToken);
          try {
            setAccount(await api.me(savedToken));
          } catch (cause) {
            if (active) {
              setError(
                cause instanceof Error ? cause.message : 'Could not restore account.',
              );
            }
          }
        }
      } catch (cause) {
        if (active) {
          setError(cause instanceof Error ? cause.message : 'Could not read saved session.');
        }
      } finally {
        if (active) setLoading(false);
      }
    }
    void restoreSession();
    return () => {
      active = false;
    };
  }, []);

  async function authenticate(
    email: string,
    password: string,
    register: boolean,
  ) {
    setError('');
    if (register) await api.register(email, password);
    const result = await api.login(email, password);
    await writeToken(result.access_token);
    const currentAccount = await api.me(result.access_token);
    setToken(result.access_token);
    setAccount(currentAccount);
  }

  async function signOut() {
    await writeToken(null);
    setToken(null);
    setAccount(null);
  }

  const value = useMemo(
    () => ({
      account,
      token,
      loading,
      error,
      authenticate,
      signOut,
      clearError: () => setError(''),
    }),
    [account, token, loading, error],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): SessionContextValue {
  const context = useContext(SessionContext);
  if (!context) throw new Error('useSession must be used inside SessionProvider.');
  return context;
}
