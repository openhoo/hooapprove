# Lokale Abnahme · 4. Oktober 2026

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

## Noch nicht als live bestanden

- Produktionsadresse, DNS/TLS, GitOps-Rollout und Wiederherstellungstest.
- Echte OpenHoo-OIDC-Registrierung und vollständiger Login auf dem Zielhandy.
- Native Installation, Screenreader-/Touch-Gerätetest, Biometrie und tatsächliche Push-Zustellung.
- Apple-Signierung/TestFlight beziehungsweise Play-Store-Freigabe.
- Echter gefüllter REWE-Checkout und echte Bestellung. Alle neuen Bestelltests sind synthetisch.

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

## Konkreter Android-Build-Blocker

Der lokale AMD64-Android-Build am 4. Oktober 2026 erreichte die nativen
CMake-/Kotlin-Schritte, lieferte aber noch kein APK. Die gemeinsame OrbStack-VM
antwortet seit dem Build weder auf Docker-Abfragen noch auf einen gezielten
Stop-Aufruf für `hooapprove-android-build`. Ihr Kernel-Log enthält mehrfach
`VM_FAULT_OOM`; die alleinige Ursache des Stillstands ist damit nicht bewiesen.
Es wurde kein Neustart der gemeinsamen VM ausgelöst, da das andere Container
betreffen kann. Der Zustand des Build-Containers ist aktuell nicht abfragbar.
Nach Wiederherstellung der Engine zuerst gezielt den alten Build stoppen:

```sh
docker stop --time 1 hooapprove-android-build
```

Danach den dokumentierten Build mit freiem Speicher wiederholen. Es gibt noch
kein erfolgreich gebautes oder installiertes HooApprove-APK als Abnahmebeleg.
Die sichtbare native UI-Abnahme war zusätzlich durch den gesperrten Mac blockiert.

Die lokalen Feature-Änderungen sind gestaged. Ein Shooping-Commit scheiterte am
nicht verfügbaren 1Password-Signierzugriff; die konfigurierte Signierung wurde
nicht geändert. Kein Push und keine Veröffentlichung erfolgt.
