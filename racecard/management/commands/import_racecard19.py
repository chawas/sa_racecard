import os
import re
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from racecard.models import Race, Horse, Run, Ranking

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Import racecard HTML file and populate models"

    def add_arguments(self, parser):
        parser.add_argument("html_file", type=str, help="Path to HTML file")

    def handle(self, *args, **options):
        html_file = options["html_file"]
        self.stdout.write(f"\U0001F4C4 Processing: {html_file}")

        try:
            with open(html_file, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to open file: {e}"))
            return

        try:
            header_div = soup.find("div", class_="header_div")
            if not header_div:
                raise ValueError("❌ Could not find div.header_div")

            header_lines = list(header_div.stripped_strings)
            self.stdout.write(f"📋 Header lines found: {header_lines}")

            race_name = header_lines[0] if len(header_lines) > 0 else None
            race_distance = header_lines[1] if len(header_lines) > 1 else None
            race_class_merit = header_lines[2] if len(header_lines) > 2 else None
            self.stdout.write(f"📋 Race class merit: {race_class_merit}")

            race_info_td = soup.find("td", {"align": "center"})
            if not race_info_td:
                raise ValueError("❌ Could not find race info <td align='center'>")

            lines = list(race_info_td.stripped_strings)
            self.stdout.write(f"📋 Race info lines: {lines}")

            field = lines[0]
            date_str = lines[1]
            race_date = datetime.strptime(date_str, "%d/%m/%Y").date()

            race_no = int(race_info_td.find("div", class_="rev4").text.strip())
            race_time = race_info_td.find("div", class_="b1").text.strip()

            race, created = Race.objects.get_or_create(
                race_date=race_date,
                race_no=race_no,
                race_time=int(race_time.replace(":", "")),  # convert HH:MM to HHMM int
                field=field,
                name=race_name,
                distance=race_distance,
                race_class_merit=race_class_merit
            )

            if created:
                self.stdout.write(f"✅ Created Race: {field} #{race_no} on {race_date}")
            else:
                self.stdout.write(f"ℹ️ Race already exists: {field} #{race_no} on {race_date}")
                return  # Skip existing

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to import race: {e}"))
            return

        try:
            tables = soup.find_all("table")
            horses = []
            for i, table in enumerate(tables):
                if 'Horse:' in table.text:
                    tds = table.find_all("td")
                    number = tds[0].text.strip()
                    name = tds[1].text.strip()
                    blinkers = "b" in tds[2].text.lower()
                    age = tds[3].text.strip()
                    dob = None
                    try:
                        dob = datetime.strptime(tds[4].text.strip(), "%d/%m/%Y").date()
                    except:
                        pass
                    odds = tds[5].text.strip()
                    merit = None
                    try:
                        merit = int(tds[6].text.strip())
                    except:
                        pass

                    horse = Horse.objects.create(
                        race=race,
                        number=number,
                        name=name,
                        blinkers=blinkers,
                        age=age,
                        dob=dob,
                        odds=odds,
                        merit_rating=merit
                    )
                    horses.append(horse)
                    self.stdout.write(f"🐎 Imported Horse: {horse.name}")

                    # Parse runs (assume at i + 7)
                    if i + 7 < len(tables):
                        run_rows = tables[i + 7].find_all("tr", class_="small")
                        for row in run_rows:
                            cols = row.find_all("td")
                            if not cols or len(cols) < 9:
                                continue

                            date_cell = cols[0]
                            span = date_cell.find("span")
                            if span:
                                span.decompose()
                            run_date_str = date_cell.text.strip()
                            try:
                                run_date = datetime.strptime(run_date_str, "%d.%m.%y").date()
                            except:
                                continue

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
            self.stdout.write(self.style.ERROR(f"❌ Error during horse/run parsing: {e}"))
