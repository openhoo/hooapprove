import React, { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, AppState, Platform, Pressable, RefreshControl, ScrollView, Switch, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { StatusBar } from 'expo-status-bar';
import * as LocalAuthentication from 'expo-local-authentication';
import * as Haptics from 'expo-haptics';
import * as Notifications from 'expo-notifications';
import * as Device from 'expo-device';
import * as SecureStore from 'expo-secure-store';
import Constants from 'expo-constants';
import { api, getConnections, reconcile, unlink, Connection } from '../api';
import { router } from 'expo-router';
import { Approval } from '../types';
import { ApprovalCard } from '../ApprovalCard';
import { C, s } from '../theme';

Notifications.setNotificationHandler({ handleNotification: async () => ({ shouldPlaySound: true, shouldSetBadge: false, shouldShowBanner: true, shouldShowList: true }) });

function Main() {
  const [connections, setConnections] = useState<Connection[]>([]);
  const [demo, setDemo] = useState(false);
  const [items, setItems] = useState<(Approval & { deviceId: string })[]>([]);
  const [history, setHistory] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const decisionLock = useRef(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [settings, setSettings] = useState(false);
  const [biometrics, setBiometrics] = useState(false);
  const [biometricsAvailable, setBiometricsAvailable] = useState(false);
  const active = useRef(true);
  const connectionEpoch = useRef(0);

  async function reload() {
    const epoch = connectionEpoch.current;
    try {
      const linked = await getConnections();
      if (epoch !== connectionEpoch.current) return;
      setConnections(linked);
      const loaded: (Approval & { deviceId: string })[] = [];
      let failed = false;
      for (const connection of linked) {
        try {
          const me = await reconcile(connection);
          const requests = await api('/api/requests', undefined, 'GET', connection.device_id);
          setDemo(me.demo);
          loaded.push(...requests.map((item: Approval) => ({ ...item, deviceId: connection.device_id })));
        } catch { failed = true; }
      }
      if (epoch !== connectionEpoch.current) return;
      setItems(loaded.sort((a, b) => b.created - a.created));
      if (failed) setError('Eine Verbindung ist nicht erreichbar oder wurde aufgehoben. Prüfe deine Verbindung und aktualisiere.');
    } catch { setError('Der geschützte Gerätespeicher ist nicht verfügbar.'); }
  }

  useEffect(() => {
    (async () => {
      try {
        setBiometrics(await SecureStore.getItemAsync('hooapprove.biometric') === '1');
        setBiometricsAvailable(await LocalAuthentication.hasHardwareAsync() && await LocalAuthentication.isEnrolledAsync());
        await reload();
      } catch { setError('Der geschützte Gerätespeicher ist nicht verfügbar.'); }
      finally { setInitializing(false); }
    })();
    const timer = setInterval(() => { if (active.current && !decisionLock.current) void reload(); }, 10000);
    const listener = AppState.addEventListener('change', state => { active.current = state === 'active'; if (active.current) void reload(); });
    const received = Notifications.addNotificationReceivedListener(() => { void reload(); });
    const tapped = Notifications.addNotificationResponseReceivedListener(() => { setHistory(false); setSettings(false); void reload(); });
    return () => { clearInterval(timer); listener.remove(); received.remove(); tapped.remove(); };
  }, []);
  async function decide(item: Approval & { deviceId?: string }, decision: 'approve' | 'reject') {
    if (decisionLock.current) return;
    decisionLock.current = true; setBusy(true); setError(''); setNotice('');
    try {
      if (decision === 'approve' && biometrics) {
        const result = await LocalAuthentication.authenticateAsync({ promptMessage: 'Aktion freigeben', cancelLabel: 'Abbrechen', disableDeviceFallback: true, biometricsSecurityLevel: 'strong' });
        if (!result.success) return;
      }
      await api(`/api/requests/${item.id}/decision`, { decision, digest: item.digest }, 'POST', item.deviceId);
      void Haptics.notificationAsync(decision === 'approve' ? Haptics.NotificationFeedbackType.Success : Haptics.NotificationFeedbackType.Warning);
      setNotice(decision === 'approve' ? 'Freigegeben.' : 'Abgelehnt.');
      await reload();
    } catch (e) {
      setError((e as Error).message === 'conflict' ? 'Diese Anfrage ist nicht mehr verfügbar. Bitte aktualisieren.' : 'Die Entscheidung konnte nicht bestätigt werden. Aktualisiere den Status, bevor du es erneut versuchst.');
      await reload();
    } finally { decisionLock.current = false; setBusy(false); }
  }
  async function enablePush() {
    try {
      if (!Device.isDevice) return Alert.alert('Echtes Gerät erforderlich', 'Push-Benachrichtigungen werden auf einem Handy eingerichtet.');
      const projectId = Constants.expoConfig?.extra?.eas?.projectId || Constants.easConfig?.projectId;
      if (!projectId) return Alert.alert('Noch nicht eingerichtet', 'Benachrichtigungen sind zurzeit nicht verfügbar.');
      if (Platform.OS === 'android') await Notifications.setNotificationChannelAsync('default', { name: 'Freigabe-Anfragen', importance: Notifications.AndroidImportance.HIGH });
      const permission = await Notifications.requestPermissionsAsync();
      if (permission.status !== 'granted') return Alert.alert('Benachrichtigungen deaktiviert', 'Du kannst offene Anfragen weiterhin in der App sehen.');
      const token = (await Notifications.getExpoPushTokenAsync({ projectId })).data;
      for (const connection of connections) await api('/api/native-devices', { token }, 'POST', connection.device_id); await SecureStore.setItemAsync('hooapprove.push', token); setNotice('Benachrichtigungen sind aktiviert.');
    } catch { setError('Benachrichtigungen konnten nicht eingerichtet werden. Bitte versuche es erneut.'); }
  }
  function disconnect(connection: Connection) {
    Alert.alert('Verbindung aufheben?', `Du erhältst keine weiteren Anfragen von ${connection.label} auf diesem Handy.`, [
      { text: 'Abbrechen', style: 'cancel' }, { text: 'Verbindung aufheben', style: 'destructive', onPress: async () => {
        try { await unlink(connection.device_id); connectionEpoch.current++; await reload(); }
        catch { setError('Die Verbindung konnte nicht aufgehoben werden. Bitte aktualisieren und erneut versuchen.'); }
      } },
    ]);
  }
  const pending = items.filter(item => item.status === 'pending');
  const visible = items.filter(item => history ? item.status !== 'pending' : item.status === 'pending');
  if (initializing) return <SafeAreaView style={s.screen}><ActivityIndicator color={C.green} style={{ flex: 1 }} /></SafeAreaView>;
  return <SafeAreaView style={s.screen} edges={['top', 'left', 'right']}>
    <StatusBar style="dark" />
    <View style={s.header}><Text style={s.brandText}>HooApprove</Text>
      {connections.length > 0 && <Pressable onPress={() => setSettings(!settings)} accessibilityRole="button" accessibilityLabel={settings ? "Zurück zu den Anfragen" : "Einstellungen"} style={s.avatar}><Text style={s.avatarText}>{settings ? '×' : '⚙'}</Text></Pressable>}</View>
    <ScrollView contentContainerStyle={s.content} refreshControl={connections.length ? <RefreshControl refreshing={refreshing} tintColor={C.green} onRefresh={async () => { setRefreshing(true); setError(''); await reload(); setRefreshing(false); }} /> : undefined}>
      {demo && <View style={s.demo}><Text style={s.demoText}>Demo · keine echte Bestellung</Text></View>}
      {error ? <View style={s.error} accessibilityRole="alert"><Text style={s.errorText}>{error}</Text></View> : null}
      {notice ? <View style={s.notice} accessibilityLiveRegion="polite"><Text style={s.noticeText}>{notice}</Text></View> : null}
      {!connections.length ? <View style={s.onboarding}>
        <Text style={s.headline}>Dienst verbinden</Text>
        <Text style={s.introText}>Scanne den QR-Code deines Dienstes.</Text>
        <Pressable style={s.primary} onPress={() => router.push('/pair')} accessibilityRole="button"><Text style={s.primaryText}>Verbinden</Text></Pressable>
      </View>
      : settings ? <View><Text style={s.headline}>Einstellungen</Text><Text style={s.sectionTitle}>Verbindungen</Text>
        {connections.map(connection => <View key={connection.device_id} style={s.connection}>
          <Text style={s.settingText}>{connection.label}</Text>
          <Text style={s.hint}>{connection.service}{connection.pending ? ' · Wird geprüft' : ''}</Text>
          <Pressable onPress={() => disconnect(connection)} style={s.reject} accessibilityRole="button" accessibilityLabel={`${connection.label} trennen`}><Text style={s.rejectText}>Trennen</Text></Pressable>
        </View>)}
        <Pressable onPress={() => router.push('/pair')} style={s.settingButton} accessibilityRole="button"><Text style={s.settingText}>Dienst hinzufügen</Text></Pressable>
        <Pressable onPress={enablePush} style={s.settingButton} accessibilityRole="button"><Text style={s.settingText}>Benachrichtigungen</Text></Pressable>
        <View style={s.settingButton}><View style={{ flex: 1 }}><Text style={s.settingText}>Biometrie</Text><Text style={s.hint}>{biometricsAvailable ? 'Face ID oder Fingerabdruck' : 'Nicht eingerichtet'}</Text></View>
          <Switch value={biometrics} disabled={!biometricsAvailable} trackColor={{ true: C.green }} onValueChange={async value => {
            try { if (value) { const result = await LocalAuthentication.authenticateAsync({ promptMessage: 'Biometrie aktivieren', disableDeviceFallback: true, biometricsSecurityLevel: 'strong' }); if (!result.success) return; }
              await SecureStore.setItemAsync('hooapprove.biometric', value ? '1' : '0'); setBiometrics(value);
            } catch { setError('Biometrie konnte nicht eingerichtet werden.'); }
          }} /></View></View>
      : <><View style={s.tabs}><Pressable style={[s.tab, !history && s.tabActive]} onPress={() => setHistory(false)} accessibilityRole="tab" accessibilityState={{ selected: !history }}><Text style={[s.tabText, !history && s.tabTextActive]}>Offen</Text>{pending.length > 0 && <Text style={s.countText}>{pending.length}</Text>}</Pressable>
          <Pressable style={[s.tab, history && s.tabActive]} onPress={() => setHistory(true)} accessibilityRole="tab" accessibilityState={{ selected: history }}><Text style={[s.tabText, history && s.tabTextActive]}>Verlauf</Text></Pressable></View>
        {demo && <Pressable accessibilityRole="button" style={s.demoButton} onPress={async () => { try { await api('/api/demo/request', {}); setHistory(false); await reload(); } catch { setError('Beispielanfrage konnte nicht erstellt werden.'); } }}><Text style={s.meta}>＋ Beispielanfrage erstellen</Text></Pressable>}
        {visible.length ? visible.map(item => <ApprovalCard key={item.id} item={item} busy={busy} decide={decide} />) : <View style={s.empty}>
          {!history && <View style={s.emptyIcon}><Text style={s.emptyCheck}>✓</Text></View>}
          <Text style={s.emptyTitle}>{history ? 'Noch keine Entscheidungen' : 'Keine offenen Anfragen'}</Text>
        </View>}</>}

    </ScrollView>
  </SafeAreaView>;
}
export default Main;
