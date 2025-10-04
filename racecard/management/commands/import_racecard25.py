# racecard/management/commands/import_racecard.py
import re
from datetime import datetime
from bs4 import BeautifulSoup

from django.core.management.base import BaseCommand
from django.db import transaction

from racecard.models import Race, Horse, Run  # adjust imports if model names differ


class Command(BaseCommand):
    help = "Import a single racecard HTML file (race + horses + up to 4 past runs each)."

    def add_arguments(self, parser):
        parser.add_argument("path", type=str, help="Path to the racecard HTML file to import")

    # ---------- Helpers ----------
    @staticmethod
    def _time_to_hhmm_int(time_text):
        """Convert '16.43' or '16:43' to integer 1643. Return None if can't parse."""
        if not time_text:
            return None
        time_text = time_text.strip()
        parts = re.split(r"[.:]", time_text)
        if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
            hh = int(parts[0])
            mm = int(parts[1][:2])  # in case of weird chars
            if 0 <= hh < 24 and 0 <= mm < 60:
                return hh * 100 + mm
        digits = re.sub(r"\D", "", time_text)
        return int(digits) if digits else None

    @staticmethod
    def _parse_run_date(text):
        """Find and parse date in forms dd.mm.yy, dd.mm.yyyy or dd/mm/yyyy. Return date or None."""
        if not text:
            return None
        text = text.strip()
        # common patterns: 25.03.22  or 25.03.2022 or 25/03/2022
        m = re.search(r"(\d{2}[./]\d{2}[./]\d{2,4})", text)
        if not m:
            return None
        s = m.group(1)
        for fmt in ("%d.%m.%y", "%d.%m.%Y", "%d/%m/%Y"):
            try:
                return datetime.strptime(s, fmt).date()
            except ValueError:
                continue
        return None

    def _find_next_runs_table(self, start_row):
        """
        Locate the nearest following <table> that looks like a runs table:
        a runs table typically contains <tr class="small"> rows where first <td> has a date.
        We try a small number of tables forward.
        """
        tbl = start_row.find_next("table")
        attempts = 0
        while tbl and attempts < 12:
            rows = tbl.find_all("tr", class_="small")
            if rows:
                # check first row first cell contains a date-like token
                first_td = rows[0].find("td")
                if first_td:
                    txt = first_td.get_text(" ", strip=True)
                    if re.search(r"\d{2}[./]\d{2}[./]\d{2,4}", txt):
                        return tbl
            tbl = tbl.find_next("table")
            attempts += 1
        return None

    def _extract_race_details_from_soup(self, soup):
        """
        Extracts top-level race info: course (race_field), date, race_no, race_time,
        race_name, race_distance, race_class_text, race_merit (int if exists).
        """
        top_left_td = soup.find("td", align="center")
        if not top_left_td:
            raise ValueError("Could not find <td align='center'> with race header information.")

        header_lines = list(top_left_td.stripped_strings)
        self.stdout.write(f"\n📋 Header lines: {header_lines}")

        race_field = header_lines[0] if len(header_lines) > 0 else "Unknown"
        race_date = None
        for t in header_lines:
            m = re.search(r"\d{2}/\d{2}/\d{4}", t)
            if m:
                race_date = datetime.strptime(m.group(), "%d/%m/%Y").date()
                break

        # race number
        rev4_div = top_left_td.find("div", class_="rev4")
        race_no = None
        if rev4_div:
            txt = rev4_div.get_text(strip=True)
            if txt.isdigit():
                race_no = int(txt)

        # race time
        b1_div = top_left_td.find("div", class_="b1")
        race_time = None
        if b1_div:
            race_time = self._time_to_hhmm_int(b1_div.get_text(strip=True))

        # right td (distance / race name / class)
        right_td = top_left_td.find_next_sibling("td")
        race_name = None
        race_distance = None
        race_class_text = None
        race_merit = None

        if right_td:
            b2_div = right_td.find("div", class_="b2")
            if b2_div:
                b2_lines = list(b2_div.stripped_strings)
                if len(b2_lines) >= 1:
                    race_name = b2_lines[0].strip()
                if len(b2_lines) >= 2:
                    # extract digits for distance
                    m = re.search(r"(\d+)\s*Metres", b2_lines[1], flags=re.I)
                    if m:
                        race_distance = m.group(1)

            # find line containing 'Class', 'Merit Rated', 'Benchmark', 'Handicap' etc
            for t in right_td.stripped_strings:
                if any(x in t for x in ("Class", "Merit Rated", "Benchmark", "Handicap", "Rated")):
                    race_class_text = t.strip()
                    m2 = re.search(r"(\d{2,3})", race_class_text)
                    if m2:
                        race_merit = int(m2.group(1))
                    break

        # Debug prints
        self.stdout.write(f"✅ Field: {race_field}, Date: {race_date}, Race No: {race_no}, Time: {race_time}")
        self.stdout.write(f"\n🔍 Detail lines: b2 -> name:'{race_name}', distance:'{race_distance}', class:'{race_class_text}', merit:{race_merit}")

        return {
            "race_field": race_field,
            "race_date": race_date,
            "race_no": race_no,
            "race_time": race_time,
            "race_name": race_name,
            "race_distance": race_distance,
            "race_class_text": race_class_text,
            "race_merit": race_merit,
        }

    # ---------- Main ----------
    def handle(self, *args, **options):
        path = options.get("path")
        if not path:
            self.stdout.write(self.style.ERROR("Missing path argument."))
            return

        self.stdout.write(f"\n📂 Loading racecard file: {path}")
        try:
            with open(path, "r", encoding="utf-8") as f:
                html = f.read()
                soup = BeautifulSoup(html, "html.parser")
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"❌ Failed to open/read file: {exc}"))
            return

        # extract race details
        try:
            rd = self._extract_race_details_from_soup(soup)
        except Exception as exc:
            self.stdout.write(self.style.ERROR(f"❌ Failed to extract race header: {exc}"))
            return

        # basic sanity checks
        if rd["race_date"] is None:
            self.stdout.write(self.style.ERROR("❌ Could not determine race date. Aborting."))
            return
        if rd["race_no"] is None:
            self.stdout.write(self.style.ERROR("❌ Could not determine race number (rev4). Aborting."))
            return

        # create race (use get_or_create and defaults)
        defaults = {
            "race_time": rd["race_time"] or 0,
            "race_name": rd["race_name"] or "",
            "race_distance": rd["race_distance"] or "",
            "race_class": rd["race_class_text"] or "",
            "race_merit": rd["race_merit"],
        }

        race, created = Race.objects.get_or_create(
            race_date=rd["race_date"],
            race_no=rd["race_no"],
            race_field=rd["race_field"],
            defaults=defaults,
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"🏇 Created Race: {race.race_date} - R{race.race_no} - {race.race_field}"))
        else:
            self.stdout.write(self.style.WARNING(f"ℹ️ Race already exists: {race}. Clearing horses/runs for reimport."))
            # delete related Horses (will cascade run rows if using FK cascade)
            Horse.objects.filter(race=race).delete()

        # Now parse horses and, immediately after each horse, attach up to 4 past runs
        rows = soup.find_all("tr", class_="small")
        self.stdout.write(f"\n🔍 Found {len(rows)} 'tr.small' rows (both horses and runs mixed).")

        imported_horses = []
        for idx, row in enumerate(rows):
            cols = row.find_all("td")
            if not cols or len(cols) < 2:
                # skip empty or malformed
                continue

            first_txt = cols[0].get_text(" ", strip=True)
            # Identify horse rows: first column starts with a number only (horse_no)
            mnum = re.match(r"^\s*(\d+)\b", first_txt)
            if not mnum:
                # not a horse row (likely run row or header)
                continue

            # Basic heuristics: second col should be horse name (not a date)
            name_txt = cols[1].get_text(" ", strip=True)
            # skip if second column looks like a run date
            if self._parse_run_date(name_txt):
                continue

            try:
                horse_no = int(mnum.group(1))
            except Exception:
                self.stdout.write(self.style.WARNING(f"⚠️ Could not parse horse number from '{first_txt}', skipping row {idx}."))
                continue

            # Now extract horse fields defensively
            horse_name = name_txt
            blinkers = "(b)" in horse_name.lower() or "(B)" in horse_name
            horse_name = horse_name.replace("(b)", "").replace("(B)", "").strip()

            age = cols[2].get_text(" ", strip=True) if len(cols) > 2 else None
            dob = cols[3].get_text(" ", strip=True) if len(cols) > 3 else None
            odds = cols[4].get_text(" ", strip=True) if len(cols) > 4 else None
            merit_raw = cols[5].get_text(" ", strip=True) if len(cols) > 5 else ""
            merit_match = re.search(r"\d+", merit_raw)
            merit = int(merit_match.group()) if merit_match else None

            # trainer/jockey might appear in additional rows; try to pick them if present in the same row
            trainer = None
            jockey = None
            if len(cols) > 6:
                trainer = cols[6].get_text(" ", strip=True)
            if len(cols) > 7:
                jockey = cols[7].get_text(" ", strip=True)

            # Create Horse
            try:
                horse = Horse.objects.create(
                    race=race,
                    horse_no=horse_no,
                    name=horse_name,
                    blinkers=blinkers,
                    age=age,
                    dob=dob,
                    merit=merit,
                    odds=odds,
                    race_class=None,  # optionally fill from context if you want
                    trainer=trainer if trainer else None,
                    jockey=jockey if jockey else None,
                )
                imported_horses.append(horse)
                self.stdout.write(f"🐎 Horse {horse_no}: {horse_name}, Blinkers: {blinkers}, Merit: {merit}")
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Failed to create Horse {horse_no}/{horse_name}: {e}"))
                continue

            # Immediately find the runs table for THIS horse and extract up to 4 runs
            runs_table = self._find_next_runs_table(row)
            if not runs_table:
                self.stdout.write("  ℹ️ No runs table found for this horse (continuing).")
                continue

            run_rows = runs_table.find_all("tr", class_="small")
            self.stdout.write(f"  📜 Found {len(run_rows)} run rows for horse {horse_no} (will take up to 4).")
            added_runs = 0
            for r_i, run_row in enumerate(run_rows):
                if added_runs >= 4:
                    break
                run_cols = run_row.find_all("td")
                if not run_cols or len(run_cols) < 7:
                    continue

                # Clean date cell (strip any <span> like (11) marker)
                date_cell = run_cols[0]
                span = date_cell.find("span")
                if span:
                    span.decompose()
                run_date_txt = date_cell.get_text(" ", strip=True)
                run_date = self._parse_run_date(run_date_txt)
                if not run_date:
                    self.stdout.write(self.style.WARNING(f"    ⚠️ Skipping run with invalid date format: '{run_date_txt}'"))
                    continue

                # Map columns to the Run model fields as best we can:
                # Used indices: position (1), margin (2), distance (6), race_class (7 if present)
                position = run_cols[1].get_text(" ", strip=True) if len(run_cols) > 1 else ""
                margin = run_cols[2].get_text(" ", strip=True) if len(run_cols) > 2 else ""
                distance_txt = run_cols[6].get_text(" ", strip=True) if len(run_cols) > 6 else ""
                run_class_txt = run_cols[7].get_text(" ", strip=True) if len(run_cols) > 7 else ""

                try:
                    Run.objects.create(
                        horse=horse,
                        run_date=run_date,
                        position=position,
                        margin=margin,
                        distance=distance_txt,
                        race_class=run_class_txt or None,
                    )
                    added_runs += 1
                    self.stdout.write(f"    ✅ Added Run: {run_date} | Pos:{position} | Dist:{distance_txt}")
                except Exception as e:
                    self.stdout.write(self.style.WARNING(f"    ⚠️ Skipping run due to error: {e}"))
                    continue

        self.stdout.write(self.style.SUCCESS("\n✅ Import finished."))
