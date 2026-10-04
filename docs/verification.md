# Kontofreie Gerätekopplung · 4. Oktober 2026

Diese Abnahme ersetzt den verworfenen Login-Ablauf aus Preview 1/2.
Die frühere Veröffentlichung ist in `verification-login-preview.md` als historischer Nachweis erhalten.

## Lokal verifiziert

- 39 Diensttests: private Erstkopplung, Besitznachweis, Ablauf, einmalige und parallele Ticket-Einlösung.
- Gerät kann nicht durch den Executor ausgetauscht werden; andere offene Tickets werden invalidiert.
- Signaturen binden Methode, Pfad und Body; veraltete Nachweise, falsche Schlüssel und Nonce-Replay werden abgewiesen.
- Widerruf sperrt den alten Schlüssel. Dienst und Empfänger sind gemeinsam gebunden.
- Produktionsstart mit HTTPS ohne OIDC, Sitzungsschlüssel oder Login. Alte Login-Routen sind entfernt.
- Acht parallele Claims ergeben genau eine Ausführung; geänderte Details, Ablauf, Ablehnung und unklare Ergebnisse bleiben gesperrt.
- Echter HTTP-Dienst + tatsächlicher Shooping-Adapter, synthetischer REWE-Upstream: vor Freigabe keine Bestellung, danach genau eine, Abschluss gespeichert und Replay gesperrt.
- Native TypeScript- und Lint-Prüfungen bestanden; iOS-/Android-Bundle-Prüfung wird im Release-Gate wiederholt.

## Veröffentlichung und Geräteabnahme

- Veröffentlichte Vorschau: [v0.1.0-preview.3](https://github.com/openhoo/hooapprove/releases/tag/v0.1.0-preview.3), PR #5 (`b9882cd`), Checks und Release-Workflow erfolgreich.
- Android-ARM64-APK: SHA-256 `0d6eca12027f29749cffd83fcaf4aed68b1340eaa6be5552ef0071dcbb81d8b2`; Signatur geprüft und auf Android-15-ARM64-Emulator installiert.
- Produktion: `https://approve.openhoo.dev`, GitOps-PR #201 (`66ace78`); Argo CD Synced/Healthy, zuletzt auf Revision `7453883` gelesen; Image `ghcr.io/openhoo/hooapprove@sha256:1c1c773c911280d5f03f8b4a5ff8d1041a01af8164987a16f123e9c1aa0c102e`.
- Nach dem Test-Widerruf wurde das temporäre `native-proof`-Dienstkonto aus dem Secret Store entfernt, die externe Secret-Synchronisierung erzwungen und der App-Pod neu gestartet. Live-Konfiguration enthält nur `services.rewe`; keine Identitäts- oder Sitzungsschlüssel. `/healthz` meldet `production`.
- Konto- und loginfreie native Erstkopplung, private Codeeingabe, explizite Bestätigung, signierte Inbox-Abfrage und signierte Ablehnung wurden mit dem Produktionsdienst geprüft. `/api/me` und Inbox funktionieren mit dem lokalen Geräteschlüssel.
- Testaktion `e9d7a9dd-607d-42ce-be48-0a13fb37e6ac` wurde in der App abgelehnt; Live-Datenbank zeigt `requested → rejected`. Die aktive Gerätekopplung wurde danach in der App widerrufen und serverseitig als widerrufen gelesen. Kein REWE-Zugriff und keine Bestellung.
- Echter SQLite-Backupjob `pairing-after-20261004` erfolgreich. Eine isolierte Wiederherstellung (`daily-20261004T183920Z.db`) bestätigte Datenbankintegrität, den abgelehnten Testverlauf, widerrufenes Gerät, eine erhaltene abgeschlossene Anfrage und nur die Tabellen `requests`, `events`, `pairings`, `paired_devices`, `device_nonces` (plus SQLite-Sequenz).
- Ein emulatorseitiger Touch-Klick funktioniert; Drag-Ereignisse ließen sich über den verwendeten macOS-Mirror nicht zuverlässig übertragen. Der native Schieberegler ist daher noch nicht durch eine echte Hardware-Touchgeste abgenommen. Die signierte Ablehnung und Bestätigungsdialoge bleiben benutzbar; kein synthetischer Serverentscheid wurde als App-Freigabe ausgegeben.
- Screenshots: `output/native-no-login.png`, `output/native-pairing-preview.png`, `output/native-rejected-action.png`.

## Offene Grenzen

- Reale Push-Zustellung benötigt ein Push-Projekt und APNs/FCM-Einrichtung; Vordergrund-Polling funktioniert unabhängig davon.
- Kein signiertes iOS-IPA/TestFlight, kein Play-Store-Release. Android-Vorschau ist debug-signiert.
- Keine echte REWE-Bestellung; der bestehende REWE-Dienst bleibt opt-in.
- Keine Plattformattestierung oder serververifizierte Biometrie.
- Native Build-Abhängigkeiten: 29 Auditmeldungen (10 moderate, 19 high) im aufgelösten SDK-57-Stand; kein erzwungenes inkompatibles Downgrade.
