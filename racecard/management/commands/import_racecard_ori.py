import os
import re
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from racecard.models4 import Horse, Run
from datetime import datetime

class Command(BaseCommand):
    help = "Import horse racecard HTML and save horses, races, and runs"

    def add_arguments(self, parser):
        parser.add_argument('html_path', type=str)

    def handle(self, *args, **kwargs):
        html_path = kwargs['html_path']
        print("🟢 Running import_racecard command...")

        if not os.path.exists(html_path):
            self.stderr.write(f"❌ File not found: {html_path}")
            return

        # Clean old data
        Horse.objects.all().delete()
        Run.objects.all().delete()

        with open(html_path, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        tables = soup.find_all("table")
        print(f"🔍 Found {len(tables)} tables in HTML")

        i = 0
        while i < len(tables):
            rows = tables[i].find_all("tr")
            first_row = [td.get_text(strip=True) for td in rows[0].find_all("td")] if rows else []

            # Skip if it doesn't look like a horse block
            if not first_row or not re.match(r"^\d+\s*/\s*\d+", first_row[0]):
                i += 1
                continue

            # Extract horse number, odds, and merit
            try:
                parts = [td.get_text(strip=True) for td in tables[i].find_all("td")]
                horse_no = int(parts[0])
                odds = parts[1]
                merit = int(parts[2])
            except:
                i += 1
                continue

            # Horse name + blinkers
            try:
                name_row = tables[i + 1].find("tr").find_all("td")
                name = name_row[0].get_text(strip=True)
                blinkers = name_row[1].get_text(strip=True) if len(name_row) > 1 else None
            except:
                name = "Unknown"
                blinkers = None

            # Age/Sex/Color + DOB
            try:
                info_row = tables[i + 2].find("tr").find_all("td")
                age_sex_color = info_row[0].get_text(strip=True)
                dob = None
                if len(info_row) > 1 and "dob:" in info_row[1]:
                    dob = datetime.strptime(info_row[1].split("dob:")[1].strip(), "%d %b %Y").date()
            except:
                age_sex_color = None
                dob = None

            # Save Horse
            horse = Horse.objects.create(
                horse_no=horse_no,
                name=name,
                blinkers=blinkers,
                age_sex_color=age_sex_color,
                dob=dob,
                merit=merit,
                odds=odds
            )

            # Parse past 4 runs (usually at i + 7)
            if i + 7 < len(tables):
                run_rows = tables[i + 7].find_all("tr", class_="small")
                for r in run_rows[-4:]:
                    tds = r.find_all("td")
                    if len(tds) < 21:
                        continue

                    try:
                        Run.objects.create(
                            horse=horse,
                            date=tds[0].get_text(strip=True),
                            position=tds[1].get_text(strip=True),
                            distance=int(tds[6].get_text(strip=True)),
                            jockey=tds[7].get_text(strip=True),
                            weight=float(tds[8].get_text(strip=True)),
                            merit_rating=tds[9].get_text(strip=True),
                            position_num=int(tds[12].get_text(strip=True)),
                            margin=float(tds[13].get_text(strip=True)),
                            time=tds[15].get_text(strip=True),
                            odds=tds[17].get_text(strip=True),
                            race_class=tds[4].get_text(strip=True),
                            going=tds[3].get_text(strip=True),
                            comment=tds[20].get_text(strip=True)
                        )
                    except Exception as e:
                        print(f"[⚠️] Skipping run due to error: {e}")

            i += 1

        print("✅ All horses and runs imported successfully.")
