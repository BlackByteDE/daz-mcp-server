# TODO — Aufträge im Fork (BlackByteDE/daz-mcp-server)

Aufträge für die DAZ-MCP-Bridge (diesen Fork). Die beads-Issues
(`bd ready`) sind **Upstreams** Roadmap (G.Hirpara, dazpy-Migration) und
gehören nicht hierher — siehe CLAUDE.md.

## Regeln zum Eintragen (auch für andere Projekte)

1. **Eine Zeile pro Auftrag** in der Tabelle *Offen* (oder *Später /
   optional*). Keine Befunde, Logs oder Reproduktionen hier — die gehören in
   den Bug-Katalog bzw. eine Themendatei im eigenen Repo. Die Zeile verlinkt
   nur darauf.
2. **Was:** Was die Bridge danach können oder anders machen soll, aus
   Sicht des Aufrufers (z. B. „Tool X liefert Y“, nicht „Bug in Z“).
3. **Quelle:** wer den Auftrag gibt.
   - Projektname (`pinkcharakter`, `pink-outbreak`, …) = von einem anderen
     Projekt hier abgelegt
   - `User` = im Chat beauftragt
   - `selbst` = bei der Arbeit hier festgestellt
4. **Seit:** Datum des Eintrags (`YYYY-MM-DD`).
5. **Details:** Bug-Nummer aus dem Bug-Katalog
   (`D:\Dev\pinkcharakter\docs\daz-mcp-bridge-bugs.md`), falls vorhanden,
   plus Link auf die Datei mit den Details. Pfade relativ zu diesem Repo
   (`../pinkcharakter/docs/…`), **ohne `#anker`** — Überschriften ändern
   sich, der Anker bricht dann still.
6. **Nicht doppelt führen:** Wird ein Auftrag aus der eigenen Todo-Liste
   hierher verschoben, dort löschen (oder nur noch „→ daz-mcp-server
   FORK_TODO“ stehen lassen, solange das eigene Projekt darauf wartet).
7. **Erledigt** wird die Zeile hier gelöscht; der Git-Verlauf und
   [FORK_CHANGELOG.md](FORK_CHANGELOG.md) halten fest, was geliefert wurde.
   Das auftraggebende Projekt prüft das Ergebnis und räumt bei sich auf.

## Offen

| Was | Quelle | Seit | Details |
|---|---|---|---|
| `daz_execute`/`daz_execute_file`: Timeout pro Aufruf; nach einem Timeout „läuft noch“ + Request-ID statt Fehler, Folgeaufrufe bis zum Ende sperren/ablehnen; Abbruch eines laufenden Skripts, wenn machbar | pinkcharakter | 2026-10-26 | Bug 47, [../pinkcharakter/docs/bugs/tooling-tests.md](../pinkcharakter/docs/bugs/tooling-tests.md) |

## Später / optional

| Was | Quelle | Seit | Details |
|---|---|---|---|
| `daz_export_geometry_frames` reicht `vertices` (bool, Default `true`) an `POST /geometry/frames` durch — `false` liefert nur Bone-Ursprünge (`numVerts = 0`, braucht `bones`), ab daz-script-server `2.9.2+bb.4` | daz-script-server | 2026-10-27 | Bug 48, [../pinkcharakter/docs/bugs/tooling-tests.md](../pinkcharakter/docs/bugs/tooling-tests.md) |
