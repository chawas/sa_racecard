import os
import re
from datetime import datetime

from bs4 import BeautifulSoup
import requests

# Import base command class only
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Import racecard data from HTML files'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.jt_analysis_cache = {}
        self.current_file_path = None
        self.scoring_service = None
        self.run_service = None

    def _text(self, element):
        """Safe text extraction"""
        if element:
            return element.get_text(strip=True)
        return ""
    
    def add_arguments(self, parser):
        parser.add_argument(
            'filename',  # Positional argument (no --)
            nargs='?',   # Makes it optional
            type=str,
            help='Path to specific HTML file to import'
        )
        parser.add_argument(
            '--date',
            type=str,
            help='Date to process (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--update-existing',
            action='store_true',
            help='Update existing records'
        )
    
    def handle(self, *args, **options):
        # Import ALL Django components inside the handle method
        from django.utils import timezone
        from django.db import transaction
        from django.shortcuts import get_object_or_404
        
        # Import models and services
        from racecard_02.models import Race, Horse, HorseScore, Run
        from racecard_02.services.scoring_service import ScoringService
        from racecard_02.services.run_analysis import RunAnalysisService
        
        # Initialize services
        self.scoring_service = ScoringService(debug_callback=self.stdout.write)
        self.run_service = RunAnalysisService(debug_callback=self.stdout.write)
        
        self.stdout.write("🚀 Starting racecard import...")
        
        filename = options.get('filename')
        target_date = options.get('date')
        update_existing = options.get('update_existing', False)
        
        try:
            if filename:
                self.stdout.write(f"📁 Processing specific file: {filename}")
                self._process_single_file(filename, update_existing)
            elif target_date:
                self.stdout.write(f"📅 Processing date: {target_date}")
                self._process_date(target_date, update_existing)
            else:
                self.stdout.write(self.style.ERROR("❌ Please specify a filename or --date"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Fatal error: {str(e)}"))
            import traceback
            self.stdout.write(self.style.ERROR(f"Traceback: {traceback.format_exc()}"))

    def _process_date(self, date_str, update_existing):
        """Process all files for a given date"""
        self.stdout.write(f"📅 Processing date: {date_str}")
        self.stdout.write(self.style.WARNING("⚠️ Date processing not fully implemented yet"))
    
    

    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _process_single_file(self, file_path, update_existing):
        """Process a single HTML file and return the races"""
        from racecard_02.models import Race, Horse
        
        self.stdout.write(f"📁 Processing file: {file_path}")
        self.current_file_path = file_path
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            # Store the soup as instance variable for run parsing
            self.soup = BeautifulSoup(html_content, 'html.parser')
            
            # Parse races
            races = self._parse_races(self.soup, update_existing)
            self.stdout.write(self.style.SUCCESS(f"✅ Races processed: {len(races)}"))
            
            # Parse horses for each race from this file
            for race in races:
                horses_created = self._parse_horses(self.soup, race, update_existing)
                self.stdout.write(self.style.SUCCESS(f"✅ Horses processed for race {race.race_no}: {horses_created}"))
                
                # Verify speed data is stored correctly
                self._verify_speed_data(race)
                
                # IMPORTANT: Import runs for all horses
                runs_imported = self._import_runs_for_all_horses()
                self.stdout.write(self.style.SUCCESS(f"✅ Runs imported: {runs_imported}"))
            
            # Calculate scores after all data is imported
            for race in races:
                self._calculate_horse_scores(race)
            
            return races
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error processing file {file_path}: {str(e)}"))
            import traceback
            self.stdout.write(self.style.ERROR(f"Traceback: {traceback.format_exc()}"))
            return []

    def _parse_races(self, soup, update_existing):
        """Parse race information from HTML and return race objects"""
        # Import models inside the method
        from racecard_02.models import Race
        
        self.stdout.write("🔍 Extracting Races...")
        races = []
        
        # Extract race number from filename
        filename = os.path.basename(self.current_file_path)
        match = re.search(r'_(\d{2})_', filename)
        
        if match:
            race_no = int(match.group(1))
            track_name = filename.split('_')[2].replace('_', ' ')
            race_name = f"Race {race_no} - {track_name}"
            
            # Create a basic race
            race, created = Race.objects.update_or_create(
                race_no=race_no,
                defaults={
                    'race_name': race_name,
                    'race_date': datetime.now().date(),
                    'race_field': 'Turf',
                    'race_distance': 1600,
                    'race_class': 'Handicap',
                }
            )
            races.append(race)
            self.stdout.write(f"✅ Created race from filename: {race_name} (No. {race_no})")
        else:
            self.stdout.write("❌ Could not extract race info from filename")
        
        return races

    def _parse_horses(self, soup, race, update_existing):
        """Parse horse blocks"""
        # Import models inside the method
        from racecard_02.models import Horse
        
        self.stdout.write(f"\n🔍 Extracting Horses for Race {race.race_no}...")
        created_or_updated = 0
        horse_tables = soup.select('table[border="border"]')
        self.stdout.write(f"Found {len(horse_tables)} horse tables")
        
        # FIRST: Find and parse the jockey-trainer stats table
        jt_analysis_data = self._parse_jockey_trainer_table(soup)
        self.stdout.write(f"J-T analysis data keys: {list(jt_analysis_data.keys())}")
        
        # Store in class cache for later use in score calculation
        self.jt_analysis_cache = jt_analysis_data
        self.stdout.write(f"✅ Stored J-T data in class cache: {len(self.jt_analysis_cache)} horses")
        
        # Find the PREDICTED FINISH table
        speed_index_data = {}
        
        # Look for the specific table structure with PREDICTED FINISH header
        all_tables = soup.find_all('table')
        for table in all_tables:
            predicted_finish_header = table.find('td', class_='bld')
            if predicted_finish_header and 'PREDICTED FINISH' in predicted_finish_header.get_text():
                self.stdout.write("✅ Found PREDICTED FINISH table")
                
                rows = table.find_all('tr')
                for i, row in enumerate(rows):
                    if i < 2:
                        continue
                        
                    cells = row.find_all('td')
                    if len(cells) >= 4:
                        try:
                            horse_no_text = cells[0].get_text(strip=True)
                            if not horse_no_text.isdigit():
                                continue
                            horse_no = int(horse_no_text)
                            
                            speed_text = cells[3].get_text(strip=True)
                            bracket_match = re.search(r'\[(\d+)\]', speed_text)
                            if bracket_match:
                                speed_index = int(bracket_match.group(1))
                                speed_index_data[horse_no] = speed_index
                                self.stdout.write(f"✅ Extracted speed index for horse {horse_no}: {speed_index}")
                            else:
                                digit_match = re.search(r'\d+', speed_text)
                                if digit_match:
                                    speed_index = int(digit_match.group())
                                    speed_index_data[horse_no] = speed_index
                                    self.stdout.write(f"✅ Extracted speed index (no brackets) for horse {horse_no}: {speed_index}")
                                else:
                                    self.stdout.write(f"❌ No speed index found for horse {horse_no}: '{speed_text}'")
                        except (ValueError, IndexError) as e:
                            self.stdout.write(f"Error parsing row in predicted finish table: {e}")
                            continue
        
        self.stdout.write(f"Extracted speed indices for {len(speed_index_data)} horses: {speed_index_data}")
        
        for idx, table in enumerate(horse_tables, start=1):
            try:
                self.stdout.write(f"\n🔍 Analyzing horse table {idx}...")
                
                first_tr = table.find("tr")
                if not first_tr:
                    self.stdout.write(f"Skipping table {idx}: No rows found")
                    continue
                    
                main_tds = first_tr.find_all("td", recursive=False)
                if len(main_tds) < 2:
                    self.stdout.write(f"Skipping table {idx}: Not enough main TDs ({len(main_tds)})")
                    continue

                # TD 0: number/odds/rating
                td0 = main_tds[0]
                num_div = td0.find("div", class_="b4")
                if not num_div:
                    self.stdout.write(f"Skipping table {idx}: No b4 div found")
                    continue
                    
                try:
                    horse_no = int(self._text(num_div))
                    self.stdout.write(f"Processing horse {horse_no}...")
                except Exception as e:
                    self.stdout.write(f"Skipping table {idx}: Could not parse horse number: {e}")
                    continue

                # EXTRACT SPEED INDEX
                speed_index = None
                
                if horse_no in speed_index_data:
                    speed_index = speed_index_data[horse_no]
                    self.stdout.write(f"✅ Using speed index from predicted finish table: {speed_index}")
                else:
                    self.stdout.write(f"❌ Speed index not found in predicted finish table for horse {horse_no}")
                    
                    speed_elements = table.find_all(string=re.compile(r'\[\d+\]'))
                    for element in speed_elements:
                        bracket_match = re.search(r'\[(\d+)\]', element)
                        if bracket_match:
                            try:
                                speed_index = int(bracket_match.group(1))
                                self.stdout.write(f"✅ Found speed index in brackets: {speed_index}")
                                break
                            except ValueError:
                                continue
                    
                    if speed_index is None:
                        speed_index = 50
                        self.stdout.write(f"ℹ️ Using default speed index for horse {horse_no}: 50")
                    else:
                        speed_index = max(0, min(100, speed_index))

                # Continue with rest of parsing
                odds_el = td0.find("div", class_="b1")
                odds = self._text(odds_el)

                merit_el = td0.find("span", class_="b1")
                horse_merit = None
                if merit_el:
                    m = re.search(r"\d+", merit_el.get_text())
                    if m:
                        horse_merit = int(m.group())

                # TD 1: name + age/blinkers
                td1 = main_tds[1] if len(main_tds) > 1 else None
                horse_name = ""
                blinkers = False
                age = ""

                if td1:
                    name_cell = td1.find("td", class_="b1")
                    horse_name = self._text(name_cell) or self._text(td1)
                    block_text_upper = td1.get_text(" ", strip=True).upper()
                    blinkers = "(B" in block_text_upper

                    age_text = ""
                    for s in td1.stripped_strings:
                        if re.search(r"\by\.?\s*o\.?", s, flags=re.I):
                            age_text = s
                            break
                    m_age = re.search(r"\b(\d{1,2})\b", age_text)
                    age = m_age.group(1) if m_age else ""

                # Extract Best MR from comment section
                best_merit_rating = None
                comment_section = table.find('td', colspan="21")
                if comment_section:
                    comment_text = comment_section.get_text()
                    mr_patterns = [
                        r'Best\s+(WR|MR):\s*(\d+)',
                        r'Best\s+Rating:\s*(\d+)',
                    ]
                    
                    for pattern in mr_patterns:
                        match = re.search(pattern, comment_text, re.IGNORECASE)
                        if match:
                            try:
                                mr_value = match.group(2) if len(match.groups()) > 1 else match.group(1)
                                best_merit_rating = int(mr_value)
                                self.stdout.write(f"✅ Found Best MR for horse {horse_no}: {best_merit_rating}")
                                break
                            except:
                                continue

                # Jockey / Trainer
                itbld_divs = table.select("div.itbld")
                jockey, trainer = "", ""
                if len(itbld_divs) >= 1:
                    jockey = " ".join(itbld_divs[0].stripped_strings)
                if len(itbld_divs) >= 2:
                    trainer = " ".join(itbld_divs[1].stripped_strings)

                # Jockey-Trainer Analysis
                jt_score = 50
                jt_rating = "Average"
                
                if horse_no in jt_analysis_data:
                    jt_data = jt_analysis_data[horse_no]
                    jt_score = jt_data['score']
                    jt_rating = jt_data['rating']
                    jockey = jt_data.get('jockey', jockey)
                    trainer = jt_data.get('trainer', trainer)
                    self.stdout.write(f"✅ Found J-T data for horse {horse_no}: Score={jt_score}")
                else:
                    self.stdout.write(f"❌ No J-T data found for horse {horse_no}, using default score 50")

                # Ensure safe field lengths
                age = (age or "")[:10]
                odds = (odds or "")[:20]

                # Upsert with speed_rating
                defaults = dict(
                    horse_name=horse_name,
                    blinkers=bool(blinkers),
                    age=age,
                    dob="",
                    odds=odds,
                    horse_merit=horse_merit if horse_merit is not None else 0,
                    best_merit_rating=best_merit_rating,
                    speed_rating=speed_index,
                    race_class=race.race_class or "",
                    trainer=trainer,
                    jockey=jockey,
                    jt_score=jt_score,
                    jt_rating=jt_rating,
                )
                obj, created = Horse.objects.update_or_create(
                    race=race, horse_no=horse_no, defaults=defaults
                )
                created_or_updated += 1

                self.stdout.write(f"💾 Saved horse {horse_no} with speed_rating: {speed_index}")
                
                obj.refresh_from_db()
                self.stdout.write(f"✅ Verified speed_rating in DB: {obj.speed_rating}")

                self.stdout.write(
                    f"🐎 Horse {horse_no}: {horse_name} | "
                    f"Blinkers={blinkers} | Odds={odds or '-'} | "
                    f"Merit={defaults['horse_merit']} | Best MR={best_merit_rating or '-'} | "
                    f"Speed={speed_index} | "
                    f"Jockey={jockey or '-'} | Trainer={trainer or '-'} | "
                    f"J-T Score={jt_score} | J-T Rating={jt_rating}"
                )

            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Skipping one table (idx {idx}) due to error: {e}"))
                import traceback
                self.stdout.write(traceback.format_exc())

        self.stdout.write(self.style.SUCCESS(f"✅ Horses saved: {created_or_updated}"))
        
        return created_or_updated

    def _parse_jockey_trainer_table(self, soup):
        """Find and parse the jockey-trainer statistics table"""
        jt_analysis_data = {}
        
        self.stdout.write("🔍 SEARCHING FOR JOCKEY-TRAINER TABLE...")
        
        for i, table in enumerate(soup.find_all('table')):
            if table.get('class') and 'small' in table.get('class'):
                continue
                
            rows = table.find_all('tr')
            if not rows:
                continue
            
            is_jt_table = False
            jt_rows_found = 0
            
            for row in rows[:5]:
                cells = row.find_all(['td', 'th'])
                cell_texts = [cell.get_text(strip=True) for cell in cells]
                
                if len(cell_texts) >= 9 and len(cell_texts) % 9 == 0:
                    if cell_texts[0].isdigit() and len(cell_texts[0]) <= 2:
                        if (not any(text in cell_texts[1] for text in ['(', ')', '/']) and 
                            not any(text in cell_texts[2] for text in ['(', ')', '/'])):
                            is_jt_table = True
                            jt_rows_found += 1
            
            if is_jt_table and jt_rows_found >= 2:
                self.stdout.write(f"🎯 FOUND J-T TABLE {i} with {jt_rows_found} valid rows!")
                
                for j, row in enumerate(rows):
                    jt_results = self.analyze_jockey_trainer_combination(row)
                    
                    for result in jt_results:
                        try:
                            horse_no = int(result['horse_number'])
                            jt_analysis_data[horse_no] = {
                                'score': result['score'],
                                'rating': result['rating'],
                                'jockey': result['jockey'],
                                'trainer': result['trainer'],
                                'starts': result.get('starts', 0),
                                'first_places': result.get('first_places', 0),
                                'second_places': result.get('second_places', 0),
                                'third_places': result.get('third_places', 0)
                            }
                            self.stdout.write(f"  🎯 Horse {horse_no}: J-T Score={result['score']} ({result['jockey']}/{result['trainer']})")
                        except (ValueError, KeyError) as e:
                            continue
                
                if jt_analysis_data:
                    self.stdout.write(f"✅ Successfully parsed J-T data from table {i}")
                    break
        
        if not jt_analysis_data:
            self.stdout.write("⚠️ No J-T table found, using empty data")
        else:
            self.stdout.write(f"✅ SUCCESS: Parsed J-T data for {len(jt_analysis_data)} horses: {list(jt_analysis_data.keys())}")
        
        return jt_analysis_data

    def analyze_jockey_trainer_combination(self, html_row):
        """Analyze jockey-trainer combination from HTML row"""
        cells = html_row.find_all('td')
        cell_texts = [cell.get_text(strip=True) for cell in cells]
        
        if len(cell_texts) < 9 or len(cell_texts) % 9 != 0:
            return []
        
        if not cell_texts[0].isdigit() or len(cell_texts[0]) > 2:
            return []
        
        if any('(' in text and ')' in text for text in cell_texts[:3]):
            return []
        
        if any('/' in text for text in cell_texts[:3]):
            return []
        
        self.stdout.write(f"🔍 ANALYZING J-T ROW: {cell_texts}")
        
        results = []
        
        def safe_int(value, default=0):
            try:
                return int(value.replace(',', '').replace('%', '').strip())
            except (ValueError, AttributeError):
                return default
        
        horse_count = len(cell_texts) // 9
        
        for horse_index in range(horse_count):
            start_idx = horse_index * 9
            end_idx = start_idx + 9
            
            if end_idx > len(cell_texts):
                break
                
            horse_data = cell_texts[start_idx:end_idx]
            
            try:
                horse_number = horse_data[0]
                trainer = horse_data[1]
                jockey = horse_data[2]
                
                if any(c.isdigit() for c in trainer) or any(c.isdigit() for c in jockey):
                    continue
                
                starts = safe_int(horse_data[3])
                first_places = safe_int(horse_data[4])
                second_places = safe_int(horse_data[5])
                third_places = safe_int(horse_data[6])
                win_percentage = safe_int(horse_data[7])
                place_percentage = safe_int(horse_data[8])
                
                score = (
                    (place_percentage * 0.4) +
                    (win_percentage * 0.3) +
                    (min(starts, 50) * 0.1) +
                    (25 if starts > 10 else 0)
                )
                score = max(0, min(100, round(score, 2)))
                
                rating = self._get_jt_rating(score)
                
                results.append({
                    'horse_number': horse_number,
                    'jockey': jockey,
                    'trainer': trainer,
                    'starts': starts,
                    'first_places': first_places,
                    'second_places': second_places,
                    'third_places': third_places,
                    'win_percentage': win_percentage,
                    'place_percentage': place_percentage,
                    'score': score,
                    'rating': rating
                })
                
                self.stdout.write(f"✅ Horse {horse_number}: {jockey}/{trainer}, Score={score}")
                
            except Exception as e:
                self.stdout.write(f"❌ Error parsing horse {horse_index + 1}: {e}")
                continue
        
        return results

    def _get_jt_rating(self, score):
        """Convert numerical score to qualitative rating"""
        if score >= 80:
            return "Excellent"
        elif score >= 60:
            return "Very Good"
        elif score >= 40:
            return "Good"
        elif score >= 20:
            return "Average"
        else:
            return "Poor"

    def _verify_speed_data(self, race):
        """Verify that speed data is being stored correctly"""
        # Import models inside the method
        from racecard_02.models import Horse
        
        self.stdout.write(f"\n🔍 VERIFYING SPEED DATA FOR RACE {race.race_no}")
        self.stdout.write("="*50)
        
        horses = Horse.objects.filter(race=race)
        for horse in horses:
            self.stdout.write(
                f"Horse {horse.horse_no}: {horse.horse_name} - "
                f"Speed Rating: {getattr(horse, 'speed_rating', 'NOT SET')} - "
                f"Best MR: {getattr(horse, 'best_merit_rating', 'N/A')} - "
                f"Current MR: {getattr(horse, 'horse_merit', 'N/A')} - "
                f"J-T Score: {getattr(horse, 'jt_score', 'N/A')}"
            )
        
        self.stdout.write("="*50)

    

    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _debug_horse_compartments(self):
        """Debug method to understand horse compartment structure"""
        self.stdout.write("\n🔍 DEBUG: Analyzing horse compartments...")
        
        if not hasattr(self, 'soup') or not self.soup:
            self.stdout.write("❌ No HTML content parsed yet")
            return
        
        # Look for tables that might be horse compartments
        potential_compartments = []
        
        # Look for tables that contain both horse data and run data
        all_tables = self.soup.find_all('table')
        
        for i, table in enumerate(all_tables):
            # Check if this table has horse data (numbers or names)
            horse_numbers = table.find_all(string=lambda text: text and text.strip().isdigit() and 1 <= int(text.strip()) <= 20)
            horse_names = table.find_all('td', class_='b1')
            
            # Check if it also has run data
            run_rows = table.find_all('tr', class_='small')
            
            if (horse_numbers or horse_names) and run_rows:
                potential_compartments.append((i, table, len(horse_numbers), len(horse_names), len(run_rows)))
        
        self.stdout.write(f"Found {len(potential_compartments)} potential horse compartments")
        
        for comp_idx, table, num_count, name_count, run_count in potential_compartments[:3]:  # Show first 3
            self.stdout.write(f"Compartment {comp_idx}: {num_count} numbers, {name_count} names, {run_count} runs")
            
            # Show sample horse data
            if num_count > 0:
                numbers = table.find_all(string=lambda text: text and text.strip().isdigit() and 1 <= int(text.strip()) <= 20)
                self.stdout.write(f"  Horse numbers: {[n.strip() for n in numbers[:2]]}")
            
            # Show sample run data (with SAFE access)
            if run_count > 0:
                runs = table.find_all('tr', class_='small')
                if runs:
                    first_run = runs[0]
                    cells = first_run.find_all('td')
                    if cells:
                        # SAFE cell access - check length first
                        cell_texts = []
                        for cell_idx in range(min(3, len(cells))):  # Only first 3 cells max
                            cell_texts.append(cells[cell_idx].get_text(strip=True))
                        self.stdout.write(f"  First run cells: {cell_texts}")



    def parse_horse_runs(html_content, horse_name, verbosity=1):
        """
        Parses the horse racing HTML content and returns structured data for runs.
        """
        if verbosity >= 2:
            print(f"Parsing runs for {horse_name}...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all('tr', class_='small')
        
        parsed_runs = []
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 21:
                continue
                
            try:
                # Column 0: Date & Days
                days_date_str = cells[0].get_text(strip=True)
                match = re.match(r'\((\d+)\)\s*(\d{2}\.\d{2}\.\d{2})', days_date_str)
                if match:
                    days_since_last_run = match.group(1)
                    raw_date = match.group(2)
                    # Convert date from YY.MM.DD to YYYY-MM-DD
                    try:
                        run_date = datetime.strptime(raw_date, '%y.%m.%d').strftime('%Y-%m-%d')
                    except ValueError:
                        run_date = raw_date
                else:
                    days_since_last_run = None
                    run_date = days_date_str

                # Column 1: Track Condition
                going = cells[1].get_text(strip=True)
                
                # Column 2: Race Number
                race_number = cells[2].get_text(strip=True)
                
                # Column 3: Race Class
                race_class = cells[3].get_text(strip=True)
                
                # Column 4: Track Name
                track = cells[4].get_text(strip=True)
                
                # Column 6: Distance
                distance = cells[6].get_text(strip=True)
                
                # Column 7: Jockey
                jockey = cells[7].get_text(strip=True)
                
                # Column 8: Weight
                weight = cells[8].get_text(strip=True)
                
                # Column 9: Merit Rating
                merit_rating = cells[9].get_text(strip=True).strip('()')
                
                # Column 10: Equipment
                equipment = cells[10].get_text(strip=True)
                
                # Column 11: Draw and Field Size
                draw_info = cells[11].get_text(strip=True)
                if '-' in draw_info:
                    draw, field_size = draw_info.split('-')
                else:
                    draw, field_size = None, None
                
                # Column 12: Finishing Position
                position = cells[12].get_text(strip=True)
                
                # Column 13: Lengths Behind
                margin = cells[13].get_text(strip=True)
                
                # Column 15: Time
                time_seconds = cells[15].get_text(strip=True)
                
                # Column 16: Speed Figure
                speed_figure = cells[16].get_text(strip=True)
                
                # Column 17: Starting Price
                sp_price = cells[17].get_text(strip=True)
                
                # Column 20: Comment
                comment = cells[20].get_text(strip=True) if len(cells) > 20 else ""

                run_data = {
                    'date': run_date,
                    'days_since_last_run': days_since_last_run,
                    'track': track,
                    'going': going,
                    'race_class': race_class,
                    'distance': int(distance),
                    'position': int(position),
                    'margin': float(margin) if margin.replace('.', '').isdigit() else 0.0,
                    'weight': float(weight),
                    'merit_rating': int(merit_rating) if merit_rating.isdigit() else None,
                    'jockey': jockey,
                    'draw': int(draw) if draw and draw.isdigit() else None,
                    'field_size': int(field_size) if field_size and field_size.isdigit() else None,
                    'time_seconds': float(time_seconds) if time_seconds.replace('.', '').isdigit() else None,
                    'starting_price': sp_price,
                    'comment': comment,
                    'horse_name': horse_name
                }
                
                parsed_runs.append(run_data)
                
            except (IndexError, ValueError) as e:
                if verbosity >= 1:
                    print(f"Error parsing row for {horse_name}: {e}")
                continue
            except Exception as e:
                if verbosity >= 1:
                    print(f"Unexpected error parsing row for {horse_name}: {e}")
                continue
        
        return parsed_runs


    

    def _debug_find_all_tables(self):
        """Debug method to find all tables and their content"""
        self.stdout.write("\n🔍 DEBUG: Analyzing ALL tables in HTML...")
        
        if not hasattr(self, 'soup') or not self.soup:
            self.stdout.write("❌ No HTML content parsed yet")
            return
        
        all_tables = self.soup.find_all('table')
        self.stdout.write(f"Found {len(all_tables)} total tables")
        
        for i, table in enumerate(all_tables):
            rows = table.find_all('tr')
            self.stdout.write(f"\nTable {i}: {len(rows)} rows")
            
            # Show first 2 rows as sample
            for j, row in enumerate(rows[:2]):
                cells = row.find_all('td')
                cell_texts = [cell.get_text(strip=True) for cell in cells[:8]]  # First 8 cells
                self.stdout.write(f"  Row {j}: {cell_texts}")
                
            # Check if this table might contain run data
            if any('25.06.15' in str(row) for row in rows[:5]):  # Look for date patterns
                self.stdout.write(f"  🎯 POTENTIAL RUN TABLE: Contains date patterns")

    def _find_main_run_table(self):
        """Find the actual table that contains all run data"""
        self.stdout.write("\n🔍 Searching for main run table...")
        
        all_tables = self.soup.find_all('table')
        
        for i, table in enumerate(all_tables):
            rows = table.find_all('tr')
            
            # Look for tables with many rows that contain run-like data
            if len(rows) > 10:  # Tables with many rows might be run tables
                # Check if rows contain run data patterns (dates, tracks, etc.)
                date_patterns = ['25.06.15', '24.08.11', '24.09.08', '24.10.24']
                has_run_patterns = any(any(pattern in str(row) for pattern in date_patterns) for row in rows[:5])
                
                if has_run_patterns:
                    self.stdout.write(f"🎯 FOUND POTENTIAL RUN TABLE: Table {i} with {len(rows)} rows")
                    return table
        
        self.stdout.write("❌ No main run table found")
        return None


    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _debug_html_structure(self):
        """Debug method to understand the HTML structure"""
        self.stdout.write("\n🔍 DEBUG: Analyzing HTML structure...")
        
        if not hasattr(self, 'soup') or not self.soup:
            self.stdout.write("❌ No HTML content parsed yet")
            return
        
        # 1. Count all tables
        all_tables = self.soup.find_all('table')
        self.stdout.write(f"Total tables found: {len(all_tables)}")
        
        # 2. Find tables with specific classes
        for class_name in ['small', 'bld', 'b1', 'b4']:
            tables = self.soup.find_all('table', class_=class_name)
            self.stdout.write(f"Tables with class '{class_name}': {len(tables)}")
        
        # 3. Look for horse numbers and names
        horse_numbers = self.soup.find_all(string=lambda text: text and text.strip().isdigit() and 1 <= int(text.strip()) <= 20)
        self.stdout.write(f"Potential horse numbers found: {len(horse_numbers)}")
        
        # 4. Show sample of what we found
        for i, number in enumerate(horse_numbers[:5]):
            self.stdout.write(f"  Horse number {i}: '{number.strip()}'")
            parent = number.find_parent()
            if parent:
                self.stdout.write(f"    Parent: {parent.name}, classes: {parent.get('class', [])}")

    def _debug_find_horse_sections(self):
        """Debug method to find how horses are organized"""
        self.stdout.write("\n🔍 DEBUG: Finding horse sections...")
        
        # Look for horse tables (usually with border="border")
        horse_tables = self.soup.select('table[border="border"]')
        self.stdout.write(f"Potential horse tables: {len(horse_tables)}")
        
        for i, table in enumerate(horse_tables[:3]):  # First 3 tables
            self.stdout.write(f"\nHorse table {i}:")
            
            # Look for horse number in this table
            horse_numbers = table.find_all(string=lambda text: text and text.strip().isdigit() and 1 <= int(text.strip()) <= 20)
            for number in horse_numbers:
                self.stdout.write(f"  Found horse #: {number.strip()}")
                
            # Look for horse names
            horse_names = table.find_all('td', class_='b1')
            for name in horse_names[:2]:  # First 2 names
                self.stdout.write(f"  Found horse name: {name.get_text(strip=True)}")
                
            # Look for adjacent run tables
            run_tables = table.find_next_siblings('table', class_='small')
            self.stdout.write(f"  Adjacent run tables: {len(run_tables)}")

    def _debug_save_html(self, filename="debug_output.html"):
        """Save the parsed HTML to a file for manual inspection"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(str(self.soup.prettify()))
            self.stdout.write(f"💾 HTML saved to {filename} for manual inspection")
        except Exception as e:
            self.stdout.write(f"❌ Error saving HTML: {e}")

    def _get_horse_runs_html(self, horse):
        """Get HTML content for a specific horse's runs - SIMPLIFIED FOR NOW"""
        self.stdout.write(f"    🔍 Looking for runs of {horse.horse_name} (#{horse.horse_no})...")
        
        # TEMPORARY: Return empty for now while we debug the structure
        self.stdout.write("    ⚠️ Run extraction paused for structure debugging")
        return None



    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _calculate_horse_scores(self, race):
        """Simple score calculation - FIXED SCORING SERVICE CALL"""
        from racecard_02.models import Horse, HorseScore
        
        self.stdout.write(f"\n📊 Calculating basic scores for Race {race.race_no}...")
        
        horses = Horse.objects.filter(race=race)
        
        for horse in horses:
            try:
                self.stdout.write(f"    🐎 Processing {horse.horse_name}...")
                
                # FIXED: Handle the return value properly
                result = self.scoring_service.create_score_record(horse, race)
                
                if result:
                    score_record, created = result  # Now expecting 2 values, not 3
                    status = "Created" if created else "Updated"
                    self.stdout.write(f"    ✅ {status}: {score_record.overall_score:.1f}")
                else:
                    self.stdout.write(f"    ❌ No score record returned for {horse.horse_name}")
                    
            except Exception as e:
                self.stdout.write(f"    ❌ Error: {e}")
                import traceback
                self.stdout.write(f"    Traceback: {traceback.format_exc()}")
        
        # Display simple rankings
        self._display_simple_rankings(race)



    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _get_horse_compartment(self, horse):
        """Find the HTML compartment/section for a specific horse's runs"""
        try:
            self.stdout.write(f"    🔍 Searching for compartment of {horse.horse_name} (#{horse.horse_no})...")
            
            # Look for the horse number in the HTML
            horse_number_pattern = re.compile(rf'\b{horse.horse_no}\b')
            horse_number_elements = self.soup.find_all(string=horse_number_pattern)
            
            self.stdout.write(f"    Found {len(horse_number_elements)} elements with horse number {horse.horse_no}")
            
            for i, element in enumerate(horse_number_elements):
                # Look for the parent table that might contain runs
                parent_table = element.find_parent('table')
                if parent_table:
                    # Check if this table has run data (rows with class 'small')
                    run_rows = parent_table.find_all('tr', class_='small')
                    if run_rows:
                        self.stdout.write(f"    ✅ Found horse compartment with {len(run_rows)} run rows")
                        
                        # DEBUG: Show sample of what we found
                        if len(run_rows) > 0:
                            sample_cells = run_rows[0].find_all('td')
                            if sample_cells and len(sample_cells) > 5:
                                sample_text = ' | '.join([cell.get_text(strip=True)[:10] for cell in sample_cells[:5]])
                                self.stdout.write(f"    Sample data: {sample_text}...")
                        
                        return str(parent_table)
                    else:
                        self.stdout.write(f"    ℹ️  Found table but no run rows for element {i}")
                else:
                    self.stdout.write(f"    ℹ️  No parent table for element {i}")
            
            self.stdout.write(f"    ❌ No compartment found for {horse.horse_name} (#{horse.horse_no})")
            return None
            
        except Exception as e:
            self.stdout.write(f"    ❌ Error finding compartment for {horse.horse_name}: {e}")
            return None

    def _parse_runs_from_compartment(self, html_content, horse_name, horse_number):
        """Parse ACTUAL run data from a horse's compartment"""
        runs_data = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find all run rows (class 'small') - these should be actual run history
            run_rows = soup.find_all('tr', class_='small')
            
            if not run_rows:
                self.stdout.write(f"    🐎 {horse_name} is a MAIDEN - no previous runs")
                return runs_data
            
            # Filter out rows that don't look like actual runs (no dates, etc.)
            actual_run_rows = []
            for row in run_rows:
                cells = row.find_all('td')
                if len(cells) >= 5 and any('.' in cells[0].get_text() for cell in cells[:2]):  # Look for date patterns
                    actual_run_rows.append(row)
            
            if not actual_run_rows:
                self.stdout.write(f"    🐎 {horse_name} has no recognizable run history in this compartment")
                return runs_data
            
            self.stdout.write(f"    📊 Found {len(actual_run_rows)} actual run rows for {horse_name}")
            
            # Display table header only if we have actual runs
            self.stdout.write("\n    ┌─────────┬──────────┬────┬──────┬──────┬────────┬────────┬──────────┬────────┐")
            self.stdout.write("    │   Date  │  Track   │ R# │ Going│ Class│ Distance│ Weight │ Jockey  │ Position│")
            self.stdout.write("    ├─────────┼──────────┼────┼──────┼──────┼─────────┼────────┼──────────┼────────┤")
            
            for row_idx, row in enumerate(actual_run_rows):
                cells = row.find_all('td')
                
                try:
                    # Check if this looks like a real run (should contain a date)
                    first_cell = cells[0].get_text(strip=True)
                    if not any(char.isdigit() and '.' in first_cell for char in first_cell):
                        continue  # Skip rows that don't start with a date
                    
                    run_data = {
                        'run_date': cells[0].get_text(strip=True).replace('(', '').replace(')', '').strip(),
                        'track': cells[1].get_text(strip=True) if len(cells) > 1 else '',
                        'race_no': cells[2].get_text(strip=True) if len(cells) > 2 else '',
                        'going': cells[3].get_text(strip=True) if len(cells) > 3 else '',
                        'race_class': cells[4].get_text(strip=True) if len(cells) > 4 else '',
                        'distance': cells[6].get_text(strip=True) if len(cells) > 6 else '',
                        'weight': cells[8].get_text(strip=True) if len(cells) > 8 else '',
                        'jockey': cells[7].get_text(strip=True) if len(cells) > 7 else '',
                        'position': '',
                        'margin': ''
                    }
                    
                    # Extract position from later cells if available
                    if len(cells) > 11:
                        position_cell = cells[11]
                        position_span = position_cell.find('span', class_='r')
                        if position_span:
                            run_data['position'] = position_span.get_text(strip=True)
                    
                    # Display in table format
                    date_display = run_data['run_date'][:9] if len(run_data['run_date']) > 9 else run_data['run_date']
                    track_display = run_data['track'][:8] if len(run_data['track']) > 8 else run_data['track']
                    going_display = run_data['going'][:4] if len(run_data['going']) > 4 else run_data['going']
                    class_display = run_data['race_class'][:4] if len(run_data['race_class']) > 4 else run_data['race_class']
                    jockey_display = run_data['jockey'][:8] if len(run_data['jockey']) > 8 else run_data['jockey']
                    
                    self.stdout.write(f"    │ {date_display:8} │ {track_display:8} │ {run_data['race_no']:2} │ {going_display:4} │ {class_display:4} │ {run_data['distance']:7} │ {run_data['weight']:6} │ {jockey_display:8} │ {run_data['position']:6} │")
                    
                    runs_data.append(run_data)
                    
                except Exception as e:
                    self.stdout.write(f"    │ ERROR PARSING ROW {row_idx} {str(e)[:30]:<40} │")
            
            if runs_data:
                self.stdout.write("    └─────────┴──────────┴────┴──────┴──────┴─────────┴────────┴──────────┴────────┘")
                self.stdout.write(f"    ✅ Parsed {len(runs_data)} runs for {horse_name}")
            else:
                self.stdout.write("    │ NO VALID RUNS FOUND IN THIS COMPARTMENT │")
                self.stdout.write("    └─────────────────────────────────────────┘")
            
        except Exception as e:
            self.stdout.write(f"    ❌ Error parsing runs from compartment: {e}")
        
        return runs_data






    def _display_simple_rankings(self, race):
        """Simple rankings display"""
        # Import models inside the method
        from racecard_02.models import HorseScore
        
        self.stdout.write(f"\n🔍 Checking database for HorseScore records...")
        
        # Check what scores actually exist
        scores = HorseScore.objects.filter(race=race)
        self.stdout.write(f"Found {scores.count()} HorseScore records for race {race.race_no}")
        
        if scores.count() == 0:
            self.stdout.write("❌ No HorseScore records found in database!")
            # Check if the scoring service is actually saving records
            self.stdout.write("The scoring service may be calculating scores but not saving them to the database")
            return
        
        scores = scores.select_related('horse').order_by('-overall_score')
        
        self.stdout.write("\n" + "="*60)
        self.stdout.write(f"🏆 RANKINGS - Race {race.race_no}")
        self.stdout.write("="*60)
        
        header = f"{'Pos':<3} {'No':<3} {'Horse':<20} {'Score':<6} {'Speed':<6} {'JT':<5}"
        self.stdout.write(header)
        self.stdout.write("-" * 60)
        
        for position, score in enumerate(scores, 1):
            horse = score.horse
            self.stdout.write(
                f"{position:<3} "
                f"{horse.horse_no:<3} "
                f"{horse.horse_name:<20.20} "
                f"{score.overall_score:<6.1f} "
                f"{getattr(horse, 'speed_rating', 0):<6} "
                f"{getattr(horse, 'jt_score', 50):<5} "
            )
        
        self.stdout.write("="*60)



    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _parse_runs_from_html(self, html_content, horse_name):
        """Parse run data from HTML content based on the exact format"""
        runs_data = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            row = soup.find('tr')
            
            if not row:
                self.stdout.write(f"    ⚠️ No table row found for {horse_name}")
                return runs_data
                
            cells = row.find_all('td')
            
            if len(cells) < 20:  # Based on your sample format
                self.stdout.write(f"    ⚠️ Insufficient data cells ({len(cells)}) for {horse_name}")
                return runs_data
                
            try:
                run_data = {
                    'date': cells[0].get_text(strip=True).replace('(', '').replace(')', '').strip(),
                    'track': cells[1].get_text(strip=True),
                    'race_no': cells[2].get_text(strip=True),
                    'going': cells[3].get_text(strip=True),
                    'race_class': cells[4].get_text(strip=True),
                    'draw': cells[5].get_text(strip=True),
                    'distance': cells[6].get_text(strip=True),
                    'jockey': cells[7].get_text(strip=True),
                    'weight': cells[8].get_text(strip=True),
                    'rating': cells[9].get_text(strip=True).replace('(', '').replace(')', '').strip(),
                    'position': cells[12].get_text(strip=True) if len(cells) > 12 else '',  # Position is in cell 12
                    'margin': cells[12].get_text(strip=True) if len(cells) > 12 else '',    # Margin might be here too
                    'time': cells[16].get_text(strip=True) if len(cells) > 16 else '',
                    'odds': cells[18].get_text(strip=True) if len(cells) > 18 else '',
                    'comment': cells[19].get_text(strip=True) if len(cells) > 19 else ''
                }
                
                # Extract position and margin from the specific cell
                position_cell = cells[11] if len(cells) > 11 else None
                if position_cell:
                    # Look for position in span with class 'r'
                    position_span = position_cell.find('span', class_='r')
                    if position_span:
                        run_data['position'] = position_span.get_text(strip=True)
                    
                    # Extract margin from the text
                    cell_text = position_cell.get_text(strip=True)
                    if '"' in cell_text:
                        parts = cell_text.split('"')
                        if len(parts) > 1:
                            run_data['margin'] = parts[1].strip()
                
                runs_data.append(run_data)
                self.stdout.write(f"    📋 Parsed run: {run_data['date']} at {run_data['track']} - Pos {run_data.get('position', 'N/A')}")
                
            except IndexError as e:
                self.stdout.write(f"    ⚠️ Cell index error for {horse_name}: {e}")
            except Exception as e:
                self.stdout.write(f"    ⚠️ Parse error for {horse_name}: {e}")
                
        except Exception as e:
            self.stdout.write(f"    ❌ Error parsing runs for {horse_name}: {e}")
        
        return runs_data
    




    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

   
    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _debug_run_tables(self):
        """Debug method to find run tables in the HTML"""
        self.stdout.write("\n🔍 DEBUG: Searching for run tables...")
        
        if not hasattr(self, 'soup') or not self.soup:
            self.stdout.write("❌ No HTML content parsed yet")
            return
        
        # Look for tables with small rows
        tables_with_small_rows = []
        all_tables = self.soup.find_all('table')
        
        for i, table in enumerate(all_tables):
            small_rows = table.find_all('tr', class_='small')
            if small_rows:
                tables_with_small_rows.append((i, table, small_rows))
        
        self.stdout.write(f"Found {len(tables_with_small_rows)} tables with 'small' rows")
        
        for table_idx, table, small_rows in tables_with_small_rows:
            self.stdout.write(f"\nTable {table_idx}: {len(small_rows)} small rows")
            
            # Show first 3 rows as sample
            for j, row in enumerate(small_rows[:3]):
                bId_cell = row.find('td', class_='bId')
                horse_number = bId_cell.get_text(strip=True) if bId_cell else "N/A"
                self.stdout.write(f"  Row {j}: Horse #{horse_number}")

    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _parse_runs_from_compartment(self, html_content, horse_name, horse_number):
        """Parse run data from a horse's compartment and display in table format"""
        runs_data = []
        
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Find all run rows (class 'small')
            run_rows = soup.find_all('tr', class_='small')
            
            if not run_rows:
                self.stdout.write(f"    🐎 {horse_name} is a MAIDEN - no previous runs")
                return runs_data
            
            self.stdout.write(f"    📊 Found {len(run_rows)} run rows for {horse_name}")
            
            # Display table header
            self.stdout.write("\n    ┌─────────┬──────────┬────┬──────┬──────┬────────┬────────┬──────────┬────────┐")
            self.stdout.write("    │   Date  │  Track   │ R# │ Going│ Class│ Distance│ Weight │ Jockey  │ Position│")
            self.stdout.write("    ├─────────┼──────────┼────┼──────┼──────┼─────────┼────────┼──────────┼────────┤")
            
            for row_idx, row in enumerate(run_rows):
                cells = row.find_all('td')
                
                # Skip rows that don't have enough data
                if len(cells) < 10:
                    continue
                
                try:
                    run_data = {
                        'date': cells[0].get_text(strip=True).replace('(', '').replace(')', '').strip(),
                        'track': cells[1].get_text(strip=True),
                        'race_no': cells[2].get_text(strip=True),
                        'going': cells[3].get_text(strip=True),
                        'race_class': cells[4].get_text(strip=True),
                        'draw': cells[5].get_text(strip=True) if len(cells) > 5 else '',
                        'distance': cells[6].get_text(strip=True) if len(cells) > 6 else '',
                        'jockey': cells[7].get_text(strip=True) if len(cells) > 7 else '',
                        'weight': cells[8].get_text(strip=True) if len(cells) > 8 else '',
                        'rating': cells[9].get_text(strip=True).replace('(', '').replace(')', '').strip() if len(cells) > 9 else '',
                        'position': '',
                        'margin': ''
                    }
                    
                    # Extract position and margin
                    if len(cells) > 11:
                        position_cell = cells[11]
                        position_span = position_cell.find('span', class_='r')
                        if position_span:
                            run_data['position'] = position_span.get_text(strip=True)
                        else:
                            run_data['position'] = position_cell.get_text(strip=True)
                    
                    # Display in table format
                    date_display = run_data['date'][:9] if len(run_data['date']) > 9 else run_data['date']
                    track_display = run_data['track'][:8] if len(run_data['track']) > 8 else run_data['track']
                    going_display = run_data['going'][:4] if len(run_data['going']) > 4 else run_data['going']
                    class_display = run_data['race_class'][:4] if len(run_data['race_class']) > 4 else run_data['race_class']
                    jockey_display = run_data['jockey'][:8] if len(run_data['jockey']) > 8 else run_data['jockey']
                    
                    self.stdout.write(f"    │ {date_display:8} │ {track_display:8} │ {run_data['race_no']:2} │ {going_display:4} │ {class_display:4} │ {run_data['distance']:7} │ {run_data['weight']:6} │ {jockey_display:8} │ {run_data['position']:6} │")
                    
                    runs_data.append(run_data)
                    
                except Exception as e:
                    self.stdout.write(f"    │ ERROR PARSING ROW {row_idx} {str(e)[:30]:<40} │")
            
            # Close the table
            self.stdout.write("    └─────────┴──────────┴────┴──────┴──────┴─────────┴────────┴──────────┴────────┘")
            self.stdout.write(f"    ✅ Parsed {len(runs_data)} runs for {horse_name}")
            
        except Exception as e:
            self.stdout.write(f"    ❌ Error parsing runs from compartment: {e}")
        
        return runs_data
    



    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _import_runs_for_all_horses(self):
        # ... [your existing code] ...
        
        for run_data in runs_data:
            try:
                run_date = datetime.strptime(run_data['date'], '%Y-%m-%d').date()
                
                # Use run_date instead of date
                run, created = Run.objects.update_or_create(
                    horse=horse,
                    run_date=run_date,  # ✅ Changed from date to run_date
                    defaults={
                        'track': run_data['track'],
                        'going': run_data['going'],
                        'race_class': run_data['race_class'],
                        'distance': run_data['distance'],
                        'position': run_data['position'],
                        'margin': run_data['margin'],
                        'weight': run_data['weight'],
                        'merit_rating': run_data['merit_rating'],
                        'jockey': run_data['jockey'],
                        'draw': run_data['draw'],
                        'field_size': run_data['field_size'],
                        'time_seconds': run_data['time_seconds'],
                        'starting_price': run_data['starting_price'],
                        'comment': run_data['comment'],
                        'days_since_last_run': run_data['days_since_last_run'],
                    }
                )
                
                total_imported += 1
                status = "Created" if created else "Updated"
                self.stdout.write(f"      💾 {status}: {run_date} - {run_data['track']} - Pos {run_data['position']}")
                
            except Exception as e:
                self.stdout.write(f"      ❌ Error saving run: {e}")
            # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

        def debug_html_structure(self):
            """Manual debug method to call separately if needed"""
            self._debug_horse_compartments()




    # === PLACE IN: racecard_02/management/commands/import_racecard_02.py ===

    def _debug_compartment_content(self, html_content, horse_name):
        """Debug what's actually in the compartment"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            run_rows = soup.find_all('tr', class_='small')
            
            self.stdout.write(f"\n    🔍 DEBUG: Content for {horse_name}'s compartment:")
            
            for i, row in enumerate(run_rows[:3]):  # Show first 3 rows
                cells = row.find_all('td')
                cell_texts = [cell.get_text(strip=True) for cell in cells[:8]]  # First 8 cells
                self.stdout.write(f"    Row {i}: {cell_texts}")
                
        except Exception as e:
            self.stdout.write(f"    ❌ Debug error: {e}")




    def parse_horse_runs(self, html_content, horse_name, verbosity=1):
        """
        Parses the horse racing HTML content and returns structured data for runs.
        """
        if verbosity >= 2:
            self.stdout.write(f"Parsing runs for {horse_name}...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all('tr', class_='small')
        
        parsed_runs = []
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 21:
                continue
                
            try:
                # Column 0: Date & Days
                days_date_str = cells[0].get_text(strip=True)
                match = re.match(r'\((\d+)\)\s*(\d{2}\.\d{2}\.\d{2})', days_date_str)
                if match:
                    days_since_last_run = match.group(1)
                    raw_date = match.group(2)
                    # Convert date from YY.MM.DD to YYYY-MM-DD
                    try:
                        run_date = datetime.strptime(raw_date, '%y.%m.%d').strftime('%Y-%m-%d')
                    except ValueError:
                        run_date = raw_date
                else:
                    days_since_last_run = None
                    run_date = days_date_str

                # Column 1: Track Condition
                going = cells[1].get_text(strip=True)
                
                # Column 2: Race Number
                race_number = cells[2].get_text(strip=True)
                
                # Column 3: Race Class
                race_class = cells[3].get_text(strip=True)
                
                # Column 4: Track Name
                track = cells[4].get_text(strip=True)
                
                # Column 6: Distance
                distance = cells[6].get_text(strip=True)
                
                # Column 7: Jockey
                jockey = cells[7].get_text(strip=True)
                
                # Column 8: Weight
                weight = cells[8].get_text(strip=True)
                
                # Column 9: Merit Rating
                merit_rating = cells[9].get_text(strip=True).strip('()')
                
                # Column 10: Equipment
                equipment = cells[10].get_text(strip=True)
                
                # Column 11: Draw and Field Size
                draw_info = cells[11].get_text(strip=True)
                if '-' in draw_info:
                    draw, field_size = draw_info.split('-')
                else:
                    draw, field_size = None, None
                
                # Column 12: Finishing Position
                position = cells[12].get_text(strip=True)
                
                # Column 13: Lengths Behind
                margin = cells[13].get_text(strip=True)
                
                # Column 15: Time
                time_seconds = cells[15].get_text(strip=True)
                
                # Column 16: Speed Figure
                speed_figure = cells[16].get_text(strip=True)
                
                # Column 17: Starting Price
                sp_price = cells[17].get_text(strip=True)
                
                # Column 20: Comment
                comment = cells[20].get_text(strip=True) if len(cells) > 20 else ""

                run_data = {
                    'date': run_date,
                    'days_since_last_run': days_since_last_run,
                    'track': track,
                    'going': going,
                    'race_class': race_class,
                    'distance': int(distance),
                    'position': int(position),
                    'margin': float(margin) if margin.replace('.', '').isdigit() else 0.0,
                    'weight': float(weight),
                    'merit_rating': int(merit_rating) if merit_rating.isdigit() else None,
                    'jockey': jockey,
                    'draw': int(draw) if draw and draw.isdigit() else None,
                    'field_size': int(field_size) if field_size and field_size.isdigit() else None,
                    'time_seconds': float(time_seconds) if time_seconds.replace('.', '').isdigit() else None,
                    'starting_price': sp_price,
                    'comment': comment,
                    'horse_name': horse_name
                }
                
                parsed_runs.append(run_data)
                
                # PRINT THE RUN DATA TO SCREEN
                if verbosity >= 2:
                    self.stdout.write(f"    📋 Parsed run: {run_date} | {track} | {distance}m | Pos {position} | {margin}L | {jockey}")
                
            except (IndexError, ValueError) as e:
                if verbosity >= 1:
                    self.stdout.write(f"Error parsing row for {horse_name}: {e}")
                continue
            except Exception as e:
                if verbosity >= 1:
                    self.stdout.write(f"Unexpected error parsing row for {horse_name}: {e}")
                continue
        
        return parsed_runs


    def _debug_compartment_content(self, html_content, horse_name):
        """Debug what's actually in the compartment"""
        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            run_rows = soup.find_all('tr', class_='small')
            
            self.stdout.write(f"\n    🔍 DEBUG: Content for {horse_name}'s compartment:")
            self.stdout.write(f"    Found {len(run_rows)} run rows")
            
            for i, row in enumerate(run_rows[:3]):  # Show first 3 rows
                cells = row.find_all('td')
                cell_texts = [cell.get_text(strip=True) for cell in cells[:8]]  # First 8 cells
                self.stdout.write(f"    Row {i}: {cell_texts}")
                
        except Exception as e:
            self.stdout.write(f"    ❌ Debug error: {e}")



    def _display_runs_table(self, runs_data, horse_name):
        """Display runs in a formatted table with enhanced graphics"""
        if not runs_data:
            self.stdout.write(f"    🐎 {horse_name} is a MAIDEN - no previous runs")
            return
        
        # Prepare table data
        table_data = []
        for run in runs_data:
            date_display = run['date'][2:] if len(run['date']) > 8 else run['date']  # Show YY-MM-DD
            track_display = run['track'][:8] if len(run['track']) > 8 else run['track']
            dist_display = str(run['distance'])
            pos_display = str(run['position'])
            
            # Format margin with color based on performance
            margin = run.get('margin', 0)
            if margin == 0:
                margin_display = "🏆WON "  # Winner
            elif margin <= 2.0:
                margin_display = f"🥈{margin:.1f}L"  # Close finish
            elif margin <= 5.0:
                margin_display = f"🥉{margin:.1f}L"  # Placed
            else:
                margin_display = f"{margin:.1f}L"  # Unplaced
            
            weight_display = f"{run['weight']}kg"
            jockey_display = run['jockey'][:8] if len(run['jockey']) > 8 else run['jockey']
            time_display = f"{run['time_seconds']:.1f}" if run.get('time_seconds') else "N/A"
            
            # Add SP (Starting Price) if available
            sp_display = run.get('starting_price', '')[:5]  # Shorten SP
            
            table_data.append([
                date_display, track_display, dist_display, pos_display,
                margin_display, weight_display, jockey_display, time_display, sp_display
            ])
        
        # Display the table with enhanced graphics
        self.stdout.write(f"\n    🏇 RUN HISTORY FOR {horse_name.upper()}")
        self.stdout.write("    ╔══════════╦══════════╦══════╦════╦══════╦════════╦══════════╦══════════╦═══════╗")
        self.stdout.write("    ║   Date   ║  Track   ║ Dist ║Pos ║Margin║ Weight ║  Jockey  ║   Time   ║  SP   ║")
        self.stdout.write("    ╠══════════╬══════════╬══════╬════╬══════╬════════╬══════════╬══════════╬═══════╣")
        
        for row in table_data:
            self.stdout.write(f"    ║ {row[0]:8} ║ {row[1]:8} ║ {row[2]:4} ║ {row[3]:2} ║ {row[4]:4} ║ {row[5]:6} ║ {row[6]:8} ║ {row[7]:8} ║ {row[8]:5} ║")
        
        self.stdout.write("    ╚══════════╩══════════╩══════╩════╩══════╩════════╩══════════╩══════════╩═══════╝")
        
        # Add summary statistics
        total_runs = len(runs_data)
        wins = sum(1 for run in runs_data if run.get('position') == 1)
        places = sum(1 for run in runs_data if 1 < run.get('position', 99) <= 3)
        
        self.stdout.write(f"    📊 Summary: {total_runs} runs | {wins} wins 🏆 | {places} places 🥈🥉")
        
        # Show recent form
        recent_form = ''.join(
            '1' if run['position'] == 1 else
            '2' if run['position'] == 2 else
            '3' if run['position'] == 3 else
            '0' if run['position'] <= 5 else
            'U'
            for run in runs_data[:6]  # Last 6 runs
        )
        
        if recent_form:
            self.stdout.write(f"    📈 Recent form: {recent_form}")

    def _display_runs_table_compact(self, runs_data, horse_name):
        """Alternative compact display for terminals with limited width"""
        if not runs_data:
            self.stdout.write(f"    🐎 {horse_name} is a MAIDEN - no previous runs")
            return
        
        self.stdout.write(f"\n    🏇 {horse_name.upper()} - LAST {len(runs_data)} RUNS")
        self.stdout.write("    ┌────────┬────────┬────┬────┬──────┬──────┬────────┬──────┐")
        self.stdout.write("    │  Date  │ Track  │Dist│Pos │Margin│Weight│ Jockey │  SP  │")
        self.stdout.write("    ├────────┼────────┼────┼────┼──────┼──────┼────────┼──────┤")
        
        for run in runs_data[:8]:  # Show only last 8 runs for compact view
            date_display = run['date'][5:] if len(run['date']) > 8 else run['date']  # Show DD-MM
            track_display = run['track'][:6] if len(run['track']) > 6 else run['track']
            dist_display = str(run['distance'])
            pos_display = str(run['position'])
            margin_display = f"{run['margin']:.1f}L"
            weight_display = f"{run['weight']}kg"
            jockey_display = run['jockey'][:6] if len(run['jockey']) > 6 else run['jockey']
            sp_display = run.get('starting_price', '')[:4]
            
            self.stdout.write(f"    │ {date_display:6} │ {track_display:6} │ {dist_display:2} │ {pos_display:2} │ {margin_display:4} │ {weight_display:4} │ {jockey_display:6} │ {sp_display:4} │")
        
        self.stdout.write("    └────────┴────────┴────┴────┴──────┴──────┴────────┴──────┘")
        

    def _import_runs_for_all_horses(self):
        """Import runs for all horses from their individual compartments"""
        from racecard_02.models import Horse, Run
        
        self.stdout.write("\n" + "="*80)
        self.stdout.write("📊 IMPORTING RUNS FOR ALL HORSES")
        self.stdout.write("="*80)
        
        total_imported = 0
        total_horses_processed = 0
        horses_with_runs = 0
        
        try:
            horses = Horse.objects.all().order_by('horse_no')
            self.stdout.write(f"Found {horses.count()} horses in database")
            
            for horse in horses:
                total_horses_processed += 1
                self.stdout.write(f"\n    [{total_horses_processed}] 📥 Processing {horse.horse_name} (#{horse.horse_no})...")
                
                # Find this horse's compartment
                compartment_html = self._get_horse_past_performance_compartment(horse)
                
                if not compartment_html:
                    self.stdout.write(f"    ⚠️  No past performance compartment found for {horse.horse_name}")
                    continue
                    
                # Parse runs from the compartment
                runs_data = self.parse_horse_runs(compartment_html, horse.horse_name, verbosity=2)
                
                if not runs_data:
                    self.stdout.write(f"    🐎 {horse.horse_name} is a MAIDEN - no previous runs")
                    continue
                
                horses_with_runs += 1
                self.stdout.write(f"    📊 Found {len(runs_data)} runs for {horse.horse_name}")
                
                # DISPLAY THE RUNS IN A TABLE
                self._display_runs_table(runs_data, horse.horse_name)
                    
                # Save runs to database
                horse_runs_imported = 0
                for run_data in runs_data:
                    try:
                        # Convert date string to date object
                        run_date = datetime.strptime(run_data['date'], '%Y-%m-%d').date()
                        
                        # Create or update Run model - USING CORRECT FIELD NAMES
                        run, created = Run.objects.update_or_create(
                            horse=horse,
                            run_date=run_date,  # ✅ Use run_date (database column name)
                            defaults={
                                'track': run_data.get('track', ''),
                                'going': run_data.get('going', ''),
                                'race_class': run_data.get('race_class', ''),
                                'distance': run_data.get('distance', 0),
                                'position': run_data.get('position', 0),
                                'margin': run_data.get('margin', 0.0),
                                'weight': run_data.get('weight', 0.0),
                                'merit_rating': run_data.get('merit_rating', None),
                                'jockey': run_data.get('jockey', ''),
                                'draw': run_data.get('draw', None),
                                'field_size': run_data.get('field_size', None),
                                'time_seconds': run_data.get('time_seconds', None),
                                'starting_price': run_data.get('starting_price', ''),
                                'comment': run_data.get('comment', ''),
                                'days_since_last_run': run_data.get('days_since_last_run', None),
                            }
                        )
                        
                        horse_runs_imported += 1
                        total_imported += 1
                        status = "Created" if created else "Updated"
                        self.stdout.write(f"      💾 {status}: {run_date} - {run_data.get('track', '')} - Pos {run_data.get('position', '')}")
                        
                    except ValueError as e:
                        self.stdout.write(f"      ❌ Date parsing error: {e} - Data: {run_data.get('date', '')}")
                    except Exception as e:
                        self.stdout.write(f"      ❌ Error saving run: {e}")
                        # Debug info
                        self.stdout.write(f"      🔍 Run data: {run_data}")
                
                self.stdout.write(f"    ✅ Imported {horse_runs_imported} runs for {horse.horse_name}")
                    
        except Exception as e:
            self.stdout.write(f"    ❌ Error in run import process: {e}")
            import traceback
            self.stdout.write(f"    Traceback: {traceback.format_exc()}")
        
        # Summary
        self.stdout.write("\n" + "="*80)
        self.stdout.write("📈 RUN IMPORT SUMMARY")
        self.stdout.write("="*80)
        self.stdout.write(f"   Total horses processed: {total_horses_processed}")
        self.stdout.write(f"   Horses with runs found: {horses_with_runs}")
        self.stdout.write(f"   Maiden horses: {total_horses_processed - horses_with_runs}")
        self.stdout.write(f"   Total runs imported: {total_imported}")
        self.stdout.write("="*80)
        
        return total_imported


    def _get_horse_past_performance_compartment(self, horse):
        """Find the HTML compartment for a specific horse's past performance runs"""
        try:
            self.stdout.write(f"    🔍 Searching for past performance compartment of {horse.horse_name} (#{horse.horse_no})...")
            
            # Look for tables that contain PAST RUN data (not future predictions)
            all_tables = self.soup.find_all('table')
            
            for table_idx, table in enumerate(all_tables):
                # Look for tables with run data rows
                run_rows = table.find_all('tr', class_='small')
                
                if not run_rows:
                    continue
                    
                # Check if this table contains PAST performance data
                has_past_performance = False
                for row in run_rows[:3]:  # Check first 3 rows
                    cells = row.find_all('td')
                    if len(cells) > 0:
                        first_cell_text = cells[0].get_text(strip=True)
                        # Past performance tables usually start with dates like "(3) 24.11.10"
                        if re.match(r'\((\d+)\)\s*\d{2}\.\d{2}\.\d{2}', first_cell_text):
                            has_past_performance = True
                            break
                
                if has_past_performance:
                    # Also check if this table contains data for our specific horse
                    horse_numbers = table.find_all(string=re.compile(rf'\b{horse.horse_no}\b'))
                    horse_names = table.find_all(string=re.compile(re.escape(horse.horse_name), re.IGNORECASE))
                    
                    if horse_numbers or horse_names:
                        self.stdout.write(f"    ✅ Found past performance table at index {table_idx} with {len(run_rows)} runs")
                        return str(table)
            
            self.stdout.write(f"    ❌ No past performance compartment found for {horse.horse_name}")
            return None
            
        except Exception as e:
            self.stdout.write(f"    ❌ Error finding compartment for {horse.horse_name}: {e}")
            return None


    