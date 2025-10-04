"""
Training command: import only the race-level (header) details from a single
racecard HTML file and write them to the Race table.

Run:
  python manage.py import_racecard_race_details path/to/file.html
  python manage.py import_racecard_race_details path/to/file.html --update

This prints detailed debug info at each step so you can see how parsing flows.
"""

import os
import re
from datetime import datetime, date, time

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from racecard.models import Race, Horse




def ensure_date(val):
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        try:
            return datetime.strptime(val, "%Y-%m-%d").date()
        except ValueError:
            pass
        try:
            return datetime.strptime(val, "%d %B %Y").date()
        except ValueError:
            pass
    raise ValueError(f"Cannot parse date from value: {val}")


def ensure_time(val):
    if isinstance(val, time):
        return val
    if isinstance(val, str):
        val = val.strip()
        if ":" in val:
            h, m = map(int, val.split(":"))
        else:
            h, m = divmod(int(val), 100)
        return time(h, m)
    if isinstance(val, int):
        h, m = divmod(val, 100)
        return time(h, m)
    raise ValueError(f"Cannot parse time from value: {val}")


class Command(BaseCommand):
    help = (
        "Import only the race (header) details from a racecard HTML file and "
        "create or update a Race row. Use --update to force update if race exists."
    )

    # -------------------------
    # CLI arguments
    # -------------------------
    def add_arguments(self, parser):
        parser.add_argument(
            "html_file",
            type=str,
            help="Path to a single racecard HTML file",
        )
        parser.add_argument(
            "--update",
            action="store_true",
            dest="update",
            help="If set, update the existing Race with parsed values.",
        )
    


   
    # -------------------------
    # Helper parsing functions
    # -------------------------
    @staticmethod
    def _parse_header_td(soup):
        """
        Locate the top-left <td align="center"> which usually contains:
          - course/field (text)
          - date (dd/mm/YYYY or dd/mm/YY)
          - race_no (in <div class='rev4'>)
          - race_time (in <div class='b1'>)

        Return a dict with keys:
          lines, course, date_text, race_date, race_no, race_time_text, race_time_hhmm
        """
        td = soup.find("td", align="center")
        if not td:
            return {}

        # Collect visible text lines in order
        lines = list(td.stripped_strings)

        result = {
            "lines": lines,
            "course": None,
            "date_text": None,
            "race_date": None,
            "race_no": None,
            "race_time_text": None,
            "race_time_hhmm": None,  # integer like 1640
        }

        # Course name is usually the first line
        if lines:
            result["course"] = lines[0]
            print(result)

        # Date detection (accept 25/07/2025 or 25/07/25)
        for text in lines[1:4]:  # be defensive; scan the next few items
            clean_text = text.strip()  # remove leading/trailing spaces and \n
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", clean_text):
                parsed_date = datetime.strptime(clean_text, "%d/%m/%Y").date()
                # Convert from string "13/08/2025" to datetime.date object
                #parsed_date = datetime.strptime(parsed_date, "%d/%m/%Y").date()

                # Debug: show both forms
                print(f"[DATE DETECTED] {parsed_date} -> tuple: {(parsed_date.year, parsed_date.month, parsed_date.day)}")
                result["date_text"] = clean_text
                result["race_date"] = parsed_date  # Django DateField friendly
                break

            if re.fullmatch(r"\d{2}/\d{2}/\d{2}", clean_text):
                parsed_date = datetime.strptime(clean_text, "%d/%m/%y").date()
                result["date_text"] = clean_text
                result["race_date"] = parsed_date  # Django DateField friendly

                # Debug: also print tuple form
                print(f"[DATE DETECTED] '{parsed_date}' -> tuple: {(parsed_date.year, parsed_date.month, parsed_date.day)}")
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

            # Normalize "16.40" -> "16:40", then parse; fall back to digits
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
        """
        Given the right-hand <td> (sibling of the header td), extract:
          - race_name         (first line in <div class='b2'>)
          - race_distance     (digits before 'Metres')
          - race_class        (a line containing class/handicap information)
          - race_merit        (a 2-3 digit number in the class line: Merit Rated 84, Benchmark 80, etc.)

        Return a dict with keys: race_name, race_distance, race_class, race_merit
        """
        result = {
            "race_name": None,
            "race_distance": None,
            "race_class": None,
            "race_merit": None,
        }
        if not right_td:
            return result

        # First try to read <div class="b2"> lines
        b2 = right_td.find("div", class_="b2")
        if b2:
            b2_lines = list(b2.stripped_strings)
            if b2_lines:
                result["race_name"] = b2_lines[0]
            if len(b2_lines) > 1:
                m = re.search(r"(\d+)\s*Metres", b2_lines[1], flags=re.I)
                if m:
                    result["race_distance"] = m.group(1)

        # Now scan all text chunks in right_td for a "class-like" line
        for text in (t.strip() for t in right_td.stripped_strings if t.strip()):
            low = text.lower()
            if any(k in low for k in ("class", "maiden", "merit rated", "benchmark", "handicap", "stakes")):
                result["race_class"] = text

                # Try to extract merit/rating number
                m = re.search(r"Merit\s*Rated\s*(\d{1,3})", text, flags=re.I)
                if not m:
                    m = re.search(r"Benchmark\s*(\d{1,3})", text, flags=re.I)
                if not m:
                    m = re.search(r"\b(\d{2,3})\b", text)  # fallback
                if m:
                    try:
                        result["race_merit"] = int(m.group(1))
                    except Exception:
                        result["race_merit"] = 0  # default to 0 if can't parse
                else:
                    result["race_merit"] = 0  # no merit found, set to 0
                break

        return result



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
        print(f"[DEBUG] race_date type: {type(race_date)}, value: {race_date}")
        race_no = int(header["race_no"])
        race_time_hhmm = ensure_time(header["race_time_hhmm"]) or 0
        #race_time_hhmm = header.get("race_time_hhmm") or 0  # integer (HHMM)
        race_field = header["course"].strip()
        race_name = details.get("race_name") or ""
        race_distance = details.get("race_distance") or ""
        race_class = details.get("race_class") or ""
        race_merit = details.get("race_merit") or 0

        self.stdout.write("\n[STEP 5] Prepared DB values:")
        self.stdout.write(f"  • race_date={race_date}, race_no={race_no}, race_time={race_time_hhmm}")
        self.stdout.write(f"  • race_field={race_field!r}, race_name={race_name!r}")
        self.stdout.write(f"  • race_distance={race_distance!r}, race_class={race_class!r}, race_merit={race_merit!r}")

        # Step 6: write to DB
        self.stdout.write("\n[STEP 6] Writing to database (Race table)...")
        try:
            race, created = Race.objects.get_or_create(
                race_date=race_date,
                race_no=race_no,
                race_field=race_field,
                defaults={
                    "race_time": race_time_hhmm,
                    "race_name": race_name,
                    "race_distance": race_distance,
                    "race_class": race_class,
                    "race_merit": race_merit,
                },
            )

            if created:
                self.stdout.write(self.style.SUCCESS("✅ Created new Race row."))
            else:
                self.stdout.write("ℹ️ Race already exists (same date/no/field).")
                if update_existing:
                    race.race_time = race_time_hhmm
                    race.race_name = race_name
                    race.race_distance = race_distance
                    race.race_class = race_class
                    race.race_merit = race_merit
                    race.save()
                    self.stdout.write(self.style.SUCCESS("🔄 Updated existing Race (because --update was used)."))

            # Final confirmation print
            self.stdout.write("\n[STEP 7] Final saved record:")
            self.stdout.write(
                f"  id={race.id} | date={race.race_date} | no={race.race_no} | "
                f"field={race.race_field} | time={race.race_time} | "
                f"name={race.race_name!r} | distance={race.race_distance!r} | "
                f"class={race.race_class!r} | merit={race.race_merit!r}"
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ DB write failed: {e}"))
            return

        #self.stdout.write(self.style.SUCCESS("\n✅ Done. Race header import finished."))



        # =========================
        #   PARSE HORSES
        # =========================


        self.stdout.write("\n🔍 Extracting Horses...")
        horses = []

        # Find only the horse detail tables
        horse_tables = soup.find_all("table", attrs={"border": "border"})

        for table in horse_tables:
            try:
                tds = table.find_all("td")

                # Horse No + Merit Rating
                horse_no = int(tds[0].find("div", class_="b4").get_text(strip=True))
                merit_rating = int(tds[0].find("span", class_="b1").get_text(strip=True))

                # Horse Name
                horse_name = tds[1].find("td", class_="b1").get_text(strip=True)
                blinkers = '(B)' in horse_name.upper()
                horse_name = horse_name.replace("(B)", "").replace("(b)", "").strip()

                # Age/Sex/Colour
                age_info = tds[2].get_text(strip=True)

                # Weight
                weight = tds[3].get_text(strip=True)

                # Trainer & Jockey
                trainer_div = tds[4].find_all("div", class_="itbld")
                trainer = trainer_div[0].get_text(strip=True) if len(trainer_div) > 0 else ""
                jockey = trainer_div[1].get_text(strip=True) if len(trainer_div) > 1 else ""

                # Create Horse entry
                horse = Horse.objects.create(
                    race=race,
                    horse_no=horse_no,
                    horse_name=horse_name,
                    blinkers=blinkers,
                    age=age_info,
                    dob="",  # not available in HTML
                    odds=None,  # not found in provided snippet
                    horse_merit=merit_rating if merit_rating else 0,
                    race_class=race.race_class,
                    trainer=trainer,
                    jockey=jockey
                )
                horses.append(horse)
                self.stdout.write(f"🐎 Horse {horse_no}: {horse_name}, Trainer: {trainer}, Jockey: {jockey}, Merit: {merit_rating}")

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Skipping table due to error: {e}"))


        self.stdout.write(self.style.SUCCESS("🎯 Racecard import completed!"))
