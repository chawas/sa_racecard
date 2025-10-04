import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from racecard.models import Race, Horse

class Command(BaseCommand):
    help = "Import racecard HTML file or all HTML files in a directory"

    def add_arguments(self, parser):
        parser.add_argument("html_file", type=str, help="Path to HTML file or directory")

    def handle(self, *args, **options):
        input_path = options["html_file"]

        # Determine if input is a folder or file
        if os.path.isdir(input_path):
            html_files = [os.path.join(input_path, f) for f in os.listdir(input_path) if f.endswith(".html")]
        else:
            html_files = [input_path]

        for file_path in html_files:
            self.stdout.write(f"\n📄 Processing file: {file_path}")

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    soup = BeautifulSoup(f, "html.parser")
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Failed to open file: {e}"))
                continue

            # Extract race metadata
            info_tds = soup.find_all("td", align="center")
            if len(info_tds) < 2:
                self.stdout.write(self.style.ERROR("❌ Could not find race header section."))
                continue

            race_info_td = info_tds[0]
            race_info_text = race_info_td.get_text("\n", strip=True).split("\n")
            field = race_info_text[0].strip()

            # Parse and normalize race date
            raw_date = race_info_text[1].strip().replace("“", "").replace("”", "").replace("'", "").replace('"', "")
            try:
                race_date = datetime.strptime(raw_date, "%d/%m/%Y").date()
            except ValueError:
                self.stdout.write(self.style.ERROR(f"❌ Invalid date format: {raw_date}"))
                continue

            race_no = race_info_td.find("div", class_="rev4").text.strip()
            race_time_raw = race_info_td.find("div", class_="b1").text.strip()
            race_time = re.sub(r"\D", "", race_time_raw)  # Remove ":" or "."

            race_name_td = info_tds[1]
            race_name = race_name_td.contents[0].strip() if race_name_td.contents else ""

            distance_div = race_name_td.find("div", class_="b2")
            race_distance = distance_div.text.strip() if distance_div else ""

            # Get class & merit
            class_merit_text = ""
            merit_match = None
            for br in race_name_td.find_all("br"):
                next_sibling = br.next_sibling
                if next_sibling and isinstance(next_sibling, str):
                    possible_text = next_sibling.strip()
                    if "Merit Rated" in possible_text or re.search(r"\d{2,3}", possible_text):
                        class_merit_text = possible_text
                        merit_match = re.search(r"(\d{2,3})", class_merit_text)
                        break

            race_class_merit = class_merit_text
            race_merit = int(merit_match.group(1)) if merit_match else None

            self.stdout.write(f"🏇 Field: {field}")
            self.stdout.write(f"📅 Date: {race_date}, 🕒 Time: {race_time_raw}, 🏁 No: {race_no}")
            self.stdout.write(f"🏷️ Name: {race_name}, 📏 Distance: {race_distance}")
            self.stdout.write(f"📊 Class & Merit: {race_class_merit}, Extracted Merit: {race_merit}")

            # Create race only if it doesn't exist
            race, created = Race.objects.get_or_create(
                race_date=race_date,
                race_no=race_no,
                race_field=field,
                defaults={
                    "race_time": int(race_time),
                    "race_name": race_name,
                    "race_distance": race_distance,
                    "race_class": race_class_merit,
                    "race_merit": race_merit
                }
            )

            if not created:
                self.stdout.write(self.style.WARNING("⚠️ Race already exists, skipping."))
                continue

            # Process horses
            rows = soup.find_all("tr", class_="small")
            for row in rows:
                cols = row.find_all("td")
                if len(cols) < 2:
                    continue

                horse_number = cols[0].text.strip()
                if not horse_number.isdigit():
                    continue  # Skip header or bad rows
                horse_number = int(horse_number)

                name_trainer_cell = cols[1].text.strip().split("\n")
                horse_name = name_trainer_cell[0].strip()
                trainer = name_trainer_cell[1].strip() if len(name_trainer_cell) > 1 else ""

                odds = None
                merit_rating = None
                match = re.search(r"(\d+/\d+)\s+(\d+)", row.text)
                if match:
                    odds = match.group(1)
                    merit_rating = int(match.group(2))

                horse = Horse.objects.create(
                    race=race,
                    horse_no=horse_number,
                    horse_name=horse_name,
                    odds=odds,
                    horse_merit=merit_rating
                )

                self.stdout.write(f"✅ Horse {horse.horse_no}: {horse.horse_name} (MR: {horse.horse_merit}, Odds: {horse.odds})")
