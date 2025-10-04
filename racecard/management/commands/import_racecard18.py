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
        self.stdout.write(f"📄 Processing: {html_file}")

        try:
            with open(html_file, "r", encoding="utf-8") as f:
                soup = BeautifulSoup(f, "html.parser")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to open file: {e}"))
            return

        try:
            race_info_td = soup.find("td", {"align": "center"})
            if race_info_td is None:
                raise ValueError("❌ Could not find race info <td align='center'>")

            lines = list(race_info_td.stripped_strings)
            field = lines[0]  # Fairview Polytrack
            date_str = lines[1]  # 25/07/2025
            race_date = datetime.strptime(date_str, "%d/%m/%Y").date()

            race_no = race_info_td.find("div", class_="rev4").text.strip()
            race_time = race_info_td.find("div", class_="b1").text.strip()

            race, created = Race.objects.get_or_create(
                race_date=race_date,
                race_no=int(race_no),
                race_time=int(race_time),
                field=field
            )

            if created:
                self.stdout.write(f"✅ Created Race: {field} #{race_no} on {race_date}")
            else:
                self.stdout.write(f"ℹ️ Race already exists: {field} #{race_no} on {race_date}")
                return  # Skip to avoid duplicates

        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Failed to import race from {html_file}: {e}"))
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
                    except Exception:
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

                            # Extract and clean date (remove span if exists)
                            date_cell = cols[0]
                            span = date_cell.find("span")
                            if span:
                                span.decompose()
                            run_date_str = date_cell.text.strip()
                            try:
                                run_date = datetime.strptime(run_date_str, "%d.%m.%y").date()
                            except:
                                continue  # Skip if bad date

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

            # Score and rank
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
