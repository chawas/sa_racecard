import os
import re
from bs4 import BeautifulSoup
from datetime import datetime
from django.core.management.base import BaseCommand
from racecard.models4 import Race, Horse

class Command(BaseCommand):
    help = 'Import a South African horse racecard from an HTML file.'

    def add_arguments(self, parser):
        parser.add_argument('filepath', type=str, help='Path to the racecard HTML file')

    def handle(self, *args, **kwargs):
        filepath = kwargs['filepath']

        if not os.path.exists(filepath):
            self.stdout.write(self.style.ERROR(f"File not found: {filepath}"))
            return

        # Extract race date and race number from filename e.g., turffontein_20250719_09.html
        filename = os.path.basename(filepath)
        match = re.match(r'(?P<field>.+)_(?P<date>\d{8})_(?P<race_no>\d+)\.html', filename)
        if not match:
            self.stdout.write(self.style.ERROR("Filename must be like 'turffontein_YYYYMMDD_01.html'"))
            return

        field = match.group('field').capitalize()
        race_date = datetime.strptime(match.group('date'), "%Y%m%d").date()
        race_no = int(match.group('race_no'))

        # Delete old race if it exists
        Race.objects.filter(race_date=race_date, race_no=race_no, field=field).delete()

        # Create new race
        race = Race.objects.create(race_date=race_date, race_no=race_no, field=field)
        self.stdout.write(self.style.SUCCESS(f"✔ Created Race: {field} - {race_date} - Race {race_no}"))

        with open(filepath, 'r', encoding='utf-8') as f:
            soup = BeautifulSoup(f, 'html.parser')

        tables = soup.find_all('tr', class_='small')

        for i, row in enumerate(tables):
            cols = row.find_all('td')
            if len(cols) < 8:
                continue  # Skip incomplete rows

            try:
                horse_no = int(cols[0].text.strip())
                name = cols[1].text.strip()
                blinkers = 'b' in name.lower()
                name = name.replace('(B)', '').strip()

                age = cols[2].text.strip()
                dob = cols[3].text.strip()
                odds = cols[4].text.strip()
                merit_rating = int(cols[5].text.strip())

                # Trainer and Jockey
                trainer = cols[6].text.strip()
                jockey = cols[7].text.strip()

                # Create Horse
                Horse.objects.create(
                    race=race,
                    number=horse_no,
                    name=name,
                    blinkers=blinkers,
                    age=age,
                    dob=dob,
                    odds=odds,
                    merit_rating=merit_rating,
                    trainer=trainer,
                    jockey=jockey,
                )
                self.stdout.write(f"  ✅ Added Horse #{horse_no}: {name}")

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"  ⚠️ Skipped row {i} due to error: {e}"))

        self.stdout.write(self.style.SUCCESS("🏁 Finished importing racecard."))
