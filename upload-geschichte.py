#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Laedt die 165 Kapitelseiten "Geschichte Ungarns - lange Saetze" auf
modjor.de hoch, ueber die WordPress-REST-API.

Die Dateien "kkk-02-00-00-ung-dt-html-fertig" bis
"kkk-04-05-06-ung-dt-html-fertig" sind bereits vollstaendige Seiten mit
Kopfzeile, Navigation, den beiden Ausklappboxen und Fussnavigation. Sie
werden unveraendert hochgeladen.

WICHTIG - anders als bei den Witzen:
Diese Seiten liegen UNTER dem Inhaltsverzeichnis. Ihre Adresse lautet
  modjor.de/startseite/lesebuecher/inhalt-geschichte-ungarns-lang/2-10-2-geschichte-ungarns-lang/
Genau so sind die Links in den Dateien geschrieben. Deshalb muss
PARENT_SLUG gesetzt bleiben, sonst landen die Seiten an der falschen
Stelle und saemtliche Vor- und Zurueck-Links laufen ins Leere.

Eine Seite, deren Adresse es schon gibt, wird ueberschrieben statt ein
zweites Mal angelegt. Ein zweiter Durchlauf legt also keine Dubletten an.

VOR DEM START das Anwendungspasswort als Umgebungsvariable setzen
(es steht bewusst NICHT im Code):

    Windows (Eingabeaufforderung):   set WP_APP_PASS=xxxx xxxx xxxx xxxx
    Windows (PowerShell):            $env:WP_APP_PASS = "xxxx xxxx xxxx xxxx"

Dann im selben Fenster:              python upload-geschichte.py

EMPFEHLUNG: erst TROCKENLAUF = True laufen lassen. Dann wird nichts
hochgeladen, sondern nur geprueft und angezeigt, was passieren wuerde.
"""

import os
import re
import sys
import time

import requests

# ----------------------------------------------------------------------------
# EINSTELLUNGEN
# ----------------------------------------------------------------------------

# True = nichts hochladen, nur pruefen und anzeigen. Zum Ausprobieren.
TROCKENLAUF = True

# Wie viele Seiten sollen hochgeladen werden? 3 = Testlauf, 0 = alle 165.
TESTLAUF = 0

# Status der Seiten: "draft" = nur fuer dich sichtbar, "publish" = oeffentlich.
STATUS = "publish"

# Soll auch das Inhaltsverzeichnis erneuert werden?
# Es ist schon oben, deshalb standardmaessig aus.
INHALTSVERZEICHNIS_MIT = False
INHALTSVERZEICHNIS_DATEI = "inhalt-vesion1.txt"

# Ordner mit den Seitendateien. Ein Punkt = derselbe Ordner wie dieses
# Programm.
SOURCE_FOLDER = r"."

# WordPress
WP_URL = "https://modjor.de/wp-json/wp/v2/pages"
WP_USER = "Stefan"
WP_APP_PASS = os.environ.get("WP_APP_PASS")

# Adressform: Kapitel 2.10.2 wird zu .../2-10-2-geschichte-ungarns-lang/
SLUG_MUSTER = "{bindestrich}-geschichte-ungarns-lang"

# Reiterbeschriftung, wie bei den schon vorhandenen Seiten von Kapitel 1.
TITEL_MUSTER = "{bindestrich} Geschichte Ungarns lang"

# Uebergeordnete Seite: das Inhaltsverzeichnis. NICHT leeren, siehe oben.
PARENT_SLUG = "inhalt-geschichte-ungarns-lang"

# Kurze Pause zwischen zwei Seiten, damit der Server nicht ueberrannt wird.
PAUSE_SEKUNDEN = 0.4

# Muster der Dateinamen: kkk-02-10-02-ung-dt-html-fertig
DATEI_MUSTER = re.compile(r"^kkk-(\d{2})-(\d{2})-(\d{2})-ung-dt-html-fertig$")


# ----------------------------------------------------------------------------
# 1. SEITENDATEIEN EINSAMMELN
# ----------------------------------------------------------------------------

def kapitelnummer(teile):
    """(2, 10, 2) -> "2.10.2"   /   (2, 0, 0) -> "2"

    Die Nullen am Ende gehoeren nicht in die Kapitelnummer: die Datei
    kkk-02-00-00 ist das Hauptkapitel 2, nicht "2.0.0".
    """
    zahlen = list(teile)
    while len(zahlen) > 1 and zahlen[-1] == 0:
        zahlen.pop()
    return ".".join(str(z) for z in zahlen)


def sammle_seiten():
    """Sucht die Seitendateien und bringt sie in Kapitelreihenfolge."""
    if not os.path.isdir(SOURCE_FOLDER):
        return []

    seiten = []
    for name in sorted(os.listdir(SOURCE_FOLDER)):
        treffer = DATEI_MUSTER.match(name)
        if not treffer:
            continue
        teile = tuple(int(t) for t in treffer.groups())
        nummer = kapitelnummer(teile)
        bindestrich = nummer.replace(".", "-")
        seiten.append({
            "sortier": teile,
            "nummer": nummer,
            "datei": name,
            "titel": TITEL_MUSTER.format(bindestrich=bindestrich),
            "slug": SLUG_MUSTER.format(bindestrich=bindestrich),
        })
    seiten.sort(key=lambda s: s["sortier"])
    # menu_order: die Reihenfolge in der Seitenliste von WordPress
    for i, seite in enumerate(seiten, start=1):
        seite["reihenfolge"] = i
    return seiten


def lies_datei(name):
    with open(os.path.join(SOURCE_FOLDER, name), encoding="utf-8-sig") as f:
        return f.read()


def pruefe_seite(seite, inhalt):
    """Grobe Plausibilitaetspruefung. Gibt eine Liste von Einwaenden zurueck."""
    einwaende = []
    if "<!-- wp:group" not in inhalt:
        einwaende.append("kein wp:group-Block")
    boxen = inhalt.count("<details")
    if boxen == 0 or boxen % 2:
        einwaende.append("{} Ausklappboxen - erwartet werden 2 je Textfassung".format(boxen))
    if inhalt.count("</details>") != boxen:
        einwaende.append("Ausklappboxen nicht sauber geschlossen")
    kopf = re.search(r"<span>Kapitel ([\d.]+)</span>", inhalt)
    if not kopf:
        einwaende.append("keine Kapitelangabe in der Navigation")
    elif kopf.group(1) != seite["nummer"]:
        einwaende.append("Navigation sagt Kapitel {}, Dateiname sagt {}".format(
            kopf.group(1), seite["nummer"]))
    if len(inhalt) < 2000:
        einwaende.append("verdaechtig kurz ({} Zeichen)".format(len(inhalt)))
    return einwaende


# ----------------------------------------------------------------------------
# 2. HOCHLADEN
# ----------------------------------------------------------------------------

def finde_seite(sitzung, slug, parent_id=None):
    """Gibt die ID einer schon vorhandenen Seite zurueck, sonst None."""
    werte = {"slug": slug, "status": "any", "per_page": 100}
    if parent_id is not None:
        werte["parent"] = parent_id
    antwort = sitzung.get(WP_URL, params=werte)
    antwort.raise_for_status()
    treffer = antwort.json()
    return treffer[0]["id"] if treffer else None


def mit_wiederholung(aufruf, versuche=4):
    """Wiederholt bei Netzwerkfehlern: 2s, 4s, 8s."""
    wartezeit = 2
    for versuch in range(versuche):
        try:
            return aufruf()
        except requests.exceptions.RequestException as fehler:
            if versuch == versuche - 1:
                raise
            print("     Netzwerkfehler ({}), neuer Versuch in {}s ...".format(
                type(fehler).__name__, wartezeit))
            time.sleep(wartezeit)
            wartezeit *= 2


def lade_hoch(sitzung, seite, inhalt, parent_id):
    daten = {
        "title": seite["titel"],
        "slug": seite["slug"],
        "content": inhalt,
        "status": STATUS,
        "menu_order": seite["reihenfolge"],
        "parent": parent_id,
    }

    vorhanden = mit_wiederholung(
        lambda: finde_seite(sitzung, seite["slug"], parent_id))
    if vorhanden:
        antwort = mit_wiederholung(
            lambda: sitzung.post("{}/{}".format(WP_URL, vorhanden), json=daten))
        aktion = "ueberschrieben"
    else:
        antwort = mit_wiederholung(lambda: sitzung.post(WP_URL, json=daten))
        aktion = "angelegt"

    if antwort.status_code in (200, 201):
        return True, aktion, antwort.json().get("link", "")
    return False, "{} {}".format(antwort.status_code, antwort.text[:200]), ""


# ----------------------------------------------------------------------------
# HAUPTPROGRAMM
# ----------------------------------------------------------------------------

def main():
    seiten = sammle_seiten()
    if not seiten:
        print("Abbruch: im Ordner '{}' wurde keine Datei der Form "
              "'kkk-02-10-02-ung-dt-html-fertig' gefunden.".format(
                  os.path.abspath(SOURCE_FOLDER)))
        return 1

    print("{} Seitendateien gefunden: Kapitel {} bis {}.".format(
        len(seiten), seiten[0]["nummer"], seiten[-1]["nummer"]))

    # Alle Dateien einlesen und pruefen, BEVOR irgendetwas hochgeht
    einwaende_gesamt = 0
    for seite in seiten:
        seite["inhalt"] = lies_datei(seite["datei"])
        for einwand in pruefe_seite(seite, seite["inhalt"]):
            print("  ACHTUNG {}: {}".format(seite["datei"], einwand))
            einwaende_gesamt += 1
    if einwaende_gesamt:
        print("\nAbbruch: {} Einwand/Einwaende. Bitte erst klaeren.".format(
            einwaende_gesamt))
        return 1
    print("Alle Dateien geprueft: Aufbau in Ordnung.")

    # Doppelte Adressen waeren fatal - eine Seite wuerde die andere ueberschreiben
    slugs = [s["slug"] for s in seiten]
    doppelt = {s for s in slugs if slugs.count(s) > 1}
    if doppelt:
        print("Abbruch: doppelte Adressen: {}".format(", ".join(sorted(doppelt))))
        return 1

    auswahl = seiten[:TESTLAUF] if TESTLAUF else seiten
    if TESTLAUF:
        print("TESTLAUF: nur die ersten {} Seiten.".format(len(auswahl)))

    # ---- Trockenlauf: nichts hochladen, nur zeigen ----
    if TROCKENLAUF:
        print("\nTROCKENLAUF - es wird nichts hochgeladen.\n")
        print("So wuerden die Seiten heissen:\n")
        for seite in auswahl[:5] + (["..."] if len(auswahl) > 8 else []) + auswahl[-3:]:
            if seite == "...":
                print("  ...")
                continue
            print("  Kapitel {:<8} -> .../{}/{}/".format(
                seite["nummer"], PARENT_SLUG, seite["slug"]))
            print("  {:<16}    Titel: {}".format("", seite["titel"]))
        print("\nZum echten Hochladen oben TROCKENLAUF = False setzen.")
        return 0

    if not WP_APP_PASS:
        print("\nAbbruch: die Umgebungsvariable WP_APP_PASS ist nicht gesetzt.")
        print("Siehe Anleitung oben in dieser Datei.")
        return 1

    print("Status der Seiten: {}\n".format(STATUS))

    sitzung = requests.Session()
    sitzung.auth = (WP_USER, WP_APP_PASS)

    # Uebergeordnete Seite suchen
    if not PARENT_SLUG:
        print("Abbruch: PARENT_SLUG ist leer. Die Seiten muessen unter dem")
        print("Inhaltsverzeichnis liegen, sonst stimmen alle Links nicht mehr.")
        return 1
    parent_id = mit_wiederholung(lambda: finde_seite(sitzung, PARENT_SLUG))
    if not parent_id:
        print("Abbruch: die uebergeordnete Seite '{}' wurde nicht "
              "gefunden.".format(PARENT_SLUG))
        print("Lege sie zuerst an, oder pruefe die Schreibweise.")
        return 1
    print("Inhaltsverzeichnis gefunden (ID {}).\n".format(parent_id))

    fehler = neu = ersetzt = 0
    fehlerliste = []

    for seite in auswahl:
        erfolg, meldung, adresse = lade_hoch(
            sitzung, seite, seite["inhalt"], parent_id)

        if erfolg:
            if meldung == "angelegt":
                neu += 1
            else:
                ersetzt += 1
            print("OK   {:<8} {:<15} {}".format(
                seite["nummer"], meldung, adresse))
        else:
            fehler += 1
            fehlerliste.append((seite["nummer"], meldung))
            print("FEHL {:<8} {}".format(seite["nummer"], meldung))

        time.sleep(PAUSE_SEKUNDEN)

    # Inhaltsverzeichnis, falls gewuenscht
    if INHALTSVERZEICHNIS_MIT and not TESTLAUF:
        pfad = os.path.join(SOURCE_FOLDER, INHALTSVERZEICHNIS_DATEI)
        if os.path.isfile(pfad):
            antwort = mit_wiederholung(lambda: sitzung.post(
                "{}/{}".format(WP_URL, parent_id),
                json={"content": lies_datei(INHALTSVERZEICHNIS_DATEI)}))
            if antwort.status_code in (200, 201):
                print("\nOK   Inhaltsverzeichnis erneuert.")
            else:
                fehler += 1
                print("\nFEHL Inhaltsverzeichnis: {} {}".format(
                    antwort.status_code, antwort.text[:200]))
        else:
            print("\nACHTUNG: '{}' nicht gefunden, Inhaltsverzeichnis "
                  "uebersprungen.".format(INHALTSVERZEICHNIS_DATEI))

    print("\n" + "-" * 60)
    print("FERTIG. Neu angelegt: {}. Ueberschrieben: {}. Fehler: {}.".format(
        neu, ersetzt, fehler))

    if fehlerliste:
        print("\nDiese Kapitel sind NICHT oben:")
        for nummer, meldung in fehlerliste:
            print("  {:<8} {}".format(nummer, meldung))
        print("\nEin erneuter Durchlauf holt sie nach - schon hochgeladene")
        print("Seiten werden dabei nur ueberschrieben, nicht verdoppelt.")
    elif not TESTLAUF:
        print("\nAlle {} Kapitelseiten stehen auf modjor.de.".format(len(auswahl)))
        if not INHALTSVERZEICHNIS_MIT:
            print("Das Inhaltsverzeichnis wurde nicht angefasst. Falls es")
            print("erneuert werden soll: oben INHALTSVERZEICHNIS_MIT = True.")

    return 1 if fehler else 0


if __name__ == "__main__":
    sys.exit(main())
