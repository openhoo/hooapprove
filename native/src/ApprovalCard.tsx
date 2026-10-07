import React, { useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Alert, Animated, PanResponder, Pressable, Text, View } from 'react-native';
import { api } from './api';
import { Approval, Event, eventLabels, statusLabels } from './types';
import { s } from './theme';
import { completesApprovalDrag } from './approvalGesture';

function createSlideResponder(position: Animated.Value, width: number, getLatest: () => { disabled: boolean; onApprove: () => void }) {
    let started = 0;
    let valid = false;
    let approve = () => {};
    const reset = () => { valid = false; Animated.spring(position, { toValue: 0, useNativeDriver: true }).start(); };
    return PanResponder.create({
      onStartShouldSetPanResponder: () => !getLatest().disabled,
      onMoveShouldSetPanResponder: (_, g) => !getLatest().disabled && g.dx > 8 && Math.abs(g.dx) > Math.abs(g.dy),
      onPanResponderGrant: (_, g) => { position.stopAnimation(); position.setValue(0); started = Date.now(); valid = g.numberActiveTouches === 1; approve = getLatest().onApprove; },
      onPanResponderMove: (_, g) => {
        if (getLatest().disabled || g.numberActiveTouches !== 1 || Math.abs(g.dy) > 28) { valid = false; position.setValue(0); return; }
        if (valid) position.setValue(Math.max(0, Math.min(width - 60, g.dx)));
      },
      onPanResponderRelease: (_, g) => {
        // numberActiveTouches is zero on release; valid tracks every move and grant.
        const complete = valid && !getLatest().disabled && completesApprovalDrag(width, g.dx, g.dy, 1, Date.now() - started);
        reset();
        if (complete) approve();
      },
      onPanResponderTerminate: reset,
    });
}


function Slide({ disabled, onApprove }: { disabled: boolean; onApprove: () => void }) {
  const [position] = useState(() => new Animated.Value(0));
  const [width, setWidth] = useState(0);
  const latest = useRef({ disabled, onApprove });
  useLayoutEffect(() => { latest.current = { disabled, onApprove }; }, [disabled, onApprove]);
  // The factory stores this getter in event handlers and never calls it during render.
  // eslint-disable-next-line react-hooks/refs
  const responder = useMemo(() => createSlideResponder(position, width, () => latest.current), [position, width, latest]);
  return <View style={[s.slide, disabled && s.disabled]} onLayout={e => { setWidth(e.nativeEvent.layout.width); }}
    accessible accessibilityRole="button" accessibilityLabel="Diese Aktion freigeben"
    accessibilityHint="Doppeltippen öffnet eine ausdrückliche Bestätigung." accessibilityState={{ disabled }} aria-disabled={disabled}
    accessibilityActions={[{ name: 'activate', label: 'Freigeben' }]} onAccessibilityAction={e => {
      if (e.nativeEvent.actionName === 'activate' && !disabled) Alert.alert('Aktion freigeben?', 'Du gibst die angezeigte Aktion einmal frei.', [
        { text: 'Abbrechen', style: 'cancel' }, { text: 'Freigeben', onPress: () => { if (!latest.current.disabled) latest.current.onApprove(); } },
      ]);
    }}><Text style={s.slideText}>Zur Freigabe schieben</Text>
    <Animated.View {...responder.panHandlers} style={[s.thumb, { transform: [{ translateX: position }] }]}><Text style={s.thumbText}>→</Text></Animated.View>
  </View>;
}
export function ApprovalCard({ item, busy, decide }: { item: Approval & { deviceId?: string }; busy: boolean; decide: (item: Approval, decision: 'approve' | 'reject') => void }) {
  const [events, setEvents] = useState<Event[] | null>(null);
  const [loadingEvents, setLoadingEvents] = useState(false);
  const eventLock = useRef(false);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const pending = item.status === 'pending';
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  const expired = item.expires <= now / 1000;
  const disabled = busy || expired;
  return <View style={s.card}>
    <View style={s.rowBetween}><Text style={s.serviceText}>{item.service}</Text>
      <Text style={s.badgeText}>{pending ? "Offen" : statusLabels[item.status]}</Text></View>
    <Text style={s.cardTitle}>{item.title}</Text><Text style={s.summary}>{item.summary}</Text>
    <View style={s.details}>{item.details.map((detail, i) => <View key={i} style={s.detail}><Text style={s.detailLabel}>{detail.label}</Text><Text style={s.detailValue}>{detail.value}</Text></View>)}</View>
    {pending && <Text style={s.meta}>{expired ? 'Abgelaufen · Status wird aktualisiert' : `Gültig für ${Math.ceil((item.expires - now / 1000) / 60)} Min.`}</Text>}
    {pending ? <><Slide key={item.digest} disabled={disabled} onApprove={() => decide(item, 'approve')} />
      <Pressable disabled={disabled} accessibilityState={{ disabled }} accessibilityRole="button" onPress={() => decide(item, 'reject')} style={s.reject}><Text style={s.rejectText}>Ablehnen</Text></Pressable></>
      : <Pressable accessibilityRole="button" style={s.eventButton} disabled={loadingEvents} accessibilityState={{ busy: loadingEvents }} onPress={async () => {
        if (eventLock.current) return;
        if (events) { setEvents(null); return; }
        eventLock.current = true; setLoadingEvents(true);
        try { const loaded = await api(`/api/requests/${item.id}/events`, undefined, 'GET', item.deviceId); if (mounted.current) setEvents(loaded); } catch { if (mounted.current) Alert.alert('Verlauf nicht verfügbar', 'Bitte versuche es erneut.'); }
        finally { eventLock.current = false; if (mounted.current) setLoadingEvents(false); }
      }}><Text style={s.meta}>{loadingEvents ? 'Verlauf wird geladen …' : events ? 'Verlauf ausblenden' : 'Verlauf anzeigen'}</Text>
        {events?.length === 0 && <Text style={s.event}>Keine Ereignisse verfügbar.</Text>}
        {events?.map((event, i) => <Text key={i} style={s.event}>{new Date(event.occurred * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} · {eventLabels[event.event] || event.event}</Text>)}</Pressable>}
  </View>;
}
