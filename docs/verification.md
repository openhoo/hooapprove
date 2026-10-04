# Veröffentlichung und Abnahme · 4. Oktober 2026

## Verifiziert

| Prüfung | Ergebnis |
| --- | --- |
| HooApprove-Dienst | 32 Tests bestanden |
| Autorisierung | Dienst-Token kann keine menschliche Entscheidung abgeben; fremde Nutzer/Dienste ausgeschlossen |
| Einmaligkeit | Acht parallele Claims: genau einer erfolgreich |
| Inhaltsbindung | Geänderte Preise, Payloads, Titel oder sichtbare Angaben können alte Freigaben nicht wiederverwenden |
| Ablauf und Ablehnung | Blockieren Ausführung auch ohne vorausgehendes Polling |
| Native Login-Übergabe | Falscher Verifier, Ticket-Replay und abgelaufene Tickets blockiert; Logout widerruft App-Sitzung |
| SQLite-Persistenz | Freigabe nach Öffnen eines neuen Store-Objekts ausgelesen |
| Shooping | 85 Tests bestanden, darunter acht neue HooApprove-Prüfungen |
| Tatsächlicher HTTP-Verbund | Echter HooApprove-Server + echter Shooping-Adapter, synthetischer REWE-Upstream: ohne Freigabe gesperrt, danach genau eine gespeicherte Bestellung, Abschlussmeldung und Replay-Sperre |
| Native App | TypeScript-Prüfung, Expo-Lint und iOS-/Android-Hermes-Bundles erfolgreich |
| Container | Build und Package-Import im Container erfolgreich |
| Helm | Lint und Manifest-Rendering erfolgreich |
| Browser | Demo-Anmeldung, Beispielanfrage, Schiebereglerfreigabe und gespeicherter Verlauf sichtbar geprüft |

Der HTTP-Verbund ist reproduzierbar:

```sh
cd ../shooping-hooapprove
npm run check
cd ../hooapprove
uv run python scripts/run_wire_proof.py ../shooping-hooapprove
```

## Veröffentlicht und live geprüft

- Öffentlicher Quellcode: https://github.com/openhoo/hooapprove, Default-Branch `main`.
- Dienst: https://approve.openhoo.dev, HTTPS-Startseite HTTP 200 und `/healthz` mit `mode=production`.
- Argo CD: Revision `2812619431d9caebf4ceb80a205b66b1f9e4c0b0`, Synced/Healthy; API und beide Tunnel-Replikate Ready, keine Neustarts.
- Tatsächlich laufendes Image: `ghcr.io/openhoo/hooapprove@sha256:a8dd3997a6227adfe43bac6109c7f67eb6bcfea5ae7aa817700e0bb46aa7b5a6`.
- OpenHoo-OIDC: registrierter Apps-Client, tatsächliche Anmeldung mit bestehender SSO-Sitzung, persönlicher Posteingang sichtbar.
- Produktions-Freigabetest `publication.noop`: ausdrücklich ohne Bestellung, Kosten oder REWE-Zugriff. Service-Token konnte nicht als Mensch entscheiden (401); Claim vor Freigabe gesperrt (409). Im Browser per Schieberegler freigegeben, einmal übernommen, wiederholter Claim gesperrt (409), Ergebnis `completed` gespeichert und im Verlauf erneut gelesen.
- Backupjobs `publish-proof-20261004` und `publish-proof-completed-20261004`: abgeschlossen, Meldung `SQLite backup and isolated restore verified`. Aus dem zweiten Snapshot wurde die abgeschlossene Produktions-Testaktion mitsamt vier Ereignissen in eine isolierte Datenbank wiederhergestellt und erneut gelesen. Täglicher CronJob und gesonderter Backup-PVC aktiv. Der überprüfte Exporter mit HooApprove-Snapshot wurde auf hooapps-01 installiert und bytegenau verglichen. Ein neuer tatsächlicher Offsite-Transfer wurde in dieser Abnahme nicht ausgeführt.
- Release `v0.1.0-preview.1`: APK, Multiarch-Image, Helm-Chart und Prüfsummen veröffentlicht. APK-Prüfsumme und APK-v2-Signatur geprüft, Installation auf Android-15-ARM64-Emulator erfolgreich. Diese erste APK verwendet localhost und benötigt ADB reverse für den Demo-Dienst.
- Release `v0.1.0-preview.2` ist veröffentlicht (Workflow `37201668093` erfolgreich). Alle heruntergeladenen Assets stimmen mit `SHA256SUMS` überein. APK-SHA256: `1ab0c7ef827daab93ad3b9963373728e0a349813a8b89563fd795cda5659fc0e`. APK-v2-Signatur gültig, eingebettetes Hermes-Bundle enthält den gehosteten HTTPS-Dienst und keine Demo-Localhost-Adresse. Installation/Update auf dem vorhandenen Android-15-ARM64-Emulator erfolgreich. Die veröffentlichte APK wurde anschließend tatsächlich gestartet; ihre native Oberfläche und der Wechsel über „Mit OpenHoo anmelden“ zum echten `auth.openhoo.ai`-Login im Android-Systembrowser wurden sichtbar geprüft. Für den vollständigen Rücksprung und die Freigabe fehlt noch die lokale menschliche Anmeldung im Emulator. Das native UI ist unverändert.
- Private Shooping-Integration: https://github.com/openhoo/shooping, `main`, 85 CI-Tests bestanden. Das Remote-Gate ist opt-in; der bestehende REWE-Dienst wurde nicht auf die neue Integration umgeschaltet.

## Noch nicht als live bestanden

- Vollständiger Login/Freigabeablauf in der nativen App auf einem physischen Handy; Screenreader-/Touch-Gerätetest, Biometrie und tatsächliche Push-Zustellung. Der Dienst und die Browserfreigabe wurden live geprüft; die installierte APK ist kein Beleg für diese Handytests.
- Apple-Signierung/TestFlight beziehungsweise Play-Store-Freigabe. Android-Vorschauen sind mit dem Debug-Schlüssel signiert.
- Echter gefüllter REWE-Checkout und echte Bestellung. Alle neuen Bestelltests sind synthetisch. Die produktive REWE-Integration bleibt opt-in.
- Server-verifizierbare Transaktionssignatur: lokale Biometrie stellt keine formale eTAN dar.
- Atomare upstreamseitige Versionssperre zwischen letzter REWE-Datenprüfung und Bestellaufruf.

## Abhängigkeiten

Der native Build verwendet den am 4. Oktober aufgelösten Expo-SDK-57-Template-Stand.
`npm audit` meldete 29 transitive/direct Meldungen (10 moderate, 19 high), hauptsächlich durch
Build-Werkzeuge und deren `braces`, `node-forge` und `uuid`-Abhängigkeiten. Ein pauschales
`npm audit fix --force` schlägt ein inkompatibles Expo-Downgrade vor und wurde nicht ausgeführt.
Die zum Prüfzeitpunkt veröffentlichten aktuellen `braces`-/`node-forge`-Versionen liegen weiterhin
im gemeldeten Bereich. Dies ist ein konkreter offener Release-Punkt; die Bundler/Signierwerkzeuge
dürfen nicht als ungeprüfter öffentlich zugänglicher Dienst betrieben werden.

FastAPI/Authlib melden die künftige Umstellung ihrer Test-/HTTP-Adapter auf `httpx2` als
Deprecation-Warnung. Die verwendeten Tests und der HTTP-Verbund bestehen mit dem gelockten Stand.

## Aufgelöste lokale Blocker

Der erste lokale Android-Build scheiterte während CMake/Kotlin in der gemeinsamen
OrbStack-VM. Die Veröffentlichung erfolgte anschließend über den geprüften
GitHub-Actions-Builder; ein erfolgreich gebautes und installiertes APK liegt vor.
Die konfigurierte Git-Signierung funktioniert wieder. Quellcode, Tags und Releases
wurden veröffentlicht; der Dienst wurde über die gemergten Auth-/GitOps-Änderungen
ausgerollt. Die frühere Aussage „kein APK/kein Push“ ist damit überholt.

## Fortsetzung: mobile Verteilung und Container-Anbindung

- EAS-CLI `whoami`: nicht angemeldet. Das Expo-Konto/die Organisation und das
  Apple-Developer-Team sind noch nicht zugeordnet. Keine neuen Konten, Projekte,
  Apple-Profile oder Push-Credentials wurden ohne diese Zuordnung angelegt.
- Xcode 26.5 ist lokal verfügbar; geprüft wurde ein gültiges Apple-Development-
  Zertifikat. Das belegt keine Distribution-/TestFlight-Berechtigung. Es sind keine
  verfügbaren iOS-Simulator-Geräte eingerichtet.
- REWE-Compose reicht jetzt optional `SHOOPING_HOOAPPROVE_CONFIG_FILE` in den
  Container weiter. Der Pfad liegt im bestehenden privaten State-Mount; ohne
  Opt-in bleibt der bisherige Modus erhalten. Beide gerenderten Varianten wurden
  geprüft; erneut 85 Shooping-Tests bestanden. Die laufende REWE-Instanz wurde
  noch nicht umgeschaltet und kein Kontostand verändert.
- Der bestehende Dependabot-PR zur URI-Decoder-Meldung würde Expo Router 58
  in das SDK-57-Projekt einführen. Sein `npm ci` scheitert am Peer-Konflikt
  mit `expo-constants`; er wurde nicht übernommen. Der aktuelle Auditstand bleibt
  10 moderate/19 high Meldungen; für `braces` und `node-forge` weist die
  Sicherheitsmeldung keine gepatchte Version aus. Kein pauschales Major-Downgrade
  oder `--force` wurde durchgeführt.
