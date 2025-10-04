import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from racecard.models import Race, Horse, Run, Ranking


class Command(BaseCommand):
    help = "Import a racecard HTML file into the database"

    def add_arguments(self, parser):
        parser.add_argument("filepath", type=str, help="Path to racecard HTML file")

    def handle(self, *args, **options):
        filepath = options["filepath"]

        if not os.path.exists(filepath):
            self.stdout.write(self.style.ERROR(f"File not found: {filepath}"))
            return

        with open(filepath, "r", encoding="utf-8") as f:
            soup = BeautifulSoup(f, "html.parser")

        self.stdout.write("[STEP 1] Extracting race details (name/distance/class/merit)...")
        details = extract_race_details(soup) or {}
        self.stdout.write(f"  • race_name: {details.get('race_name', '')!r}")
        self.stdout.write(f"  • distance: {details.get('distance', 0)}m")
        self.stdout.write(f"  • race_class: {details.get('race_class', '')!r}")
        self.stdout.write(f"  • merit: {details.get('merit', 0)}")

        # Save race object (avoid duplicates)
        race, created = Race.objects.get_or_create(
            race_date=details.get("race_date"),
            race_no=details.get("race_no"),
            field=details.get("field"),
            defaults={
                "race_name": details.get("race_name"),
                "distance": details.get("distance"),
                "race_class": details.get("race_class"),
                "merit": details.get("merit"),
            },
        )
        if created:
            self.stdout.write(self.style.SUCCESS(f"✅ Created Race: {race}"))
        else:
            self.stdout.write(self.style.WARNING(f"⚠️ Race already exists, skipping insert: {race}"))
            return  # do not re-import horses/runs if race already exists

        # Horses
        self.stdout.write("[STEP 2] Extracting horses...")
        horses = extract_horses(soup)
        for horse in horses:
            horse_obj = Horse.objects.create(
                race=race,
                number=horse.get("number"),
                name=horse.get("name"),
                age=horse.get("age"),
                dob=horse.get("dob"),
                odds=horse.get("odds"),
                merit=horse.get("merit"),
                blinkers=horse.get("blinkers", False),
                trainer=horse.get("trainer"),
            )
            self.stdout.write(f"  🐎 Inserted Horse: {horse_obj.name}")

            # Runs
            runs = horse.get("runs", [])
            for run in runs:
                Run.objects.create(
                    horse=horse_obj,
                    date=run.get("date"),
                    position=run.get("position"),
                    margin=run.get("margin"),
                    distance=run.get("distance"),
                    race_class=run.get("race_class"),
                )
            self.stdout.write(f"    📜 Added {len(runs)} past runs")

            # Ranking
            Ranking.objects.create(
                horse=horse_obj,
                merit_score=horse.get("merit", 0),
                class_score=calculate_class_score(horse),
                final_score=calculate_final_score(horse),
            )
            self.stdout.write(f"    📊 Ranking stored for {horse_obj.name}")

        self.stdout.write(self.style.SUCCESS("🎯 Racecard import completed."))


# ------------------ Helper functions ------------------ #

def extract_race_details(soup):
    """Extract race details safely, always return dict"""
    race_info_div = soup.find("div", class_="raceinfo")
    if not race_info_div:
        return {
            "race_name": "",
            "distance": 0,
            "race_class": "",
            "merit": 0,
            "race_date": None,
            "race_no": None,
            "field": "",
        }

    text = race_info_div.get_text(" ", strip=True)

    # Parse with regex
    race_name = re.search(r"Race\s+\d+\s*-\s*(.*?)(?=,|$)", text)
    distance = re.search(r"(\d+)\s*m", text)
    race_class = re.search(r"Class\s*([\w\s\d]+)", text)
    merit = re.search(r"Merit\s*Rated\s*(\d+)", text)
    race_no = re.search(r"Race\s*(\d+)", text)

    return {
        "race_name": race_name.group(1).strip() if race_name else "",
        "distance": int(distance.group(1)) if distance else 0,
        "race_class": race_class.group(1).strip() if race_class else "",
        "merit": int(merit.group(1)) if merit else 0,
        "race_no": int(race_no.group(1)) if race_no else None,
        "race_date": extract_race_date(soup),
        "field": extract_field(soup),
    }


def extract_horses(soup):
    """Extract all horses in the racecard"""
    horses = []
    rows = soup.find_all("tr", class_="small")
    for row in rows:
        cols = [c.get_text(strip=True) for c in row.find_all("td")]
        if not cols:
            continue

        horse = {
            "number": parse_int(cols[0]),
            "name": cols[1],
            "blinkers": "b" in cols[1].lower(),
            "age": parse_int(cols[2]) if len(cols) > 2 else None,
            "dob": None,
            "odds": parse_odds(cols[3]) if len(cols) > 3 else None,
            "merit": parse_int(cols[4]) if len(cols) > 4 else None,
            "trainer": cols[5] if len(cols) > 5 else "",
            "runs": extract_runs(row),
        }
        horses.append(horse)
    return horses


def extract_runs(row):
    """Extract past runs from a horse row"""
    runs = []
    run_rows = row.find_all("tr", class_="run")
    for r in run_rows:
        cols = [c.get_text(strip=True) for c in r.find_all("td")]
        if not cols:
            continue
        run = {
            "date": parse_date(cols[0]),
            "position": cols[1],
            "margin": cols[2],
            "distance": parse_int(cols[3]),
            "race_class": cols[4] if len(cols) > 4 else "",
        }
        runs.append(run)
    return runs


def extract_race_date(soup):
    """Stub for extracting race date from header"""
    header = soup.find("h1")
    if not header:
        return None
    text = header.get_text(strip=True)
    m = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    return datetime.strptime(m.group(1), "%Y-%m-%d").date() if m else None


def extract_field(soup):
    """Stub for extracting racecourse/field"""
    header = soup.find("h1")
    return header.get_text(strip=True).split("-")[-1].strip() if header else ""


# ------------------ Utility parsers ------------------ #

def parse_int(value):
    try:
        return int(value)
    except Exception:
        return None


def parse_odds(value):
    return value.replace("/", "-") if value else ""


def parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except Exception:
        return None


# ------------------ Scoring ------------------ #

def calculate_class_score(horse):
    """Dummy scoring, replace with real formula"""
    return horse.get("merit", 0)


def calculate_final_score(horse):
    """Combine merit & class scores"""
    return horse.get("merit", 0)
