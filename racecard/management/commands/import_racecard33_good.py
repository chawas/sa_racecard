"""
Training command: import the race header details (and horses) from a single
racecard HTML file and write them to the DB.

Run:
  python manage.py import_racecard path/to/file.html
  python manage.py import_racecard path/to/file.html --update

This prints detailed debug info at each step so you can see how parsing flows.
"""

import os
import re
from datetime import datetime, date, time

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from racecard.models import Race, Horse  # <-- import Horse too


# -------------------------
# Helpers
# -------------------------
def ensure_date(val):
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        for fmt in ("%Y-%m-%d", "%d %B %Y", "%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(val, fmt).date()
            except ValueError:
                pass
    raise ValueError(f"Cannot parse date from value: {val!r}")


def ensure_time(val):
    if isinstance(val, time):
        return val
    if isinstance(val, str):
        s = val.strip().replace(".", ":")
        if ":" in s:
            h, m = map(int, s.split(":")[:2])
        else:
            h, m = divmod(int(s), 100)
        return time(h, m)
    if isinstance(val, int):
        h, m = divmod(val, 100)
        return time(h, m)
    raise ValueError(f"Cannot parse time from value: {val!r}")


def _text(node, default=""):
    return node.get_text(strip=True) if node else default


class Command(BaseCommand):
    help = (
        "Import race header and horses from a racecard HTML file. "
        "Use --update to update existing DB rows."
    )

    # -------------------------
    # CLI arguments
    # -------------------------
    def add_arguments(self, parser):
        parser.add_argument("html_file", type=str, help="Path to a single racecard HTML file")
        parser.add_argument(
            "--update",
            action="store_true",
            dest="update",
            help="If set, update the existing Race (and Horses) with parsed values.",
        )

    # -------------------------
    # Header parsing
    # -------------------------
    @staticmethod
    def _parse_header_td(soup):
        td = soup.find("td", align="center")
        if not td:
            return {}

        lines = list(td.stripped_strings)
        result = {
            "lines": lines,
            "course": lines[0] if lines else None,
            "date_text": None,
            "race_date": None,
            "race_no": None,
            "race_time_text": None,
            "race_time_hhmm": None,
        }

        # Date detection (accept 25/07/2025 or 25/07/25)
        for text in lines[1:4]:
            clean = text.strip()
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", clean):
                parsed_date = datetime.strptime(clean, "%d/%m/%Y").date()
                result["date_text"] = clean
                result["race_date"] = parsed_date
                break
            if re.fullmatch(r"\d{2}/\d{2}/\d{2}", clean):
                parsed_date = datetime.strptime(clean, "%d/%m/%y").date()
                result["date_text"] = clean
                result["race_date"] = parsed_date
                break

        # Race number in <div class="rev4">
        rev4 = td.find("div", class_="rev4")
        if rev4:
            m = re.search(r"\d+", rev4.get_text(strip=True))
            if m:
                result["race_no"] = int(m.group())

        # Race time in <div class="b1">
        b1 = td.find("div", class_="b1")
        if b1:
            raw = b1.get_text(strip=True)
            result["race_time_text"] = raw
            normalized = raw.replace(".", ":")
            try:
                t = datetime.strptime(normalized, "%H:%M").time()
                result["race_time_hhmm"] = t.hour * 100 + t.minute
            except Exception:
                m2 = re.search(r"\b(\d{3,4})\b", raw)
                if m2:
                    try:
                        result["race_time_hhmm"] = int(m2.group(1))
                    except Exception:
                        result["race_time_hhmm"] = None

        return result

    @staticmethod
    def _parse_right_td_for_details(right_td):
        result = {
            "race_name": None,
            "race_distance": None,
            "race_class": None,
            "race_merit": None,
        }
        if not right_td:
            return result

        b2 = right_td.find("div", class_="b2")
        if b2:
            b2_lines = list(b2.stripped_strings)
            if b2_lines:
                result["race_name"] = b2_lines[0]
            if len(b2_lines) > 1:
                m = re.search(r"(\d+)\s*Metres", b2_lines[1], flags=re.I)
                if m:
                    result["race_distance"] = m.group(1)

        for text in (t.strip() for t in right_td.stripped_strings if t.strip()):
            low = text.lower()
            if any(k in low for k in (
                "class", "maiden", "merit rated", "benchmark", "handicap",
                "stakes", "conditions", "plate", "allowance", "apprentice",
                "novice", "graduation", "restricted"
            )):
                result["race_class"] = text
                m = re.search(r"Merit\s*Rated\s*(\d{1,3})", text, flags=re.I)
                if not m:
                    m = re.search(r"Benchmark\s*(\d{1,3})", text, flags=re.I)
                if not m:
                    m = re.search(r"\b(\d{2,3})\b", text)
                if m:
                    try:
                        result["race_merit"] = int(m.group(1))
                    except Exception:
                        result["race_merit"] = 0
                else:
                    result["race_merit"] = 0
                break

        return result

    # -------------------------
    # Horse parsing
    # -------------------------
    def _parse_horses(self, soup, race, update_existing: bool):
        """
        Parse horse blocks. We only consider tables that:
          - have border="border"
          - contain a <div class="b4"> with a numeric horse number
        """
        self.stdout.write("\n🔍 Extracting Horses...")
        created_or_updated = 0
        horse_tables = soup.select('table[border="border"]')

        for idx, table in enumerate(horse_tables, start=1):
            try:
                first_tr = table.find("tr")
                if not first_tr:
                    continue
                main_tds = first_tr.find_all("td", recursive=False)
                if len(main_tds) < 2:
                    continue

                # --- TD 0: number/odds/rating ---
                td0 = main_tds[0]
                num_div = td0.find("div", class_="b4")
                if not num_div:
                    # Not a horse row
                    continue
                try:
                    horse_no = int(_text(num_div))
                except Exception:
                    continue

                odds_el = td0.find("div", class_="b1")
                odds = _text(odds_el)

                merit_el = td0.find("span", class_="b1")
                horse_merit = None
                if merit_el:
                    m = re.search(r"\d+", merit_el.get_text())
                    if m:
                        horse_merit = int(m.group())

                # --- TD 1: name + age/blinkers ---
                td1 = main_tds[1] if len(main_tds) > 1 else None
                horse_name = ""
                blinkers = False
                age = ""

                if td1:
                    name_cell = td1.find("td", class_="b1")
                    horse_name = _text(name_cell) or _text(td1)
                    # Blinkers if "(B)" appears anywhere in the name block
                    block_text_upper = td1.get_text(" ", strip=True).upper()
                    blinkers = "(B" in block_text_upper

                    # Age e.g. "6 y. o. b g."
                    age_text = ""
                    for s in td1.stripped_strings:
                        if re.search(r"\by\.?\s*o\.?", s, flags=re.I):
                            age_text = s
                            break
                    m_age = re.search(r"\b(\d{1,2})\b", age_text)
                    age = m_age.group(1) if m_age else ""

                # --- Jockey / Trainer (nested table) ---
                # Look inside the current horse's table for any "div.itbld"
                itbld_divs = table.select("div.itbld")
                jockey, trainer = "", ""
                if len(itbld_divs) >= 1:
                    jockey = " ".join(itbld_divs[0].stripped_strings)
                if len(itbld_divs) >= 2:
                    trainer = " ".join(itbld_divs[1].stripped_strings)

                # --- Debug prints ---
                print(f"[DEBUG] Horse {horse_no}: name={horse_name}")
                print(f"[DEBUG]  -> Odds={odds}, Merit={horse_merit}, Blinkers={blinkers}, Age={age}")
                print(f"[DEBUG]  -> Jockey={jockey}, Trainer={trainer}")

                # Ensure safe field lengths
                age = (age or "")[:10]
                odds = (odds or "")[:20]

                # Upsert
                defaults = dict(
                    horse_name=horse_name,
                    blinkers=bool(blinkers),
                    age=age,
                    dob="",  # not present in provided markup
                    odds=odds,
                    horse_merit=horse_merit if horse_merit is not None else 0,
                    race_class=race.race_class or "",
                    trainer=trainer,
                    jockey=jockey,
                )
                obj, created = Horse.objects.update_or_create(
                    race=race, horse_no=horse_no, defaults=defaults
                )
                created_or_updated += 1
                self.stdout.write(
                    f"🐎 Horse {horse_no}: {horse_name} | "
                    f"Blinkers={blinkers} | Odds={odds or '-'} | "
                    f"Merit={defaults['horse_merit']} | "
                    f"Jockey={jockey or '-'} | Trainer={trainer or '-'}"
                )
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Skipping one table (idx {idx}) due to error: {e}"))

        self.stdout.write(self.style.SUCCESS(f"✅ Horses saved: {created_or_updated}"))
        return created_or_updated

    # -------------------------
    # Main handler
    # -------------------------
    def handle(self, *args, **options):
        html_file = options["html_file"]
        update_existing = options["update"]

        # Step 1: file existence
        self.stdout.write(f"\n[STEP 1] Checking file: {html_file}")
        if not os.path.exists(html_file):
            self.stdout.write(self.style.ERROR("❌ File not found. Aborting."))
            return
        self.stdout.write(self.style.SUCCESS("✅ File exists."))

        # Step 2: load HTML
        self.stdout.write("\n[STEP 2] Loading and parsing HTML...")
        with open(html_file, "r", encoding="utf-8") as fh:
            soup = BeautifulSoup(fh, "html.parser")
        self.stdout.write(self.style.SUCCESS("✅ HTML loaded into BeautifulSoup."))

        # Step 3: parse header (left) td
        self.stdout.write("\n[STEP 3] Extracting header block (course/date/no/time)...")
        header = self._parse_header_td(soup)

        self.stdout.write(f"  • Raw header lines: {header.get('lines')}")
        self.stdout.write(f"  • Course/Field: {header.get('course')!r}")
        self.stdout.write(f"  • Date text: {header.get('date_text')!r} -> Parsed: {header.get('race_date')!r}")
        self.stdout.write(f"  • Race No (rev4): {header.get('race_no')!r}")
        self.stdout.write(f"  • Race time raw: {header.get('race_time_text')!r} -> HHMM: {header.get('race_time_hhmm')!r}")

        essential_ok = all([
            bool(header.get("course")),
            bool(header.get("race_date")),
            header.get("race_no") is not None,
        ])
        if not essential_ok:
            self.stdout.write(self.style.ERROR("❌ Missing essential header info (course/date/race_no). Aborting."))
            return
        self.stdout.write(self.style.SUCCESS("✅ Header looks good."))

        # Step 4: parse right td for name/distance/class/merit
        self.stdout.write("\n[STEP 4] Extracting race details (name/distance/class/merit)...")
        left_td = soup.find("td", align="center")
        right_td = left_td.find_next_sibling("td") if left_td else None
        details = self._parse_right_td_for_details(right_td)

        self.stdout.write(f"  • race_name: {details.get('race_name')!r}")
        self.stdout.write(f"  • race_distance: {details.get('race_distance')!r}")
        self.stdout.write(f"  • race_class: {details.get('race_class')!r}")
        self.stdout.write(f"  • race_merit: {details.get('race_merit')!r}")
        self.stdout.write(self.style.SUCCESS("✅ Details extracted."))

        # Step 5: prepare DB fields (match your Race model fields)
        race_date = ensure_date(header["race_date"])
        race_no = int(header["race_no"])
        race_time_obj = ensure_time(header["race_time_hhmm"])  # -> datetime.time
        race_field = header["course"].strip()
        race_name = details.get("race_name") or ""
        race_distance = details.get("race_distance") or ""
        race_class = details.get("race_class") or ""
        race_merit = details.get("race_merit") or 0

        self.stdout.write("\n[STEP 5] Prepared DB values:")
        self.stdout.write(f"  • race_date={race_date}, race_no={race_no}, race_time={race_time_obj}")
        self.stdout.write(f"  • race_field={race_field!r}, race_name={race_name!r}")
        self.stdout.write(f"  • race_distance={race_distance!r}, race_class={race_class!r}, race_merit={race_merit!r}")

        # Step 6: write Race to DB
        self.stdout.write("\n[STEP 6] Writing Race to database...")
        try:
            race, created = Race.objects.get_or_create(
                race_date=race_date,
                race_no=race_no,
                race_field=race_field,
                defaults={
                    "race_time": race_time_obj,
                    "race_name": race_name,
                    "race_distance": race_distance,
                    "race_class": race_class,
                    "race_merit": race_merit,
                },
            )

            if not created and update_existing:
                race.race_time = race_time_obj
                race.race_name = race_name
                race.race_distance = race_distance
                race.race_class = race_class
                race.race_merit = race_merit
                race.save()
                self.stdout.write(self.style.SUCCESS("🔄 Updated existing Race (because --update was used)."))
            elif created:
                self.stdout.write(self.style.SUCCESS("✅ Created new Race row."))
            else:
                self.stdout.write("ℹ️ Race already exists (same date/no/field).")

            self.stdout.write(
                f"  id={race.id} | date={race.race_date} | no={race.race_no} | "
                f"field={race.race_field} | time={race.race_time} | "
                f"name={race.race_name!r} | distance={race.race_distance!r} | "
                f"class={race.race_class!r} | merit={race.race_merit!r}"
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ DB write failed (Race): {e}"))
            return

        # Step 7: write Horses to DB
        self._parse_horses(soup, race, update_existing)

        self.stdout.write(self.style.SUCCESS("\n✅ Done. Racecard import finished."))
