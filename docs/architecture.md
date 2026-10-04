# Sicherheits- und Integrationsvertrag

## Zustände

```mermaid
stateDiagram-v2
    [*] --> pending
    pending --> approved: gekoppeltes Handy entscheidet
    pending --> rejected: gekoppeltes Handy lehnt ab
    pending --> expired: Ablauf
    pending --> cancelled: ursprünglicher Dienst zieht zurück
    approved --> expired: Ablauf vor Claim
    approved --> cancelled: ursprünglicher Dienst zieht zurück
    approved --> executing: atomarer Claim durch ursprünglichen Dienst
    executing --> completed: bestätigtes Ergebnis
    executing --> failed: sicher bekanntes Scheitern
    executing --> uncertain: möglicher externer Erfolg
```

Kein Endzustand führt automatisch zu einer neuen Genehmigung. Ein hängender `executing`-Vorgang
ist ebenfalls nicht erneut einlösbar. Ablehnen, Ablaufen oder Netzwerkfehler bedeutet niemals „ja“.

## Durchsetzung

1. Der vertrauenswürdige Executor verwendet einen fest konfigurierten Empfänger. Der Agent wählt keinen Subject.
2. Der Executor liest den echten Aktionsstand und erzeugt daraus sowohl Darstellung als auch Payload.
3. Die App zeigt den Ursprungsdienst, den vollständigen Vertrag und einen kurzen Inhaltsfingerabdruck.
4. Nur signierte Anfragen des aktiven, für Dienst und Empfänger gekoppelten Geräts können entscheiden. Dienst-Tokens können es nicht.
5. Der Executor liest vor Ausführung den Aktionsstand erneut. Jede Änderung braucht eine neue Freigabe.
6. Ein Claim prüft Dienst, Digest, Zustand und Ablauf in einer `BEGIN IMMEDIATE`-Transaktion.
7. Das externe System muss eigene Idempotenz-/Versionsbedingungen erzwingen, soweit unterstützt.
8. Ergebnisse werden separat gemeldet; Freigabe bedeutet nicht abgeschlossene Bestellung oder Zahlung.

Eine universelle Freigabe-API kann keine ungeschützte alternative Bestellroute sperren.
Direkte Upstream-Credentials gehören zu einem isolierten Dienstkonto, auf das der Agent keinen
Datei-/Shell-Zugriff besitzt. Wenn der Agent dieselben OS-Rechte wie der Executor hat, kann er
eine reine MCP-Sperre umgehen. Das Deployment muss diese Rollen tatsächlich trennen.

Auch ein manipuliertes vertrauenswürdiges Backend könnte falsche Angaben darstellen oder ohne
Claim bestellen. Der Dienst ist Teil der Vertrauensgrenze. Der Digest schützt Inhaltsbindung und
Wiederverwendung; er ersetzt keine korrekte Ableitung der sichtbaren Angaben.

## Gerätekopplung ohne Konto

Keine Anmeldung, kein Benutzerkonto, kein Auth-Provider. Ein privater Eigentümer-/Operator-Client
erzeugt mit seinem Executor-Zugang ein fünf Minuten gültiges Bootstrap-Ticket. Der Server
speichert nur dessen SHA-256-Hash. Die App prüft Dienst und Verbindungsname und benötigt eine
ausdrückliche Bestätigung; ein Deep Link befüllt lediglich das Eingabefeld.

Das Handy erzeugt einen Ed25519-Seed mit nativer sicherer Zufallsquelle und speichert ihn vor
der Anmeldung des Geräts in SecureStore. Öffentlicher Schlüssel und Besitznachweis binden die
Kopplung. Die Enrollment-Transaktion beansprucht das Ticket einmal und verwirft sämtliche
anderen Tickets desselben Dienstes/Empfängers. Ein Unique-Index verhindert parallele Geräte.
Der Executor kann bei bestehender Kopplung kein Ersatzticket erzeugen. Zusätzliche Dienste
werden separat gekoppelt. Wer bei der Erstkopplung den privaten Code besitzt, kann sich koppeln;
ein kompromittierter Bootstrap-Aussteller ist deshalb Teil der Vertrauensgrenze.

Signierte App-Anfragen binden Gerätekkennung, HTTP-Methode, Pfad, Zeitstempel, Zufallsnonce
und SHA-256 des exakten HTTP-Bodys. Zeittoleranz 60 Sekunden; Nonces werden 120 Sekunden
aufbewahrt und atomar einmal verbraucht. Query-Parameter sind nicht zulässig. Eine Entscheidung
bindet zusätzlich den unveränderlichen Aktionsdigest. Die Entscheidungstransaktion prüft
Gerätewiderruf erneut und prüft sowohl Dienst als auch Empfänger.

Ein verlorener Enrollment-Response wird mit dem bereits gespeicherten Schlüssel über eine
signierte Statusabfrage abgeglichen. Der Schlüssel wird nicht automatisch verworfen.
Verbindung aufheben benötigt eine signierte Geräteanfrage und eine lokale Bestätigung.
Verlorene Geräte benötigen eine ausdrücklich vertrauenswürdige Operator-Wiederherstellung;
eine selbstständige Agenten-Wiederherstellung ist nicht implementiert.

Biometrie ist optional und lokal. Signaturen beweisen den Besitz des Geräteschlüssels,
keine Plattformattestierung oder serverprüfbare biometrische Benutzeranwesenheit.

## Benachrichtigungen und Datenschutz

Push enthält nur „Eine Aktion wartet auf deine Entscheidung“. Details, Adresse, Betrag,
Anmeldedaten und Freigabebefugnisse werden nicht in Lock-Screen-Nachrichten übertragen.
Native Nachrichten laufen über den Expo-Pushdienst; der Dienst erhält Geräte-Push-Tokens und
generische Benachrichtigungstexte. Die Details lädt die App ausschließlich mit signiertem Gerätenachweis aus HooApprove.
Eine Notification-Tap-Aktion öffnet die Inbox; sie bestätigt nichts.

Push hat aktuell weder dauerhafte Outbox noch externe Receipt-Nachverfolgung. Bei fehlgeschlagener
Zustellung bleibt die Anfrage in der Inbox. Gerätetest und Zustellnachweis gehören zur Produktionsabnahme.

Freigaben enthalten private Aktionsdaten. Datenbank, Backups und betriebliches Logging müssen
entsprechend geschützt werden. Keine Token, Kopplungscodes, Signaturen oder private Aktionsdetails loggen;
Uvicorn läuft deshalb ohne Access-Log, und der Reverse Proxy muss dieselbe Regel erhalten.

## Betrieb

Eine Instanz mit SQLite und dauerhaftem Volume. Horizontale Skalierung braucht einen anderen
transaktionalen Store und gemeinsame Geräte-/Notification-Zustände. Ingress muss zusätzlich
Verbindungs-/Ratenlimits und angemessene Timeouts setzen. Die Anwendung begrenzt Request-Bodies.

Wiederherstellungen können Freigabe-Replay verursachen. Ausführung erst wieder aktivieren, nachdem
alle offenen Freigaben verworfen und externe Wirkungen abgeglichen wurden. Bei verlorener Claim-
Antwort findet kein automatischer Versand statt. Bei verlorener Bestellantwort muss der Eigentümer
die Upstream-Historie prüfen; eine neue Freigabe allein ist kein Nachweis, dass vorher nichts geschah.
