import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { api, Stock, WatchlistItem } from '@/lib/api';
import { useSession } from '@/lib/session';

const colors = {
  background: '#f5f7fb',
  card: '#ffffff',
  ink: '#12213a',
  muted: '#71809a',
  accent: '#3858d6',
  border: '#e5eaf2',
  red: '#b42332',
};

export default function PortfolioScreen() {
  const { account, token, loading: sessionLoading, authenticate, signOut } = useSession();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [symbol, setSymbol] = useState('');
  const [registerMode, setRegisterMode] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let active = true;
    api.stocks()
      .then((items) => {
        if (active) setStocks(items);
      })
      .catch((cause: Error) => {
        if (active) setError(cause.message);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    if (!token) {
      setWatchlist([]);
      return;
    }
    api.watchlist(token)
      .then((items) => {
        if (active) setWatchlist(items);
      })
      .catch((cause: Error) => {
        if (active) setError(cause.message);
      });
    return () => {
      active = false;
    };
  }, [token]);

  async function submitAuth() {
    setBusy(true);
    setError('');
    try {
      await authenticate(email, password, registerMode);
      setPassword('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Authentication failed.');
    } finally {
      setBusy(false);
    }
  }

  async function addSymbol() {
    if (!token || !symbol) return;
    setBusy(true);
    setError('');
    try {
      await api.addWatchlist(symbol, token);
      setWatchlist(await api.watchlist(token));
      setSymbol('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not update watchlist.');
    } finally {
      setBusy(false);
    }
  }

  async function removeSymbol(value: string) {
    if (!token) return;
    setError('');
    try {
      await api.removeWatchlist(value, token);
      setWatchlist((items) => items.filter((item) => item.symbol !== value));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not remove stock.');
    }
  }

  async function logout() {
    try {
      await signOut();
      setError('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Could not sign out.');
    }
  }

  const selectedStock = stocks.find((item) => item.symbol === symbol);

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled">
      <Text style={styles.eyebrow}>YOUR PORTFOLIO</Text>
      <Text style={styles.title}>Watchlist</Text>
      <Text style={styles.subtitle}>Keep your market shortlist close.</Text>

      {sessionLoading ? (
        <ActivityIndicator color={colors.accent} style={styles.loading} />
      ) : account && token ? (
        <>
          <View style={styles.accountCard}>
            <View style={styles.accountInfo}>
              <Text style={styles.cardTitle}>Signed in</Text>
              <Text style={styles.email}>{account.email}</Text>
            </View>
            <Pressable accessibilityRole="button" onPress={() => void logout()}>
              <Text style={styles.link}>Sign out</Text>
            </Pressable>
          </View>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Add a stock</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.symbolList}>
              {stocks.slice(0, 16).map((stock) => (
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ selected: stock.symbol === symbol }}
                  key={stock.symbol}
                  onPress={() => setSymbol(stock.symbol)}
                  style={[styles.symbolChip, stock.symbol === symbol && styles.symbolChipActive]}>
                  <Text style={[styles.symbolText, stock.symbol === symbol && styles.symbolTextActive]}>
                    {stock.symbol}
                  </Text>
                </Pressable>
              ))}
            </ScrollView>
            <Text style={styles.selection}>
              {selectedStock ? `${selectedStock.name} · ${selectedStock.symbol}` : 'Select a supported symbol'}
            </Text>
            <Pressable
              accessibilityRole="button"
              disabled={!symbol || busy}
              onPress={() => void addSymbol()}
              style={[styles.button, (!symbol || busy) && styles.buttonDisabled]}>
              <Text style={styles.buttonText}>{busy ? 'Saving…' : 'Add to watchlist'}</Text>
            </Pressable>
          </View>

          <View style={styles.card}>
            <Text style={styles.cardTitle}>Saved stocks</Text>
            {watchlist.length ? watchlist.map((item) => (
              <View key={item.symbol} style={styles.watchlistRow}>
                <View>
                  <Text style={styles.watchSymbol}>{item.symbol}</Text>
                  <Text style={styles.date}>Added {item.created_at.slice(0, 10)}</Text>
                </View>
                <Pressable
                  accessibilityLabel={`Remove ${item.symbol}`}
                  accessibilityRole="button"
                  onPress={() => void removeSymbol(item.symbol)}>
                  <Text style={styles.remove}>Remove</Text>
                </Pressable>
              </View>
            )) : <Text style={styles.empty}>Your watchlist is empty. Add a stock above.</Text>}
          </View>
        </>
      ) : (
        <View style={styles.card}>
          <Text style={styles.cardTitle}>{registerMode ? 'Create your account' : 'Sign in to your portfolio'}</Text>
          <Text style={styles.helper}>
            {registerMode ? 'Use at least 12 characters for your password.' : 'Your saved stocks sync with your account.'}
          </Text>
          <TextInput
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            onChangeText={setEmail}
            placeholder="Email address"
            placeholderTextColor={colors.muted}
            style={styles.input}
            value={email}
          />
          <TextInput
            autoCapitalize="none"
            autoComplete={registerMode ? 'new-password' : 'current-password'}
            onChangeText={setPassword}
            placeholder="Password"
            placeholderTextColor={colors.muted}
            secureTextEntry
            style={styles.input}
            value={password}
          />
          <Pressable
            accessibilityRole="button"
            disabled={busy || !email || !password}
            onPress={() => void submitAuth()}
            style={[styles.button, (busy || !email || !password) && styles.buttonDisabled]}>
            <Text style={styles.buttonText}>
              {busy ? 'Please wait…' : registerMode ? 'Create account' : 'Sign in'}
            </Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={() => setRegisterMode((value) => !value)}>
            <Text style={styles.switch}>
              {registerMode ? 'Already registered? Sign in' : 'New here? Create an account'}
            </Text>
          </Pressable>
        </View>
      )}
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
      <Text style={styles.disclaimer}>
        Watchlists are for tracking only. Forecasts are not investment advice.
      </Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.background },
  content: { padding: 20, paddingTop: 28, paddingBottom: 44 },
  eyebrow: { color: colors.accent, fontSize: 11, fontWeight: '800', letterSpacing: 1.5 },
  title: { color: colors.ink, fontSize: 29, fontWeight: '800', marginTop: 8 },
  subtitle: { color: colors.muted, fontSize: 14, marginBottom: 20, marginTop: 6 },
  loading: { marginTop: 28 },
  card: { backgroundColor: colors.card, borderColor: colors.border, borderRadius: 18, borderWidth: 1, marginBottom: 14, padding: 18 },
  accountCard: { alignItems: 'center', backgroundColor: colors.card, borderColor: colors.border, borderRadius: 16, borderWidth: 1, flexDirection: 'row', justifyContent: 'space-between', marginBottom: 14, padding: 16 },
  accountInfo: { flex: 1, marginRight: 10 },
  cardTitle: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  email: { color: colors.muted, fontSize: 13, marginTop: 5 },
  link: { color: colors.accent, fontSize: 13, fontWeight: '700' },
  symbolList: { gap: 7, paddingVertical: 14 },
  symbolChip: { backgroundColor: '#f7f8fc', borderColor: colors.border, borderRadius: 15, borderWidth: 1, paddingHorizontal: 11, paddingVertical: 8 },
  symbolChipActive: { backgroundColor: colors.accent, borderColor: colors.accent },
  symbolText: { color: colors.muted, fontSize: 11, fontWeight: '700' },
  symbolTextActive: { color: '#fff' },
  selection: { color: colors.muted, fontSize: 12, marginBottom: 12 },
  button: { alignItems: 'center', backgroundColor: colors.accent, borderRadius: 11, justifyContent: 'center', minHeight: 46, paddingHorizontal: 14 },
  buttonDisabled: { opacity: 0.55 },
  buttonText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  watchlistRow: { alignItems: 'center', borderBottomColor: colors.border, borderBottomWidth: 1, flexDirection: 'row', justifyContent: 'space-between', paddingVertical: 14 },
  watchSymbol: { color: colors.ink, fontSize: 15, fontWeight: '800' },
  date: { color: colors.muted, fontSize: 11, marginTop: 4 },
  remove: { color: colors.red, fontSize: 12, fontWeight: '700' },
  empty: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 12 },
  helper: { color: colors.muted, fontSize: 12, lineHeight: 18, marginBottom: 16, marginTop: 6 },
  input: { backgroundColor: '#f7f8fc', borderColor: colors.border, borderRadius: 11, borderWidth: 1, color: colors.ink, fontSize: 14, marginBottom: 11, paddingHorizontal: 13, paddingVertical: 12 },
  switch: { color: colors.accent, fontSize: 13, fontWeight: '700', marginTop: 18, textAlign: 'center' },
  error: { color: colors.red, fontSize: 13, marginBottom: 10 },
  disclaimer: { color: colors.muted, fontSize: 11, lineHeight: 16, marginTop: 4 },
});
