import os
import re
from datetime import datetime
from bs4 import BeautifulSoup

from django.core.management.base import BaseCommand
from racecard.models import Race, Horse


def extract_race_class_and_rating(text):
    """Extract race class and rating band from the race description."""
    text = text.replace('&nbsp;', ' ').replace('\n', ' ').strip()
    
    class_match = re.search(r'(Class\s+\d+|Merit Rated\s+\d+|[A-Z]\s+Stakes|[A-Z][\w\s]+Hcp)', text)
    race_class = class_match.group(0).strip() if class_match else None

    rating_match = re.search(r'Benchmark\s*\d+', text)
    rating_band = rating_match.group(0).strip() if rating_match else None

    return race_class, rating_band


class Command(BaseCommand):
    help = "Import a racecard HTML file and populate the database."

    def add_arguments(self, parser):
        parser.add_argument('html_file', type=str, help='Path to the racecard HTML file')

    def handle(self, *args, **kwargs):
        html_file = kwargs['html_file']

        if not os.path.exists(html_file):
            self.stdout.write(self.style.ERROR(f"File not found: {html_file}"))
            return

        # Extract metadata from filename
        filename = os.path.basename(html_file)
        match = re.match(r'(?P<date>\d{8})_(?P<race_no>\d+)_+(?P<field>.+)\.html', filename)

        if not match:
            self.stdout.write(self.style.ERROR("Filename format invalid. Expected: YYYYMMDD_raceNo_field.html"))
            return

        field = match.group('field').capitalize()
        race_date = datetime.strptime(match.group('date'), "%Y%m%d").date()
        race_no = int(match.group('race_no'))

        # Read HTML content
        with open(html_file, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        # --- Extract Race Description Block ---
        divs = soup.find_all("div", class_="b2")
        race_info_text = ' '.join([div.get_text(separator=' ', strip=True) for div in divs])
        class_and_rating_text = soup.get_text()

        # Extract distance (e.g., "1400 Metres")
        dist_match = re.search(r'(\d+)\s*Metres', race_info_text)
        distance = int(dist_match.group(1)) if dist_match else 0

        # Extract class and rating
        race_class, rating_band = extract_race_class_and_rating(class_and_rating_text)

        # Avoid duplicates
        race, created = Race.objects.get_or_create(
            field=field,
            race_date=race_date,
            race_no=race_no,
            defaults={
                "distance": distance,
                "race_class": race_class or "",
                "rating_band": rating_band or "",
            }
        )

        if not created:
            self.stdout.write(self.style.WARNING(f"Race already exists: {race}"))
            return
        else:
            self.stdout.write(self.style.SUCCESS(f"✅ Created Race: {field} R{race_no} on {race_date}"))

        # Parse horses
        tables = soup.find_all('tr', class_='small')
        self.stdout.write(f"Found {len(tables)} horses.")

        for i, row in enumerate(tables):
            cols = row.find_all('td')
            if len(cols) < 8:
                continue

            try:
                horse_no = int(cols[0].text.strip())

                name = cols[1].text.strip()
                blinkers = '(B)' in name or 'B' in name
                name = name.replace('(B)', '').strip()

                age = cols[2].text.strip()
                dob = cols[3].text.strip()
                odds = cols[4].text.strip()

                # Extract clean integer merit (e.g. from '{75}', '(83)', or '79')
                merit_raw = cols[5].text.strip()
                match = re.search(r'\d+', merit_raw)
                merit = int(match.group()) if match else None

                trainer = cols[6].text.strip()
                jockey = cols[7].text.strip()

                Horse.objects.create(
                    race=race,
                    horse_no=horse_no,
                    name=name,
                    blinkers=blinkers,
                    age=age,
                    dob=dob,
                    odds=odds,
                    merit=merit,
                    trainer=trainer,
                    jockey=jockey,
                )

                self.stdout.write(f"  ✅ Added Horse #{horse_no}: {name}")

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  ⚠️ Skipped row {i} due to error: {e}"))
