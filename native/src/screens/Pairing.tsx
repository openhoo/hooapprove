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
    <Pressable onPress={() => router.replace('/')} accessibilityRole="button" style={s.settingButton}><Text style={s.settingText}>← Zur Übersicht</Text></Pressable>
    <Text style={s.eyebrow}>EINMAL VERBINDEN</Text><Text style={s.headline}>Dein Handy.</Text><Text style={s.headlineItalic}>Deine Freigabe.</Text>
    <Text style={s.introText}>Scanne den Kopplungscode deines Dienstes. Du brauchst kein Konto und keine Anmeldung.</Text>
    {error ? <View style={s.error} accessibilityRole="alert"><Text style={s.errorText}>{error}</Text></View> : null}
    <View style={s.card}>{preview ? <>
      <Text style={s.eyebrow}>VERBINDUNG PRÜFEN</Text><Text style={s.cardTitle}>{preview.label}</Text><Text style={s.summary}>Dienst: {preview.service}{'\n\n'}Dieser Dienst darf Aktionsanfragen an dein Handy schicken. Jede einzelne Freigabe entscheidest du selbst.</Text>
      <Pressable style={[s.primary, busy && s.disabled]} disabled={busy} onPress={confirm} accessibilityRole="button"><Text style={s.primaryText}>{busy ? 'Wird verbunden …' : 'Diesen Dienst verbinden'}</Text></Pressable>
      <Pressable disabled={busy} onPress={() => { setPreview(null); setCode(''); }} style={s.reject}><Text style={s.rejectText}>Abbrechen</Text></Pressable>
    </> : <>
      {camera && permission?.granted ? <CameraView style={{ height: 300, borderRadius: 16 }} facing="back" barcodeScannerSettings={{ barcodeTypes: ['qr'] }} onBarcodeScanned={event => { void inspect(event.data); }} /> : <Pressable style={s.primary} disabled={busy} accessibilityRole="button" onPress={async () => { const result = permission?.granted ? permission : await requestPermission(); if (result.granted) setCamera(true); else setError('Kamerazugriff ist deaktiviert. Du kannst den Code unten einfügen.'); }}><Text style={s.primaryText}>QR-Code scannen</Text><Text style={s.primaryArrow}>↗</Text></Pressable>}
      <Text style={s.hint}>Oder Kopplungscode einfügen</Text><TextInput value={code} onChangeText={setCode} secureTextEntry autoCapitalize="none" autoCorrect={false} multiline={false} accessibilityLabel="Kopplungscode" placeholder="Code oder Kopplungslink" style={{ borderWidth: 1, borderColor: C.green, borderRadius: 12, padding: 14, marginVertical: 12, color: C.green }} />
      <Pressable style={s.settingButton} disabled={busy || !code.trim()} accessibilityRole="button" onPress={() => { void inspect(code); }}><Text style={s.settingText}>Verbindung prüfen →</Text></Pressable>
      {LOCAL_DEMO && <Pressable style={s.settingButton} disabled={busy} onPress={async () => { try { const value = await demoTicket(); await inspect(value.ticket); } catch { setError('Die Demo ist bereits gekoppelt.'); } }}><Text style={s.settingText}>Demo-Dienst koppeln</Text></Pressable>}
      {busy && <ActivityIndicator color={C.green} />}
    </>}</View><Text style={s.hint}>Nutze nur einen Code aus deinem eigenen Dienst. Der Kopplungscode gehört dir und darf nicht an den Agenten weitergegeben werden.</Text>
  </ScrollView></SafeAreaView>;
}
