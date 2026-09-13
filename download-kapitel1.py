#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Holt die Kapitelseiten von modjor.de herunter und legt sie als Dateien ab.

Gedacht fuer Kapitel 1: die Seiten stehen schon auf der Website, sollen
aber die beiden Ausklappboxen bekommen. Dieses Programm laedt sie
herunter; das Ergaenzen der Boxen und das Hochladen kommen danach.

Es ist das Gegenstueck zu upload-geschichte.py: gleiche Schnittstelle,
gleiche Anmeldung, nur in die andere Richtung.

VOR DEM START das Anwendungspasswort setzen - am einfachsten ueber
dieselbe Batchdatei wie beim Hochladen, nur mit diesem Programmnamen
in der letzten Zeile:

    set WP_APP_PASS=[dein Passwort]
    python download-kapitel1.py
    pause

Die Dateien landen im Unterordner "heruntergeladen" und heissen wie die
Seitenadresse, also etwa "1-2-3-geschichte-ungarns-lang".
"""

import os
import sys
import time

import requests

# ----------------------------------------------------------------------------
# EINSTELLUNGEN
# ----------------------------------------------------------------------------

# Welches Hauptkapitel? "1" holt Kapitel 1 und alle seine Unterkapitel.
KAPITEL = "1"

# Wohin die Dateien geschrieben werden.
ZIEL_ORDNER = "heruntergeladen"

# WordPress
WP_URL = "https://modjor.de/wp-json/wp/v2/pages"
WP_USER = "Stefan"
WP_APP_PASS = os.environ.get("WP_APP_PASS")

# Unter welcher Seite die Kapitelseiten haengen.
PARENT_SLUG = "inhalt-geschichte-ungarns-lang"

# Endung der Adressen, an der die Kapitelseiten zu erkennen sind.
SLUG_ENDUNG = "-geschichte-ungarns-lang"

PAUSE_SEKUNDEN = 0.3


# ----------------------------------------------------------------------------

def mit_wiederholung(aufruf, versuche=4):
    """Wiederholt bei Netzwerkfehlern: 2s, 4s, 8s."""
    wartezeit = 2
    for versuch in range(versuche):
        try:
            return aufruf()
        except requests.exceptions.RequestException as fehler:
            if versuch == versuche - 1:
                raise
            print("  Netzwerkfehler ({}), neuer Versuch in {}s ...".format(
                type(fehler).__name__, wartezeit))
            time.sleep(wartezeit)
            wartezeit *= 2


def kapitelnummer(slug):
    """'1-2-3-geschichte-ungarns-lang' -> '1.2.3'; None wenn es keine ist."""
    rest = slug[:-len(SLUG_ENDUNG)] if slug.endswith(SLUG_ENDUNG) else None
    if not rest:
        return None
    teile = rest.split("-")
    if not all(t.isdigit() for t in teile):
        return None
    return ".".join(teile)


def hole_alle_unterseiten(sitzung, parent_id):
    """Holt saemtliche Seiten unterhalb der angegebenen Seite."""
    seiten = []
    nummer = 1
    while True:
        antwort = mit_wiederholung(lambda: sitzung.get(WP_URL, params={
            "parent": parent_id, "per_page": 100, "page": nummer,
            "status": "any", "_fields": "id,slug,title,content"}))
        if antwort.status_code == 400:      # keine weitere Seite mehr
            break
        antwort.raise_for_status()
        stapel = antwort.json()
        if not stapel:
            break
        seiten.extend(stapel)
        if len(stapel) < 100:
            break
        nummer += 1
    return seiten


def main():
    if not WP_APP_PASS:
        print("Abbruch: die Umgebungsvariable WP_APP_PASS ist nicht gesetzt.")
        print("Siehe Anleitung oben in dieser Datei.")
        return 1

    sitzung = requests.Session()
    sitzung.auth = (WP_USER, WP_APP_PASS)

    # Inhaltsverzeichnis finden
    antwort = mit_wiederholung(lambda: sitzung.get(
        WP_URL, params={"slug": PARENT_SLUG, "status": "any", "_fields": "id"}))
    antwort.raise_for_status()
    treffer = antwort.json()
    if not treffer:
        print("Abbruch: die Seite '{}' wurde nicht gefunden.".format(PARENT_SLUG))
        return 1
    parent_id = treffer[0]["id"]
    print("Inhaltsverzeichnis gefunden (ID {}).".format(parent_id))

    alle = hole_alle_unterseiten(sitzung, parent_id)
    print("{} Unterseiten insgesamt gefunden.".format(len(alle)))

    # Auf das gewuenschte Hauptkapitel eingrenzen
    gewaehlt = []
    for seite in alle:
        nummer = kapitelnummer(seite["slug"])
        if not nummer:
            continue
        if nummer == KAPITEL or nummer.startswith(KAPITEL + "."):
            gewaehlt.append((nummer, seite))
    gewaehlt.sort(key=lambda x: [int(t) for t in x[0].split(".")])

    if not gewaehlt:
        print("Abbruch: zu Kapitel {} wurde nichts gefunden.".format(KAPITEL))
        return 1
    print("Davon gehoeren {} zu Kapitel {}: {} bis {}.\n".format(
        len(gewaehlt), KAPITEL, gewaehlt[0][0], gewaehlt[-1][0]))

    os.makedirs(ZIEL_ORDNER, exist_ok=True)

    geschrieben = leer = 0
    for nummer, seite in gewaehlt:
        inhalt = seite.get("content", {}).get("rendered", "")
        if not inhalt.strip():
            leer += 1
            print("LEER {:<8} {} - keine Inhalte erhalten".format(
                nummer, seite["slug"]))
            continue
        pfad = os.path.join(ZIEL_ORDNER, seite["slug"])
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(inhalt)
        geschrieben += 1
        print("OK   {:<8} {:>8} Zeichen  -> {}".format(
            nummer, len(inhalt), pfad))
        time.sleep(PAUSE_SEKUNDEN)

    print("\n" + "-" * 60)
    print("FERTIG. Geschrieben: {}. Ohne Inhalt: {}.".format(geschrieben, leer))
    print("\nDie Dateien liegen im Ordner '{}'.".format(
        os.path.abspath(ZIEL_ORDNER)))
    print("Lade sie von dort nach GitHub hoch.")

    print("\nACHTUNG: WordPress liefert die Seiten in aufbereiteter Form")
    print("zurueck. Die Blockkommentare (<!-- wp:paragraph -->) koennen")
    print("dabei fehlen. Sieh dir eine Datei an und vergleiche sie mit")
    print("einer fertigen Seite, bevor du alle hochlaedst.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
