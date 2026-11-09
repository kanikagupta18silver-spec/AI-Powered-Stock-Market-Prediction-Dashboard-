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

import { api, Forecast, formatPrice, PriceRow, Stock } from '@/lib/api';
import { useSession } from '@/lib/session';

const palette = {
  background: '#f5f7fb',
  card: '#ffffff',
  ink: '#12213a',
  muted: '#71809a',
  accent: '#3858d6',
  border: '#e5eaf2',
  green: '#17835d',
};

export default function MarketScreen() {
  const { token } = useSession();
  const [stocks, setStocks] = useState<Stock[]>([]);
  const [symbol, setSymbol] = useState('AAPL');
  const [history, setHistory] = useState<PriceRow[]>([]);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [horizon, setHorizon] = useState('30');
  const [loading, setLoading] = useState(true);
  const [forecasting, setForecasting] = useState(false);
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
    setLoading(true);
    setError('');
    setForecast(null);
    api.history(symbol)
      .then(({ data }) => {
        if (active) setHistory(data);
      })
      .catch((cause: Error) => {
        if (active) setError(cause.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [symbol]);

  async function runForecast() {
    const days = Number(horizon);
    if (!Number.isInteger(days) || days < 1 || days > 60) {
      setError('Choose a forecast horizon between 1 and 60 trading days.');
      return;
    }
    setForecasting(true);
    setError('');
    try {
      setForecast(await api.forecast(symbol, days, token));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Forecast failed.');
    } finally {
      setForecasting(false);
    }
  }

  const latest = history.at(-1);
  const previous = history.at(-2);
  const change = latest && previous ? latest.close - previous.close : 0;
  const changePercent =
    latest && previous && previous.close
      ? (change / previous.close) * 100
      : 0;

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      keyboardShouldPersistTaps="handled">
      <Text style={styles.eyebrow}>MARKET OVERVIEW</Text>
      <Text style={styles.title}>Stock insights</Text>
      <Text style={styles.subtitle}>History, model evaluation and forecasts.</Text>

      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.symbolList}>
        {stocks.map((stock) => (
          <Pressable
            key={stock.symbol}
            accessibilityRole="button"
            accessibilityState={{ selected: stock.symbol === symbol }}
            onPress={() => setSymbol(stock.symbol)}
            style={[styles.symbolChip, stock.symbol === symbol && styles.symbolChipActive]}>
            <Text style={[styles.symbolText, stock.symbol === symbol && styles.symbolTextActive]}>
              {stock.symbol}
            </Text>
          </Pressable>
        ))}
      </ScrollView>

      <View style={styles.card}>
        <Text style={styles.company}>{stocks.find((stock) => stock.symbol === symbol)?.name ?? symbol}</Text>
        <Text style={styles.price}>
          {latest ? formatPrice(latest.close, symbol) : '—'}
        </Text>
        <Text style={[styles.change, change < 0 && styles.changeDown]}>
          {change >= 0 ? '+' : ''}
          {formatPrice(change, symbol)} ({changePercent.toFixed(2)}%) today
        </Text>
        <View style={styles.divider} />
        <View style={styles.row}>
          <Text style={styles.label}>Latest close</Text>
          <Text style={styles.value}>{latest?.date.slice(0, 10) ?? '—'}</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>Observations</Text>
          <Text style={styles.value}>{history.length || '—'}</Text>
        </View>
        {loading && <ActivityIndicator color={palette.accent} style={styles.loader} />}
      </View>

      <View style={styles.sectionHeader}>
        <Text style={styles.sectionTitle}>AI forecast</Text>
        <Text style={styles.sectionCaption}>Walk-forward model evaluation</Text>
      </View>
      <View style={styles.card}>
        <Text style={styles.label}>Horizon (trading days)</Text>
        <View style={styles.forecastRow}>
          <TextInput
            accessibilityLabel="Forecast horizon in trading days"
            keyboardType="number-pad"
            maxLength={2}
            onChangeText={setHorizon}
            style={styles.horizonInput}
            value={horizon}
          />
          <Pressable
            accessibilityRole="button"
            disabled={forecasting || loading}
            onPress={() => void runForecast()}
            style={[styles.primaryButton, (forecasting || loading) && styles.disabledButton]}>
            {forecasting ? (
              <ActivityIndicator color="#fff" />
            ) : (
              <Text style={styles.primaryButtonText}>Run forecast</Text>
            )}
          </Pressable>
        </View>
        {forecast && (
          <View style={styles.result}>
            <Text style={styles.label}>
              {forecast.horizon}-day estimate · {forecast.method}
            </Text>
            <Text style={styles.resultPrice}>
              {formatPrice(forecast.future_price, symbol)}
            </Text>
            <View style={styles.row}>
              <Text style={styles.label}>Model MAE</Text>
              <Text style={styles.value}>{formatPrice(forecast.model_mae, symbol)}</Text>
            </View>
            <View style={styles.row}>
              <Text style={styles.label}>Baseline MAE</Text>
              <Text style={styles.value}>{formatPrice(forecast.baseline_mae, symbol)}</Text>
            </View>
            <Text style={styles.note}>
              Estimates are historical model outputs, not investment advice.
            </Text>
          </View>
        )}
      </View>
      {!!error && <Text accessibilityRole="alert" style={styles.error}>{error}</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: palette.background },
  content: { padding: 20, paddingTop: 28, paddingBottom: 44 },
  eyebrow: { color: palette.accent, fontSize: 11, fontWeight: '800', letterSpacing: 1.5 },
  title: { color: palette.ink, fontSize: 29, fontWeight: '800', marginTop: 8 },
  subtitle: { color: palette.muted, fontSize: 14, marginTop: 6 },
  symbolList: { gap: 8, paddingVertical: 20 },
  symbolChip: { backgroundColor: palette.card, borderColor: palette.border, borderRadius: 18, borderWidth: 1, paddingHorizontal: 14, paddingVertical: 9 },
  symbolChipActive: { backgroundColor: palette.accent, borderColor: palette.accent },
  symbolText: { color: palette.muted, fontSize: 12, fontWeight: '700' },
  symbolTextActive: { color: '#fff' },
  card: { backgroundColor: palette.card, borderColor: palette.border, borderRadius: 18, borderWidth: 1, padding: 18 },
  company: { color: palette.muted, fontSize: 13, fontWeight: '600' },
  price: { color: palette.ink, fontSize: 34, fontWeight: '800', marginTop: 9 },
  change: { color: palette.green, fontSize: 13, fontWeight: '600', marginTop: 6 },
  changeDown: { color: '#c34a53' },
  divider: { backgroundColor: palette.border, height: 1, marginVertical: 16 },
  row: { alignItems: 'center', flexDirection: 'row', justifyContent: 'space-between', marginTop: 10 },
  label: { color: palette.muted, fontSize: 13 },
  value: { color: palette.ink, fontSize: 13, fontWeight: '700' },
  loader: { marginTop: 16 },
  sectionHeader: { marginBottom: 12, marginTop: 26 },
  sectionTitle: { color: palette.ink, fontSize: 19, fontWeight: '800' },
  sectionCaption: { color: palette.muted, fontSize: 12, marginTop: 4 },
  forecastRow: { alignItems: 'center', flexDirection: 'row', gap: 12, marginTop: 10 },
  horizonInput: { backgroundColor: '#f7f8fc', borderColor: palette.border, borderRadius: 11, borderWidth: 1, color: palette.ink, fontSize: 16, paddingHorizontal: 14, paddingVertical: 11, width: 76 },
  primaryButton: { alignItems: 'center', backgroundColor: palette.accent, borderRadius: 11, flex: 1, justifyContent: 'center', minHeight: 46, paddingHorizontal: 12 },
  disabledButton: { opacity: 0.6 },
  primaryButtonText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  result: { borderTopColor: palette.border, borderTopWidth: 1, marginTop: 18, paddingTop: 16 },
  resultPrice: { color: palette.ink, fontSize: 28, fontWeight: '800', marginTop: 6 },
  note: { color: palette.muted, fontSize: 11, lineHeight: 16, marginTop: 16 },
  error: { color: '#b42332', fontSize: 13, marginTop: 14 },
});
