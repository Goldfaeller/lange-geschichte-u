#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Laedt die 85 Witzeseiten auf modjor.de hoch, ueber die WordPress-REST-API.

Anders als das Programm fuer die Physiologie baut dieses hier nichts
zusammen: die Dateien "001 witze modjor-de.txt" bis "085 witze
modjor-de.txt" sind bereits vollstaendige Seiten mit Kopfzeile,
Navigation und Fussnavigation. Sie werden unveraendert hochgeladen.

Eine Seite, deren Adresse es schon gibt, wird ueberschrieben statt ein
zweites Mal angelegt. Die alten Seiten 1-witze bis 23-witze und 40-witze
bis 42-witze werden also von selbst ersetzt - haendisch loeschen ist
nicht noetig.

VOR DEM START das Anwendungspasswort als Umgebungsvariable setzen
(es steht bewusst NICHT im Code):

    Windows (Eingabeaufforderung):   set WP_APP_PASS=xxxx xxxx xxxx xxxx
    Windows (PowerShell):            $env:WP_APP_PASS = "xxxx xxxx xxxx xxxx"

Dann im selben Fenster:              python upload-witze.py
"""

import os
import re
import sys

import requests

# ----------------------------------------------------------------------------
# EINSTELLUNGEN
# ----------------------------------------------------------------------------

# Wie viele Seiten sollen hochgeladen werden? 3 = Testlauf, 0 = alle 85.
TESTLAUF = 0

# Status der Seiten: "draft" = nur fuer dich sichtbar, "publish" = oeffentlich.
STATUS = "publish"

# Ordner mit den Seitendateien. Hier liegen "001 witze modjor-de.txt" usw.
# Ein Punkt bedeutet: derselbe Ordner wie dieses Programm.
SOURCE_FOLDER = r"."

# WordPress
WP_URL = "https://modjor.de/wp-json/wp/v2/pages"
WP_USER = "Stefan"
WP_APP_PASS = os.environ.get("WP_APP_PASS")

# Adressform der Seiten: Seite 7 wird zu modjor.de/7-witze/
SLUG_MUSTER = "{nummer}-witze"

# Reiterbeschriftung: ergibt "Witze 7", WordPress haengt " – modjor.de" an.
TITEL_MUSTER = "Witze {nummer}"

# Uebergeordnete Seite. Leer lassen, dann liegen die Seiten oben in der
# Hierarchie, so wie bisher: modjor.de/1-witze/. Traegst du hier einen
# Slug ein, etwa "inhalt-witze", wandern sie darunter und ihre Adresse
# wird laenger - dann stimmen die Navigationslinks in den Dateien nicht
# mehr.
PARENT_SLUG = ""

# Muster der Dateinamen: drei Ziffern, dann " witze modjor-de.txt"
DATEI_MUSTER = re.compile(r"^(\d{3}) witze modjor-de\.txt$")


# ----------------------------------------------------------------------------
# 1. SEITENDATEIEN EINSAMMELN
# ----------------------------------------------------------------------------

def sammle_seiten():
    """Sucht die Seitendateien und bringt sie in die richtige Reihenfolge."""
    if not os.path.isdir(SOURCE_FOLDER):
        return []

    seiten = []
    for name in sorted(os.listdir(SOURCE_FOLDER)):
        treffer = DATEI_MUSTER.match(name)
        if not treffer:
            continue
        nummer = int(treffer.group(1))
        seiten.append({
            "nummer": nummer,
            "datei": name,
            "titel": TITEL_MUSTER.format(nummer=nummer),
            "slug": SLUG_MUSTER.format(nummer=nummer),
        })
    seiten.sort(key=lambda s: s["nummer"])
    return seiten


def lies_seite(seite):
    with open(os.path.join(SOURCE_FOLDER, seite["datei"]),
              encoding="utf-8-sig") as f:
        return f.read()


# ----------------------------------------------------------------------------
# 2. HOCHLADEN
# ----------------------------------------------------------------------------

def finde_seite(sitzung, slug):
    """Gibt die ID einer schon vorhandenen Seite zurueck, sonst None."""
    antwort = sitzung.get(WP_URL, params={"slug": slug, "status": "any"})
    antwort.raise_for_status()
    treffer = antwort.json()
    return treffer[0]["id"] if treffer else None


def lade_hoch(sitzung, seite, inhalt, parent_id):
    daten = {
        "title": seite["titel"],
        "slug": seite["slug"],
        "content": inhalt,
        "status": STATUS,
        # Die Reihenfolge in der Seitenliste von WordPress
        "menu_order": seite["nummer"],
        "parent": parent_id,
    }

    vorhanden = finde_seite(sitzung, seite["slug"])
    if vorhanden:
        antwort = sitzung.post("{}/{}".format(WP_URL, vorhanden), json=daten)
        aktion = "ueberschrieben"
    else:
        antwort = sitzung.post(WP_URL, json=daten)
        aktion = "angelegt"

    if antwort.status_code in (200, 201):
        return True, aktion, antwort.json().get("link", "")
    return False, "{} {}".format(antwort.status_code, antwort.text[:200]), ""


# ----------------------------------------------------------------------------
# HAUPTPROGRAMM
# ----------------------------------------------------------------------------

def main():
    if not WP_APP_PASS:
        print("Abbruch: die Umgebungsvariable WP_APP_PASS ist nicht gesetzt.")
        print("Siehe Anleitung oben in dieser Datei.")
        return 1

    seiten = sammle_seiten()
    if not seiten:
        print("Abbruch: im Ordner '{}' wurde keine Datei der Form "
              "'001 witze modjor-de.txt' gefunden.".format(
                  os.path.abspath(SOURCE_FOLDER)))
        return 1

    print("{} Seitendateien gefunden: {} bis {}.".format(
        len(seiten), seiten[0]["datei"], seiten[-1]["datei"]))

    # Luecken in der Nummernfolge melden - dann fehlt eine Datei
    erwartet = set(range(seiten[0]["nummer"], seiten[-1]["nummer"] + 1))
    fehlend = sorted(erwartet - {s["nummer"] for s in seiten})
    if fehlend:
        print("ACHTUNG: diese Nummern fehlen im Ordner: {}".format(
            ", ".join(str(n) for n in fehlend)))

    if TESTLAUF:
        auswahl = seiten[:TESTLAUF]
        print("TESTLAUF: es werden nur die ersten {} Seiten "
              "hochgeladen.".format(len(auswahl)))
    else:
        auswahl = seiten

    print("Status der Seiten: {}\n".format(STATUS))

    sitzung = requests.Session()
    sitzung.auth = (WP_USER, WP_APP_PASS)

    parent_id = 0
    if PARENT_SLUG:
        parent_id = finde_seite(sitzung, PARENT_SLUG)
        if not parent_id:
            print("Abbruch: die uebergeordnete Seite '{}' wurde nicht "
                  "gefunden.".format(PARENT_SLUG))
            return 1
        print("Uebergeordnete Seite gefunden (ID {}).\n".format(parent_id))

    fehler = 0
    neu = 0
    ersetzt = 0

    for seite in auswahl:
        inhalt = lies_seite(seite)
        erfolg, meldung, adresse = lade_hoch(sitzung, seite, inhalt, parent_id)

        if erfolg:
            if meldung == "angelegt":
                neu += 1
            else:
                ersetzt += 1
            print("OK   {:<4} {:<15} {}".format(
                seite["nummer"], meldung, adresse))
        else:
            fehler += 1
            print("FEHL {:<4} {}".format(seite["nummer"], meldung))

    print("\n" + "-" * 60)
    print("FERTIG. Neu angelegt: {}. Ueberschrieben: {}. Fehler: {}.".format(
        neu, ersetzt, fehler))

    if not TESTLAUF and not fehler:
        print("\nAlle {} Seiten stehen auf modjor.de.".format(len(auswahl)))
        print("Denk noch an das Inhaltsverzeichnis: den Inhalt von")
        print("'inhaltsverzeichnis-witze.txt' in die Seite")
        print("/startseite/lesebuecher/inhalt-witze/ einfuegen.")

    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())