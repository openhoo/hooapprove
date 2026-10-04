import React, { useRef, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, Text, TextInput, View } from 'react-native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { router } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LOCAL_DEMO, demoTicket, pair, previewPairing } from '../api';
import { C, s } from '../theme';

export default function Pairing({ initialCode = '' }: { initialCode?: string }) {
  const [code, setCode] = useState(initialCode);
  const [camera, setCamera] = useState(false);
  const [permission, requestPermission] = useCameraPermissions();
  const [preview, setPreview] = useState<{ service: string; label: string; expires: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const locked = useRef(false);
  async function inspect(value: string) {
    if (locked.current) return;
    locked.current = true; setBusy(true); setError(''); setCamera(false);
    try { setPreview(await previewPairing(value)); setCode(value); }
    catch { setError('Dieser Kopplungscode ist ungültig, abgelaufen oder nicht erreichbar. Fordere einen neuen Code beim Dienst an.'); }
    finally { locked.current = false; setBusy(false); }
  }
  async function confirm() {
    if (!preview || locked.current) return;
    locked.current = true; setBusy(true); setError('');
    try { await pair(code, preview); setCode(''); router.replace('/'); }
    catch { setError('Kopplung konnte nicht bestätigt werden. Öffne die Übersicht, um eine möglicherweise bereits verbundene Kopplung zu prüfen.'); setPreview(null); }
    finally { locked.current = false; setBusy(false); }
  }
  return <SafeAreaView style={s.screen}><ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
    <Pressable onPress={() => router.replace('/')} accessibilityRole="button" style={s.settingButton}><Text style={s.settingText}>← Zurück</Text></Pressable>
    <View style={s.pairingContent}><Text style={s.headline}>{preview ? 'Verbinden?' : 'Dienst verbinden'}</Text>
    {!preview && <Text style={s.introText}>QR-Code scannen oder Code eingeben.</Text>}</View>
    {error ? <View style={s.error} accessibilityRole="alert"><Text style={s.errorText}>{error}</Text></View> : null}
    <View style={s.pairingForm}>{preview ? <>
      <Text style={s.cardTitle}>{preview.label}</Text><Text style={s.summary}>{preview.service}</Text><Text style={s.summary}>Dieser Dienst kann dir Freigabeanfragen senden.</Text>
      <Pressable style={[s.primary, busy && s.disabled]} disabled={busy} onPress={confirm} accessibilityRole="button"><Text style={s.primaryText}>{busy ? 'Wird verbunden …' : 'Verbinden'}</Text></Pressable>
      <Pressable disabled={busy} onPress={() => { setPreview(null); setCode(''); }} style={s.reject}><Text style={s.rejectText}>Abbrechen</Text></Pressable>
    </> : <>
      {camera && permission?.granted ? <CameraView style={s.camera} facing="back" barcodeScannerSettings={{ barcodeTypes: ['qr'] }} onBarcodeScanned={event => { void inspect(event.data); }} /> : <Pressable style={s.primary} disabled={busy} accessibilityRole="button" onPress={async () => { const result = permission?.granted ? permission : await requestPermission(); if (result.granted) setCamera(true); else setError('Kamerazugriff ist deaktiviert. Du kannst den Code unten einfügen.'); }}><Text style={s.primaryText}>QR-Code scannen</Text></Pressable>}
      <Text style={s.sectionTitle}>Code eingeben</Text><TextInput value={code} onChangeText={setCode} secureTextEntry autoCapitalize="none" autoCorrect={false} multiline={false} accessibilityLabel="Kopplungscode" placeholder="Kopplungscode" placeholderTextColor={C.muted} style={s.input} />
      <Pressable style={[s.settingButton, (busy || !code.trim()) && s.disabled]} disabled={busy || !code.trim()} accessibilityRole="button" onPress={() => { void inspect(code); }}><Text style={s.settingText}>Code prüfen</Text></Pressable>
      {LOCAL_DEMO && <Pressable style={s.settingButton} disabled={busy} onPress={async () => { try { const value = await demoTicket(); await inspect(value.ticket); } catch { setError('Die Demo ist bereits gekoppelt.'); } }}><Text style={s.settingText}>Demo-Dienst koppeln</Text></Pressable>}
      {busy && <ActivityIndicator color={C.green} />}
    </>}</View><Text style={s.hint}>Nur Codes aus deinem eigenen Dienst verwenden.</Text>
  </ScrollView></SafeAreaView>;
}
