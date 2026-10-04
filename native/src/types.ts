export type Approval = {
  id: string; service: string; title: string; summary: string; digest: string;
  details: { label: string; value: string }[]; expires: number; created: number;
  status: 'pending' | 'approved' | 'executing' | 'completed' | 'rejected' | 'expired' | 'cancelled' | 'failed' | 'uncertain';
};
export type Event = { event: string; occurred: number };
export const statusLabels: Record<Approval['status'], string> = {
  pending: 'Wartet auf dich', approved: 'Freigegeben', executing: 'Wird ausgeführt',
  completed: 'Abgeschlossen', rejected: 'Abgelehnt', expired: 'Abgelaufen',
  cancelled: 'Zurückgezogen', failed: 'Fehlgeschlagen', uncertain: 'Ergebnis unklar',
};
export const eventLabels: Record<string, string> = {
  requested: 'Anfrage eingegangen', approved: 'Von dir freigegeben', rejected: 'Von dir abgelehnt',
  claimed: 'Ausführung gestartet', completed: 'Ausführung abgeschlossen', failed: 'Ausführung fehlgeschlagen',
  uncertain: 'Ergebnis muss geprüft werden', expired: 'Freigabe abgelaufen', cancelled: 'Anfrage zurückgezogen',
};
