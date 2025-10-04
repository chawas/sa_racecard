import os
import re
from datetime import datetime
from django.core.management.base import BaseCommand
from bs4 import BeautifulSoup
from racecard.models import Race, Horse, Run, Ranking


class Command(BaseCommand):
    help = "Import racecard HTML and populate Race, Horse, Run, Ranking"

    def add_arguments(self, parser):
        parser.add_argument('html_file', type=str)

    def handle(self, *args, **options):
        file_path = options['html_file']
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"❌ File not found: {file_path}"))
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        try:
            # --- Parse header section ---
            header_cell = soup.find("td", align="center")
            if not header_cell:
                self.stdout.write(self.style.ERROR("❌ No header cell found."))
                return

            lines = list(header_cell.stripped_strings)
            self.stdout.write(f"📋 Header lines: {lines}")
            try:
                field = lines[0]
                date_str = lines[1]
                race_no = int(lines[2])
                race_time = lines[3]
                race_date = datetime.strptime(date_str, "%d/%m/%Y").date()
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed to parse header: {e}"))
                return

            # --- Parse race detail section ---
            detail_cell = soup.find_all("td")[1]
            detail_lines = list(detail_cell.stripped_strings)
            self.stdout.write(f"📋 Detail lines: {detail_lines}")
            try:
                race_name = detail_lines[0]
                match_dist = re.search(r"(\d+)\s*Metres", detail_lines[1])
                race_distance = int(match_dist.group(1)) if match_dist else 0
                race_class = detail_lines[2]
                match_merit = re.search(r"\d+", race_class)
                race_merit = int(match_merit.group()) if match_merit else None
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed to parse race details: {e}"))
                return

            # --- Create or skip race ---
            race, created = Race.objects.get_or_create(
                field=field,
                race_no=race_no,
                race_date=race_date,
                defaults={
                    "race_time": race_time,
                    "race_name": race_name,
                    "race_distance": race_distance,
                    "race_class": race_class,
                    "race_merit": race_merit,
                }
            )
            if not created:
                self.stdout.write(self.style.WARNING("⚠️ Race already exists, skipping import."))
                return
            else:
                self.stdout.write(self.style.SUCCESS(f"🏇 Added Race: {race}"))

            # --- Parse horses ---
            horses = []
            tables = soup.find_all("table")
            for i, table in enumerate(tables):
                rows = table.find_all("tr", class_="small")
                for row in rows:
                    cols = row.find_all("td")
                    if not cols or len(cols) < 6:
                        continue
                    try:
                        number = int(cols[0].text.strip())
                        name = cols[1].text.strip()
                        blinkers = 'b' in name.lower()
                        name = name.replace("(b)", "").replace("(B)", "").strip()
                        age = cols[2].text.strip()
                        dob = cols[3].text.strip()
                        odds = cols[4].text.strip()
                        merit_rating = int(cols[5].text.strip())

                        horse = Horse.objects.create(
                            race=race,
                            number=number,
                            name=name,
                            blinkers=blinkers,
                            age=age,
                            dob=dob,
                            odds=odds,
                            merit_rating=merit_rating
                        )
                        horses.append(horse)
                        self.stdout.write(f"🐎 Added Horse: {name} (No: {number})")
                    except Exception as e:
                        self.stdout.write(self.style.WARNING(f"⚠️ Skipping horse row due to error: {e}"))

                # --- Parse past runs (table is 7 steps ahead) ---
                if i + 7 < len(tables):
                    run_rows = tables[i + 7].find_all("tr", class_="small")
                    for row in run_rows:
                        cols = row.find_all("td")
                        if not cols or len(cols) < 9:
                            continue
                        try:
                            date_cell = cols[0]
                            span = date_cell.find("span")
                            if span:
                                span.decompose()
                            run_date_str = date_cell.text.strip()
                            run_date = datetime.strptime(run_date_str, "%d.%m.%y").date()

                            surface = cols[3].text.strip()
                            distance = cols[6].text.strip()
                            run_class = cols[7].text.strip()
                            weight = cols[8].text.strip()

                            Run.objects.create(
                                horse=horse,
                                date=run_date,
                                surface=surface,
                                distance=distance,
                                race_class=run_class,
                                weight=weight
                            )
                            self.stdout.write(f"📅 Added Run: {run_date} for {horse.name}")
                        except Exception as e:
                            self.stdout.write(self.style.WARNING(f"⚠️ Skipping run due to error: {e}"))

            # --- Score and rank horses ---
            def score_horse(h):
                score = 0
                if h.merit_rating:
                    score += h.merit_rating
                if h.blinkers:
                    score += 5
                return score

            scored = [(h, score_horse(h)) for h in horses]
            scored.sort(key=lambda x: x[1], reverse=True)

            for idx, (h, s) in enumerate(scored, start=1):
                Ranking.objects.create(horse=h, score=s, class_score=None)
                self.stdout.write(f"🥇 Rank {idx}: {h.name} (Score: {s})")

            self.stdout.write(self.style.SUCCESS("✅ Import complete."))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Fatal error: {e}"))
