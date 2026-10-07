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

## Reduzierte Oberfläche · Preview 4

- Veröffentlicht: [v0.1.0-preview.4](https://github.com/openhoo/hooapprove/releases/tag/v0.1.0-preview.4), UI-PR #8, Quellrevision `4e7540b7a8e0b385d3e04e94930da873b9083bdf`.
- Dienst-, Native- und CodeQL-Checks erfolgreich; Release-Workflow `37227258560` erfolgreich.
- Veröffentlichte ARM64-APK heruntergeladen: alle `SHA256SUMS` geprüft und `SOURCE.txt` mit dem getesteten Commit abgeglichen. APK SHA-256: `167cf193dc33e1273fcfbd10a098511e08307195eeb7188b91e9cd52b478b871`.
- APK-Signatur gültig; Zertifikat stimmt mit Preview 3 überein. Installation mit `adb install -r` erfolgreich, ohne Deinstallation. Start der tatsächlichen Release-APK auf Android-15-ARM64-Emulator visuell geprüft: reduzierte Startansicht, kein Login. Screenshot: `output/release-preview4/start.png`.
- Kopplungsansicht und Anfragekarte vorher in einer separaten Designvorschau geprüft; die Anfragekarte verwendete lokale Beispieldaten. Die Design-Fixture ist nicht Bestandteil des Release-Quellstands.
- Diese UI-Veröffentlichung führt keine neue Produktionskopplung oder REWE-Bestellung aus. Die Backend-Abnahme oben bleibt der Nachweis für den unveränderten Dienst.

## Offene Grenzen

- Reale Push-Zustellung benötigt ein Push-Projekt und APNs/FCM-Einrichtung; Vordergrund-Polling funktioniert unabhängig davon.
- Kein signiertes iOS-IPA/TestFlight, kein Play-Store-Release. Android-Vorschau ist debug-signiert.
- Keine echte REWE-Bestellung; der bestehende REWE-Dienst bleibt opt-in.
- Keine Plattformattestierung oder serververifizierte Biometrie.
- Native Build-Abhängigkeiten: 29 Auditmeldungen (10 moderate, 19 high) im aufgelösten SDK-57-Stand; kein erzwungenes inkompatibles Downgrade.

## Breite Prüfung und Korrekturen · 7. Oktober 2026

Vier Agenten prüften parallel Backend/Sicherheitsgrenze, Native-App, Executor/CLI/Web und
HTTP-/Deployment-Konfiguration. Eine zweite unabhängige Prüfung über die Zuständigkeitsgrenzen
ergänzte die ersten Befunde. Diese Abnahme beschreibt den neuen lokalen Quellstand;
sie ersetzt keinen Nachweis einer veröffentlichten APK oder eines ausgerollten Produktionsimages.

### Behobene Sicherheits- und Zustandsfehler

- Ein degenerierter Ed25519-Schlüssel konnte im ursprünglichen Verifier einen konstanten
  Besitznachweis für beliebige Nachrichten bestehen. Enrollment und bestehende gespeicherte
  Geräteschlüssel müssen jetzt die libsodium-Prüfungen einschließlich Primordnungs-Untergruppe bestehen.
- Inbox, Entscheidung und Verlauf prüfen Gerät, Dienst und Empfänger innerhalb derselben
  Store-Transaktion. Konkurrierende Entscheidungen sowie Claim/Stornierung sind gegenseitig ausgeschlossen.
- Überlange Timestamp-Header werden mit HTTP 401 statt einem internen Fehler abgewiesen;
  ungültige Unicode-Surrogate werden vor Digest-Berechnung und Persistierung zurückgewiesen.
- HTTP-Validierungsfehler geben keine privaten Eingabewerte oder Feldnamen zurück. Chunked Bodies
  ohne Content-Length sind begrenzt, und die für Signaturen verwendeten Body-Bytes bleiben unverändert.
- Mehrdeutige Dienstkonfigurationen, doppelte Tokens und credential-/pfad-/queryhaltige Origins
  verhindern den Start. Der Host-Abgleich unterstützt IPv6-Loopback und lehnt fremde Hosts ab.
- Claims für aus der Konfiguration entfernte Empfänger sind gesperrt; bereits beanspruchte
  Ergebnisse können weiterhin finalisiert werden. Pending-Anfragen werden vor terminalem Verlauf geladen.
- Ergebnismeldungsfehler nach erfolgreicher externer Aktion sind als eigener Exception-Typ mit
  Ausführungs-ID und Ergebnisreferenz erkennbar. Upstream-Fehler werden durch Meldungsfehler nicht verdeckt.
- Das Beispiel-Checkout bindet frische Freigaben an den vollständigen Aktionsstand und unterstützt
  ausdrücklich neue, vertrauenswürdig vergebene Workflow-Versuche. Es erzeugt keine automatischen Ersatzversuche.
- QR-Dateien bleiben privat; die CLI lehnt Token-Echo ab und entfernt fehlgeschlagene Ausgaben,
  ohne Secret-haltige Fehlertexte auszugeben. Legacy-Web-Push ignoriert übermittelte private Textfelder.

### Native-App und Oberfläche

- Konkurrierende SecureStore-Änderungen erhalten beide Geräteschlüssel; späte Enrollment-Antworten
  stellen bereits entfernte Verbindungen nicht wieder her.
- Nur die aktuelle Inbox-Abfrage darf den sichtbaren Zustand ersetzen. Nicht erreichbare Verbindungen
  behalten lesbare Details, lassen aber keine Entscheidung zu. Abgelaufene Karten sperren ihre Bedienelemente.
- Der Schieberegler verlangt eine bewusste horizontale Einfinger-Geste. Live-Sperrzustand,
  Gestenabbruch und die explizite Screenreader-Bestätigung verhindern veraltete Freigabeaufrufe.
- Kopplungsvorschau und Verlauf erhalten Ablauf-, Lade- und Fehlerzustände. Biometrie ist beschriftet,
  die untere Safe Area wird berücksichtigt, und lange Dienstnamen können umbrechen.
- Der Netzwerk-Timeout umfasst auch das Lesen des Antwortbodys. Die native Transport-API weist
  Redirects zurück; die App akzeptiert nur einen geprüften HTTPS- oder Loopback-Origin.
- Lokale ausstehende Kopplungen können nur nach ausdrücklicher Bestätigung und erneuter
  eindeutiger Serverprüfung entfernt werden; ein Timeout verwirft keinen Schlüssel.
- Landingpage: semantische Schritte, Sprunglink, Tastaturfokus, Kontrast, Touch-Ziele und
  schmale Layouts. Chromium-Prüfung bei 1440, 390 und 320 Pixeln ohne horizontales Überlaufen;
  der Sprunglink fokussiert den Hauptinhalt. Screenshots: `output/review/landing-*.png`.

### Verifikation

- Python: **111 bestandene Tests** für Service, Pairing, Adapter, CLI und HTTP-Grenzen;
  Ruff-Prüfung und Formatprüfung bestanden. Eine bestehende Starlette/TestClient-Deprecation-Warnung bleibt.
- Native: TypeScript, Lint, **7 bestandene Sicherheits-/Nebenläufigkeitstests** sowie
  Android-/iOS-Hermes-Bundles. Eine temporäre iOS-Prebuild-Kopie ohne Installation bestand ebenfalls.
- Aktuelle `ApprovalCard`-/`Pairing`-Quellkomponenten über eine isolierte React-Native-Web-Fixture
  bei 390 und 320 Pixeln geprüft: pending, expired, busy, uncertain und Pairing ohne Überlaufen;
  gültige horizontale Freigabegeste akzeptiert, kurze/vertikale Gesten gesperrt, Vorschau/Abbruch geprüft.
  Native-only APIs sind in dieser Fixture gemockt. Screenshots: `output/review/native-*.png`.
- Helm: Digest-Pinning, HTTPS-Origins, eine Replik und Recreate-Strategie geprüft. Der Chart lehnt
  mutable Tags ab; die neue Chartprüfung und nativen Regressionstests laufen auch im PR-Gate.
- Tatsächlicher lokaler HTTP-Dienst + tatsächlicher Shooping-Adapter, synthetischer REWE-Upstream:
  vor Freigabe blockiert, danach genau eine gespeicherte Bestellung, `completed` gespeichert, Replay gesperrt.
- Reale Handygesten, Kamera, Biometrie, Push, iOS-Verteilung und echte REWE-Bestellungen wurden
  durch diese Prüfung nicht neu abgenommen.

### Native Abhängigkeiten

- `@expo/metro-file-map` innerhalb des bestehenden Versionsbereichs auf 57.0.4 aktualisiert.
- Der auf `xcode` begrenzte `uuid`-Override auf 11.1.1 ersetzt eine verwundbare transitive Version.
  Die verwendete CommonJS-API `uuid.v4()` wurde im tatsächlichen Xcode-Modul geprüft.
- Der aktuelle Auditstand sinkt von **29 auf 21 Meldungen**: 3 moderate, 18 high, keine critical.
  Expo 57 und React Native 0.86 bleiben erhalten. Ein erfolgreicher Bundle-Check ist kein sauberer Audit.
- Für die verbleibenden `braces`-/`node-forge`-Befunde existiert im abgefragten Registry-Stand keine
  korrigierte veröffentlichte Blattversion. Die korrigierte Decoder-Version ist ESM-only und passt
  nicht zum CommonJS-Consumer `query-string` im aktuellen Router; kein blindes Major-Override.

## Veröffentlichung und Produktionsrollout · Preview 5 · 7. Oktober 2026

- Quell-PR #10 gemergt zu `4cee7917d89daa0421a484a4eb18a7420f4b7418`.
  Exakte Main-Checks `37590346928` und CodeQL `37590346500` erfolgreich vor dem signierten Tag
  `v0.1.0-preview.5`. Release-Workflow `37590499590` erfolgreich: verify, image, Android und publish.
  Nicht als Entwurf veröffentlichte Vorschau mit fünf Assets am 7. Oktober 2026 um 10:09:22 Uhr MESZ.
- Publiziertes AMD64-/ARM64-Image:
  `ghcr.io/openhoo/hooapprove@sha256:11c91b713f64e6a3f2385e21cbe9c6adeb7b43a6e98622d2f9e742ca9bb42bbf`.
  Beide OCI-Konfigurationen binden diese Quellrevision und Preview-Version.
- GitOps-PR #243 nach erfolgreicher Validierung gemergt zu
  `22c328c98df3b2070e94b48ce3ae56a2295237ad`. Argo `hooapprove`: Synced/Healthy auf dieser Revision.
  Neuer Pod `hooapprove-5b77c4dc65-rcqrn` bereit; gewünschtes Image und tatsächliche `imageID`
  entsprechen dem publizierten Index-Digest. Beide ExternalSecrets melden Ready.
- Frische Jobs `preview5-before-backup` und `preview5-after-backup` erfolgreich:
  SQLite-Backup und isolierter Restore bestätigt. Die Produktionsdatenbank bleibt integer
  (`quick_check=ok`), mit einer abgeschlossenen und einer abgelehnten Anfrage sowie null aktiven
  Gerätekopplungen. Keine Empfänger- oder Aktionsdetails wurden ausgegeben.
- Tatsächlicher öffentlicher HTTPS-Dienst: `/healthz` meldet `production`; private Testwerte werden
  bei HTTP 422 nicht reflektiert, degenerierte Ed25519-Nachweise und übergroße Zeitstempel erhalten
  HTTP 401. `no-store` und HSTS gesetzt; die überarbeitete Landingpage ist live.
- Innerhalb des tatsächlich ausgerollten Images eine isolierte temporäre Testdatenbank genutzt:
  gültiger Schlüssel akzeptiert, gefälschter Schlüssel abgewiesen, Executor kann nicht entscheiden,
  Claim vor Entscheidung blockiert, signierte Kopplung/Inbox/Entscheidung bestätigt, Claim einmalig,
  synthetischer Abschluss gespeichert und widerrufenes Gerät gesperrt. Null externe Wirkungen;
  die Produktionsdatenbank und ihre Kopplungen wurden hierfür nicht verändert.
- Tatsächlich veröffentlichte ARM64-APK und alle Begleitassets heruntergeladen:
  alle vier `SHA256SUMS`-Einträge und alle fünf GitHub-Asset-Digests mit den Bytes abgeglichen.
  `SOURCE.txt` entspricht dem getesteten Quellcommit, `IMAGE.txt` dem ausgerollten Index-Digest.
- APK-Größe 50.959.890 Bytes; SHA-256
  `ff3115c7e4f632c6a29b18e26be31395d371af8ad68389616487ad258ab28f91`.
  APK-v2-Signatur gültig; Zertifikat-SHA-256
  `fac61745dc0903786fb9ede62a962b399f7348f0bb6f899b8332667591033b9c`
  stimmt mit Preview 4 überein.
- Aktualisierung auf Android-15-ARM64-Emulator `emulator-5580` mit `adb install -r` erfolgreich,
  ohne Deinstallation. Exakte Aktivität `ai.openhoo.hooapprove/.MainActivity` kalt gestartet und
  als Vordergrundaktivität bestätigt. Tatsächlicher veröffentlichter Start visuell geprüft:
  HooApprove, Dienst verbinden, Kopplungshinweise und Verbinden; keine Fehler-/Ladeüberlagerung.
  Screenshot `output/release-preview5/start.png`; strukturierter Nachweis
  `output/release-preview5/verification.json`.
- Diese Veröffentlichung ist weiterhin eine debug-signierte Android-ARM64-Vorschau.
  Keine neue echte Produktionskopplung, Bestellung, Push- oder Biometrieabnahme; kein Store-/TestFlight-Release.
