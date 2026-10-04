# HooApprove

**Dein Agent bereitet vor. Du gibst die konkrete Aktion frei.**

Generischer Freigabedienst mit nativer Android-/iOS-App. **Kein Benutzerkonto,
keine Anmeldung, kein Auth-Dienst.** Du koppelst dein Handy einmal per QR-Code,
wie einen Authenticator. Danach prüfst du die Anfragen und schiebst zur Freigabe.

[Android-Vorschauen](https://github.com/openhoo/hooapprove/releases) ·
[Gehosteter Dienst](https://approve.openhoo.dev)

Preview 1/2 enthalten den verworfenen Login-Ablauf. Die Kopplungsversion ersetzt diesen Ablauf.
Android-Vorschauen sind ARM64 und debug-signiert, mit eingebettetem JavaScript.
iOS-Quellcode ist enthalten; TestFlight/Store-Veröffentlichung und reale Push-Zustellung
sind noch nicht eingerichtet. Die geöffnete App lädt Anfragen auch ohne Push.

## Ablauf

1. Der Eigentümer erzeugt im eigenen Dienst einen privaten Kopplungscode.
2. In der App: **Dienst verbinden → QR-Code scannen → Verbindung prüfen → verbinden**.
3. Der MCP-Server bereitet die Aktion vor und erstellt eine Anfrage mit festem Empfänger.
4. Die App zeigt Dienst, Aktion und vollständige Details. Du schiebst zur Freigabe oder lehnst ab.
5. Der Server prüft den aktuellen Aktionsstand und löst genau diese Freigabe einmal ein.
6. Die App zeigt Entscheidung und Ausführungsergebnis im Verlauf.

Die App erzeugt ihren Geräteschlüssel lokal und speichert ihn im geschützten Gerätespeicher.
Der Server erhält nur den öffentlichen Schlüssel. Jede Anfrage der App wird signiert;
Freigaben sind an den unveränderlichen Aktionsinhalt gebunden. Kopplungscodes gelten fünf
Minuten, sind einmalig und ermöglichen keine stille Ersetzung eines bereits gekoppelten Handys.
Die App kann mehrere Dienste koppeln. Ein Dienst/Empfänger hat zunächst ein aktives Gerät.

Die Sperre muss im ausführenden Dienst sitzen. Service-Zugangsdaten, Kopplungscodes und
Upstream-Bestellzugänge gehören nicht in Agent-Prompts, MCP-Toolargumente oder Toolantworten.

## Private Kopplung für den Eigentümer

```sh
uv sync --frozen --extra pairing
uv run hooapprove-pair --subject your-fixed-recipient --label "Mein Einkaufsassistent" \
  --output /private/path/pairing.png
```

Der CLI fragt den Executor-Token verdeckt ab und erzeugt ein PNG mit Dateimodus `0600`.
Scanne es in der App und lösche es danach. Es enthält einen kurzlebigen Kopplungszugang.
Die Empfänger-ID ist eine feste, beliebige Kennung; sie benötigt kein Benutzerkonto.
Bei selbst gehostetem Dienst `--url` und die Build-Adresse der App passend konfigurieren.
Die CLI gehört in die private Eigentümer-/Operator-Oberfläche, nicht in den Agenten.

**Handywechsel:** In den App-Einstellungen die alte Verbindung ausdrücklich aufheben und
anschließend neu koppeln. Bei verlorenem Handy ist eine gesonderte vertrauenswürdige
Operator-Wiederherstellung nötig; der Agent kann das Gerät nicht austauschen.

## API für Dienste

| Endpoint | Zweck |
| --- | --- |
| `POST /v1/pairings` | Private Erstkopplung für festen Empfänger; `{subject, label}` |
| `POST /v1/requests` | Konkrete Aktion erstellen; idempotent |
| `GET /v1/requests/{id}` | Status lesen |
| `POST /v1/requests/{id}/claim` | Genehmigte Aktion genau einmal beanspruchen |
| `POST /v1/requests/{id}/result` | `completed`, `failed` oder `uncertain` melden |
| `POST /v1/requests/{id}/cancel` | Noch nicht beanspruchte Anfrage zurückziehen |

Dienste verwenden ihre eigenen Bearer-Tokens. Diese können keine menschliche Entscheidung
abgeben. Eine Aktion enthält `subject`, `action`, `title`, `summary`, vollständige `details`,
`payload`, `idempotency_key` und `expires_in` (30–1800 Sekunden). Dienst, Empfänger,
sichtbare Details und Payload werden gemeinsam durch einen Digest gebunden.

```python
from hooapprove.client import ApprovalClient
from hooapprove.models import ActionRequest

client = ApprovalClient(url, executor_token, "rewe")
action = ActionRequest(
    subject=fixed_owner_recipient,
    action="order.place",
    title="Deinen Einkauf bestellen",
    summary="Prüfe die vollständige Bestellung.",
    details=authoritative_order_details,
    payload=immutable_order_payload,
    idempotency_key=order_revision,
    expires_in=300,
)
request = client.request(action)
# Agent erhält nur Anfrage-ID/Status. Der Mensch entscheidet separat auf dem Handy.
# current_action frisch aus dem tatsächlichen Upstream-Stand ableiten.
reference = client.execute(request["id"], current_action, place_exact_order)
```

Geänderter Aktionsstand benötigt eine neue Freigabe. Nach verlorenem Claim oder unklarer
Bestellantwort wird keine Mutation automatisch wiederholt. Freigabe ist keine Erfolgsmeldung.

## Lokal entwickeln

```sh
uv sync --frozen
HOOAPPROVE_DEMO=1 uv run uvicorn hooapprove.app:create_app --factory \
  --host 127.0.0.1 --port 8097 --no-access-log
cd native
npm ci
npm run check
npm run lint
EXPO_PUBLIC_HOOAPPROVE_URL=http://127.0.0.1:8097 npx expo start
```

Die lokale App bietet **Demo-Dienst koppeln** und Beispielanfragen. Die Demo ist ausschließlich
Loopback und sendet keine echte Bestellung. Für Android-Emulator/USB kann `adb reverse tcp:8097 tcp:8097`
den Loopback-Dienst erreichbar machen. Native Kameramodule benötigen einen neuen nativen Build.

## Betrieb

Produktion benötigt HTTPS, dauerhafte SQLite-Speicherung und geschützte Executor-Zugänge.
`HOOAPPROVE_SECRETS_FILE` verweist auf das gemountete JSON-Secret:

```json
{"services": {"rewe": {"token": "retrieve-from-protected-custody", "subjects": ["fixed-recipient"]}}}
```

Tokens müssen mindestens 32 Zeichen haben. Weitere Variablen: `HOOAPPROVE_DATABASE`,
`HOOAPPROVE_PUBLIC_URL`. Es gibt keinen OIDC-Client, Issuer oder Sitzungsschlüssel.
Ältere Login-Konfigurationsfelder werden bei der Migration ignoriert. Alte Login-/Push-Sitzungstabellen
werden entfernt; Anfragen, Entscheidungen, Claims und Ausführungsergebnisse bleiben erhalten.

Container und Helm-Chart liegen im Repository; Produktionsänderungen gehen über `hooapps-gitops`
mit unveränderlichem Image-Digest. Ein Prozess, ein dauerhaftes Volume, `Recreate`-Updates.
SQLite-Backups mit der Backup-API erstellen und isoliert zurücklesen. Vor einem Restore
Ausführung anhalten, offene/genehmigte Anfragen verwerfen und externe Wirkungen abgleichen.

[Sicherheitsvertrag](docs/architecture.md) · [Abnahme](docs/verification.md) ·
[Shooping-Integration](docs/shooping.md)

Apache-2.0. Keine Analytics in der Anwendung.
