# Direkte Anbindung an den vorhandenen REWE-MCP

Arbeitsbaum: `/Users/wakemeup/projects/openhoo/shooping-hooapprove`, Branch `feat/hooapprove`.
Ausgangsrepository: `/Users/wakemeup/Documents/Codex/2026-10-03/i-w/outputs/shooping`.
Basiscommit: `c6d3153`.

Die Anbindung ist optional aktivierbar über `SHOOPING_HOOAPPROVE_CONFIG_FILE`.
Die geschützte Konfiguration enthält den HooApprove-Origin, Dienst-Token, Dienstnamen und die
fest zugeordnete OpenHoo-Subject-ID. Die Datei muss ein privates reguläres File mit Modus 0600 sein.
Zugangsdaten über die vorhandene sichere Secret-Verwaltung provisionieren; keine Werte in MCP-
Argumenten, Shell-Argumenten oder Logs. Beispiel mit Platzhaltern:

```json
{
  "url": "https://approve.openhoo.dev",
  "token": "<protected-service-token>",
  "service": "rewe",
  "subject": "<paired-openhoo-owner-subject>"
}
```

Der Empfänger ist eine Betriebskonfiguration der persönlichen REWE-Instanz, kein Agent-Parameter.
Das REWE-Konto wird zusätzlich durch `appImportSourceHash` an den verifizierten Import gebunden.
Eine andere importierte Sitzung kann die alte Freigabe nicht verwenden.

`rewe_prepare_order` prüft Zahlungs-/Adress-/Terminvoraussetzungen, liest die vorhandene Bestell-
vorschau und erstellt eine fünf Minuten gültige HooApprove-Anfrage. Alle Artikel, der feste
Gesamtpreis, Adresse, Termin, Zahlungsart und verfügbare Vertragsinformationen werden angezeigt.
REWE-Tokens, private Zahlungsdaten und Provider-Redirects werden nicht übertragen.

`rewe_submit_order` wartet standardmäßig bis zu 40 Sekunden auf die Handyentscheidung.
`waitSeconds` ist optional von 0 bis 60 konfigurierbar; der MCP-Client muss eine längere
Tool-Deadline verwenden. Danach liest es unmittelbar vorher die REWE-Bestellvorschau erneut und vergleicht den
vorhandenen Shooping-Digest. Erst danach beansprucht es HooApprove einmalig. Die lokale Datei
`order-approval.json` kann den HooApprove-Modus nicht freischalten. Auch der alte Eigentümer-
Formularweg wird bei aktiviertem HooApprove-Modus blockiert.

Ein abgebrochener MCP-Aufruf zieht während des Wartens die HooApprove-Anfrage zurück und
sendet keine Bestellung. Nach einem Wartetimeout darf der Agent dieselbe noch gültige Anfrage
wieder aufnehmen; er darf keine neue Ersatzbestellung anlegen.

Vor dem REWE-Versand wird der bestehende dauerhafte `order-attempt.json`-Zaun geschrieben.
Ein unklares Resultat blockiert weitere Bestellversuche auch nach Neustart. HooApprove erhält
`completed` oder `uncertain`; Scheitern der Ergebnismeldung löst keine zweite Bestellung aus.
Die bisherigen Zahlungsbestätigungen und die Eigentümerklärung anhand der Bestellhistorie bleiben
erhalten. Die Integration erteilt selbst keine menschliche Freigabe und bestellt im Test nicht bei REWE.

**Upstream-Grenze:** Der vorhandene APK-Vertrag besitzt für den Bestellrequest keine live belegte
atomare Digest-/Versionsbedingung. Die Kontrolle unmittelbar vor Versand schützt Änderungen, die
bei der erneut gelesenen Vorschau sichtbar werden. Gleichzeitige Änderungen durch die REWE-App
zwischen Kontrolle und finalem Request sind ohne Upstream-Versionszaun nicht vollständig auszuschließen.
Gefüllter echter Checkout und abschließende Bestellung sind im Ausgangsprojekt noch nicht live
abgenommen. Dafür benötigt es die konkrete Nutzerfreigabe für Warenkorb, Lieferdetails und Betrag.

Vor Produktionsaktivierung: HooApprove bereitstellen, kontofreie QR-Gerätekopplung auf dem tatsächlichen Handy
prüfen, den korrekten OpenHoo-Subject fest verbinden, Dienst-Secret sicher provisionieren und die
Push-Anfrage tatsächlich empfangen. Keine Konto-/Warenkorb-/Zahlungsänderungen als impliziter Test.
