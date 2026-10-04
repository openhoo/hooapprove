import React, { useEffect, useMemo, useState } from 'react';
import { Alert, Animated, PanResponder, Pressable, Text, View } from 'react-native';
import { api } from './api';
import { Approval, Event, eventLabels, statusLabels } from './types';
import { s } from './theme';

function Slide({ disabled, onApprove }: { disabled: boolean; onApprove: () => void }) {
  const [position] = useState(() => new Animated.Value(0));
  const [width, setWidth] = useState(0);
  const responder = useMemo(() => {
    const reset = () => Animated.spring(position, { toValue: 0, useNativeDriver: true }).start();
    return PanResponder.create({
      onStartShouldSetPanResponder: () => !disabled,
      onMoveShouldSetPanResponder: (_, g) => Math.abs(g.dx) > 8 && Math.abs(g.dx) > Math.abs(g.dy),
      onPanResponderMove: (_, g) => position.setValue(Math.max(0, Math.min(width - 64, g.dx))),
      onPanResponderRelease: (_, g) => {
        if (width > 100 && g.dx >= (width - 64) * .94 && !disabled) onApprove();
        reset();
      }, onPanResponderTerminate: reset,
    });
  }, [disabled, onApprove, position, width]);
  return <View style={[s.slide, disabled && s.disabled]} onLayout={e => { setWidth(e.nativeEvent.layout.width); }}
    accessible accessibilityRole="button" accessibilityLabel="Diese Aktion freigeben"
    accessibilityHint="Doppeltippen öffnet eine ausdrückliche Bestätigung." accessibilityState={{ disabled }}
    accessibilityActions={[{ name: 'activate', label: 'Freigeben' }]} onAccessibilityAction={e => {
      if (e.nativeEvent.actionName === 'activate' && !disabled) Alert.alert('Aktion freigeben?', 'Du gibst die angezeigte Aktion einmal frei.', [
        { text: 'Abbrechen', style: 'cancel' }, { text: 'Freigeben', onPress: onApprove },
      ]);
    }}><Text style={s.slideText}>Zur Freigabe schieben</Text>
    <Animated.View {...responder.panHandlers} style={[s.thumb, { transform: [{ translateX: position }] }]}><Text style={s.thumbText}>→</Text></Animated.View>
  </View>;
}
export function ApprovalCard({ item, busy, decide }: { item: Approval; busy: boolean; decide: (item: Approval, decision: 'approve' | 'reject') => void }) {
  const [events, setEvents] = useState<Event[] | null>(null);
  const pending = item.status === 'pending';
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => { const timer = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(timer); }, []);
  return <View style={s.card}>
    <View style={s.rowBetween}><View style={s.service}><View style={s.serviceIcon}><Text style={s.serviceGlyph}>↗</Text></View><Text style={s.serviceText}>{item.service}</Text></View>
      <View style={[s.badge, !pending && s.badgeDone]}><Text style={s.badgeText}>{statusLabels[item.status]}</Text></View></View>
    <Text style={s.cardTitle}>{item.title}</Text><Text style={s.summary}>{item.summary}</Text>
    <View style={s.details}>{item.details.map((detail, i) => <View key={i} style={s.detail}><Text style={s.detailLabel}>{detail.label}</Text><Text style={s.detailValue}>{detail.value}</Text></View>)}</View>
    <View style={s.rowBetween}><Text style={s.meta}>Aktion {item.digest.slice(0, 12)}</Text><Text style={s.meta}>{pending ? `Noch ${Math.max(0, Math.ceil((item.expires - now / 1000) / 60))} Min.` : statusLabels[item.status]}</Text></View>
    {pending ? <><Slide disabled={busy} onApprove={() => decide(item, 'approve')} /><Text style={s.hint}>Nur die oben gezeigte Aktion wird freigegeben.</Text>
      <Pressable disabled={busy} accessibilityRole="button" onPress={() => decide(item, 'reject')} style={s.reject}><Text style={s.rejectText}>Anfrage ablehnen</Text></Pressable></>
      : <Pressable accessibilityRole="button" style={s.eventButton} onPress={async () => {
        try { setEvents(await api(`/api/requests/${item.id}/events`)); } catch { Alert.alert('Verlauf nicht verfügbar', 'Bitte versuche es erneut.'); }
      }}><Text style={s.meta}>{events ? 'Entscheidungsverlauf' : 'Entscheidungsverlauf anzeigen ↓'}</Text>
        {events?.map((event, i) => <Text key={i} style={s.event}>{new Date(event.occurred * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' })} · {eventLabels[event.event] || event.event}</Text>)}</Pressable>}
  </View>;
}
