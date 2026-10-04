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

Release, laufender Image-Digest, native Kopplung und gespeicherte Freigabe werden nach dem
Rollout hier mit tatsächlichen Ergebnissen ergänzt. Die bestehende Preview 2 beweist diesen Ablauf nicht.

## Offene Grenzen

- Reale Push-Zustellung benötigt ein Push-Projekt und APNs/FCM-Einrichtung; Vordergrund-Polling funktioniert unabhängig davon.
- Kein signiertes iOS-IPA/TestFlight, kein Play-Store-Release. Android-Vorschau ist debug-signiert.
- Keine echte REWE-Bestellung; der bestehende REWE-Dienst bleibt opt-in.
- Keine Plattformattestierung oder serververifizierte Biometrie.
- Native Build-Abhängigkeiten: 29 Auditmeldungen (10 moderate, 19 high) im aufgelösten SDK-57-Stand; kein erzwungenes inkompatibles Downgrade.
