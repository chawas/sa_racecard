import os
import re
from datetime import datetime

from bs4 import BeautifulSoup
import requests

# Import base command class only
from django.core.management.base import BaseCommand

# Service imports
from racecard_02.services.db_service import DatabaseService
from racecard_02.services.enhanced_scoring_service import EnhancedScoringService


class Command(BaseCommand):
    help = 'Import racecard data from HTML files and calculate rankings'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.jt_analysis_cache = {}
        self.current_file_path = None
        # Initialize services with your stdout.write as debug callback
        self.db_service = DatabaseService(debug_callback=self.stdout.write)
        self.scoring_service = EnhancedScoringService(debug_callback=self.stdout.write)

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
        parser.add_argument(
            '--calculate-rankings',
            action='store_true',
            help='Calculate rankings after import'
        )
        parser.add_argument(
            '--ranking-date',
            type=str,
            help='Specific date to calculate rankings for (YYYY-MM-DD)'
        )
        parser.add_argument(
            '--race-id',
            type=int,
            help='Specific race ID to calculate rankings for'
        )
    
    def handle(self, *args, **options):
        # Import ALL Django components inside the handle method
        from django.utils import timezone
        from django.db import transaction
        from django.shortcuts import get_object_or_404
        
        # Import models
        from racecard_02.models import Race, Horse, HorseScore, Run, Ranking

        # Test basic functionality first
        self._test_basic_functionality()

        self.stdout.write("=" * 80)
        self.stdout.write("🚀 STARTING RACECARD IMPORT - HANDLE METHOD")
        self.stdout.write("=" * 80)
        
        filename = options.get('filename')
        target_date = options.get('date')
        update_existing = options.get('update_existing', False)
        calculate_rankings = options.get('calculate_rankings', False)
        ranking_date = options.get('ranking_date')
        race_id = options.get('race_id')
        
        self.stdout.write(f"📋 Parameters received:")
        self.stdout.write(f"   filename: {filename}")
        self.stdout.write(f"   target_date: {target_date}")
        self.stdout.write(f"   update_existing: {update_existing}")
        self.stdout.write(f"   calculate_rankings: {calculate_rankings}")
        self.stdout.write(f"   ranking_date: {ranking_date}")
        self.stdout.write(f"   race_id: {race_id}")
        
        try:
            if filename:
                self.stdout.write(f"📁 Processing specific file: {filename}")
                races = self._process_single_file(filename, update_existing)
                
                # Calculate rankings if requested
                if calculate_rankings and races:
                    for race in races:
                        self._calculate_horse_scores(race)
                elif calculate_rankings:
                    self.calculate_rankings(ranking_date, race_id)
                    
            elif target_date:
                self.stdout.write(f"📅 Processing date: {target_date}")
                self._process_date(target_date, update_existing)
                
                # Calculate rankings if requested
                if calculate_rankings:
                    self.calculate_rankings(target_date, race_id)
            else:
                # Just calculate rankings if no file/date specified but ranking flag is set
                if calculate_rankings:
                    self.calculate_rankings(ranking_date, race_id)
                else:
                    self.stdout.write(self.style.ERROR("❌ Please specify a filename or --date"))
                
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Fatal error: {str(e)}"))
            import traceback
            self.stdout.write(self.style.ERROR(f"Traceback: {traceback.format_exc()}"))

    def _test_basic_functionality(self):
        """Test if basic functionality is working"""
        self.stdout.write("🧪 Testing output system...")
        self.stdout.flush()  # Force output
        
        self.stdout.write("🧪 TESTING BASIC FUNCTIONALITY...")
        
        # Test 1: Basic output
        self.stdout.write("✅ Test 1: Basic stdout.write works")
        
        # Test 2: Service initialization
        try:
            from racecard_02.services.scoring_service import ScoringService
            test_service = ScoringService(debug_callback=self.stdout.write)
            self.stdout.write("✅ Test 2: Service initialization works")
        except Exception as e:
            self.stdout.write(f"❌ Test 2 failed: {e}")
        
        # Test 3: Model import
        try:
            from racecard_02.models import Horse
            self.stdout.write("✅ Test 3: Model import works")
        except Exception as e:
            self.stdout.write(f"❌ Test 3 failed: {e}")
        
        self.stdout.write("🧪 BASIC FUNCTIONALITY TEST COMPLETE")

    def _process_date(self, date_str, update_existing):
        """Process all files for a given date"""
        self.stdout.write(f"📅 Processing date: {date_str}")
        self.stdout.write(self.style.WARNING("⚠️ Date processing not fully implemented yet"))

    def _process_single_file(self, file_path, update_existing):
        """Process a single HTML file and return the races"""
        from racecard_02.models import Race, Horse
        
        self.stdout.write("=" * 60)
        self.stdout.write(f"📁 PROCESSING SINGLE FILE: {file_path}")
        self.stdout.write("=" * 60)
        
        # Check if file exists
        if not os.path.exists(file_path):
            self.stdout.write(self.style.ERROR(f"❌ File does not exist: {file_path}"))
            return []
        
        self.stdout.write(f"✅ File exists, size: {os.path.getsize(file_path)} bytes")
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            self.stdout.write(f"✅ File read successfully, length: {len(html_content)} characters")

            # Store the soup as instance variable for run parsing
            self.current_file_path = file_path
            self.soup = BeautifulSoup(html_content, 'html.parser')
            self.stdout.write("✅ HTML parsed successfully")
            
            # Parse races
            races = self._parse_races(self.soup, update_existing)
            self.stdout.write(self.style.SUCCESS(f"✅ Races processed: {len(races)}"))
            
            if not races:
                self.stdout.write("❌ No races found in file")
                return []
            
            # Parse horses for each race from this file
            for race in races:
                self.stdout.write(f"🐎 Processing horses for Race {race.race_no}...")
                horses_created = self._parse_horses(self.soup, race, update_existing)
                self.stdout.write(self.style.SUCCESS(f"✅ Horses processed for race {race.race_no}: {horses_created}"))
                
                # Verify speed data is stored correctly
                self._verify_speed_data(race)
                
                # IMPORTANT: Import runs for all horses
                self.stdout.write("📊 Starting run import...")
                runs_imported = self._import_runs_for_all_horses()
                self.stdout.write(self.style.SUCCESS(f"✅ Runs imported: {runs_imported}"))
            
            # Calculate scores after all data is imported
            for race in races:
                self.stdout.write(f"📊 Calculating scores for Race {race.race_no}...")
                self._calculate_horse_scores(race)
            
            return races
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error processing file {file_path}: {str(e)}"))
            import traceback
            self.stdout.write(self.style.ERROR(f"Traceback: {traceback.format_exc()}"))
            return []

    def _parse_races(self, soup, update_existing):
        """Parse race information from HTML and return race objects"""
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
        from racecard_02.models import Horse
        
        self.stdout.write(f"\n🔍 Extracting Horses for Race {race.race_no}...")
        created_or_updated = 0
        horse_tables = soup.select('table[border="border"]')

        # FIRST: Extract Magic Tips
        magic_tips_horses = self._extract_magic_tips(soup)
        
        # Store Magic Tips in class variable for later use
        self.magic_tips_horses = magic_tips_horses
        
        self.stdout.write(f"📊 Magic Tips horses to boost: {magic_tips_horses}")

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

                # EXTRACT WEIGHT WITH APPRENTICE ALLOWANCE
                weight = 0.0
                apprentice_allowance = 0.0
                actual_weight = 0.0

                self.stdout.write(f"   🔍 STARTING WEIGHT EXTRACTION DEBUG...")

                # Look for ALL b2 elements first to see what we're working with
                all_b2_elements = table.find_all('div', class_='b2')
                self.stdout.write(f"   📊 Found {len(all_b2_elements)} b2 elements in table:")
                for i, b2_el in enumerate(all_b2_elements):
                    text = self._text(b2_el)
                    self.stdout.write(f"     b2[{i}]: '{text}'")

                # Now try the weight extraction with better debugging
                weight_elements = table.find_all('div', class_='b2')
                for weight_el in weight_elements:
                    weight_text = self._text(weight_el)
                    self.stdout.write(f"   🔍 Checking b2 element: '{weight_text}'")
                    
                    if weight_text and '.' in weight_text:  # Looks like a weight (e.g., "64.0")
                        try:
                            # This might be the weight value
                            weight_value = float(weight_text)
                            self.stdout.write(f"   ✅ Found potential weight value: {weight_value}kg")
                            
                            # Check if this is followed by an apprentice allowance
                            next_sibling = weight_el.find_next_sibling(string=True)
                            self.stdout.write(f"   🔍 Next sibling text: '{next_sibling}'")
                            
                            if next_sibling and '-' in next_sibling:
                                # Found apprentice allowance (e.g., "-4.0")
                                allowance_match = re.search(r'-(\d+\.?\d*)', next_sibling)
                                if allowance_match:
                                    apprentice_allowance = float(allowance_match.group(1))
                                    actual_weight = weight_value - apprentice_allowance
                                    self.stdout.write(f"   ✅ Weight: {weight_value}kg, Allowance: -{apprentice_allowance}kg, Actual: {actual_weight}kg")
                                else:
                                    actual_weight = weight_value
                                    self.stdout.write(f"   ✅ Weight without allowance: {actual_weight}kg")
                            else:
                                actual_weight = weight_value
                                self.stdout.write(f"   ✅ Weight (no allowance found): {actual_weight}kg")
                                
                            weight = actual_weight
                            break
                            
                        except ValueError as e:
                            self.stdout.write(f"   ❌ Error converting '{weight_text}' to float: {e}")
                            continue

                # If still no weight found, try pattern matching on entire table
                if weight == 0.0:
                    self.stdout.write("   🔍 Trying pattern matching on entire table...")
                    table_text = table.get_text()
                    self.stdout.write(f"   📄 Table text sample: {table_text[:200]}...")
                    
                    weight_patterns = [
                        r'(\d+\.?\d*)\s*-\s*(\d+\.?\d*)',  # "64.0 -4.0"
                        r'(\d+\.?\d*)\s*/\s*-\s*(\d+\.?\d*)',  # "64.0/-4.0"
                        r'(\d+\.?\d*)\s*\(-\s*(\d+\.?\d*)\)',  # "64.0 (-4.0)"
                    ]
                    
                    for pattern in weight_patterns:
                        match = re.search(pattern, table_text)
                        if match:
                            try:
                                weight_value = float(match.group(1))
                                apprentice_allowance = float(match.group(2))
                                actual_weight = weight_value - apprentice_allowance
                                weight = actual_weight
                                self.stdout.write(f"   ✅ Found weight via pattern '{pattern}': {weight_value}kg - {apprentice_allowance}kg = {actual_weight}kg")
                                break
                            except ValueError as e:
                                self.stdout.write(f"   ❌ Pattern match error: {e}")
                                continue

                # Final fallback
                if weight == 0.0:
                    # Default weight based on race type
                    if 'handicap' in race.race_class.lower():
                        weight = 60.0
                        actual_weight = 60.0
                    else:
                        weight = 57.0
                        actual_weight = 57.0
                    self.stdout.write(f"   ⚠️ Using default weight: {weight}kg")

                self.stdout.write(f"   🏁 FINAL WEIGHT: {weight}kg, Allowance: {apprentice_allowance}kg, Actual: {actual_weight}kg")

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
                    weight=weight,  # Add weight field
                    apprentice_allowance=apprentice_allowance,  # Add allowance field
                    actual_weight=actual_weight,  # Add calculated actual weight
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

    def _calculate_horse_scores(self, race):
        """USE ENHANCED SCORING SERVICE with Magic Tips"""
        from racecard_02.models import HorseScore
        
        self.stdout.write(f"📊 Calculating Magic Tips rankings for Race {race.race_no}...")
        
        # Extract Magic Tips
        magic_tips = self._extract_magic_tips(self.soup)
        self.stdout.write(f"🎯 Magic Tips horses: {magic_tips}")
        
        try:
            # Set Magic Tips in scoring service
            self.scoring_service.set_magic_tips(magic_tips)
            
            # Calculate scores using the enhanced service
            horse_scores = self.scoring_service.calculate_scores_for_race(race)
            
            if not horse_scores:
                self.stdout.write("❌ No horse scores calculated")
                return
            
            # Use database service to save rankings
            rankings_count = self.db_service.save_rankings(race, horse_scores, magic_tips)
            
            if rankings_count > 0:
                # Display the results using service
                self.db_service.display_rankings(race)
            else:
                # Fallback to display calculated scores
                self._display_calculated_scores(race, horse_scores, magic_tips)
                
        except Exception as e:
            self.stdout.write(f"❌ Error in service pipeline: {e}")
            import traceback
            self.stdout.write(f"Traceback: {traceback.format_exc()}")
            # Fallback to your original logic
            self._fallback_calculate_rankings(race, magic_tips)

    def _display_calculated_scores(self, race, horse_scores, magic_tips):
        """Display calculated scores without database ranking - FIXED VERSION"""
        # horse_scores contains dictionaries, not model objects
        
        # Apply Magic Tips boost and create display data
        display_scores = []
        for score_data in horse_scores:
            try:
                horse_no = score_data.get('horse_no')
                horse_name = score_data.get('horse_name', 'Unknown')
                base_score = score_data.get('composite_score', 0)
                
                is_magic_tip = horse_no in magic_tips
                final_score = (base_score * 0.5) + (100 * 0.5) if is_magic_tip else base_score
                
                display_scores.append({
                    'horse_no': horse_no,
                    'horse_name': horse_name,
                    'base_score': base_score,
                    'final_score': final_score,
                    'is_magic_tip': is_magic_tip
                })
            except Exception as e:
                self.stdout.write(f"❌ Error processing score data: {e}")
                continue
        
        # Sort by final_score
        sorted_scores = sorted(display_scores, key=lambda x: x['final_score'], reverse=True)
        
        self.stdout.write(f"\n🔢 CALCULATED SCORES WITH MAGIC TIPS - Race {race.race_no}")
        self.stdout.write("=" * 80)
        self.stdout.write("Rank  Horse No  Horse Name          Base Score  Final Score  Magic Tip")
        self.stdout.write("-" * 80)
        
        for rank, score_data in enumerate(sorted_scores, 1):
            is_magic_tip = score_data['is_magic_tip']
            star = "✨" if is_magic_tip else ""
            
            self.stdout.write(
                f"{rank:2d}    {score_data['horse_no']:2d}      {score_data['horse_name']:<18}  "
                f"{score_data['base_score']:>10.1f}  {score_data['final_score']:>11.1f}  {star}"
            )
        
        self.stdout.write("=" * 80)

    
    def _fallback_calculate_rankings(self, race, magic_tips):
        """Fallback to your original ranking calculation logic"""
        from racecard_02.models import HorseScore
        
        self.stdout.write("🔄 Falling back to original ranking logic...")
        
        # Get all horse scores for this race
        horse_scores = HorseScore.objects.filter(race=race).select_related('horse')
        
        if not horse_scores.exists():
            self.stdout.write("❌ No horse scores found for this race")
            return
        
        # Apply Magic Tips and display
        display_scores = []
        for score in horse_scores:
            is_magic_tip = score.horse.horse_no in magic_tips
            final_score = (score.overall_score * 0.5) + (100 * 0.7) if is_magic_tip else score.overall_score
            
            display_scores.append({
                'horse': score.horse,
                'base_score': score.overall_score,
                'final_score': final_score,
                'is_magic_tip': is_magic_tip
            })
        
        # Sort by final_score
        sorted_scores = sorted(display_scores, key=lambda x: x['final_score'], reverse=True)
        
        self.stdout.write(f"\n🔢 FALLBACK RANKINGS - Race {race.race_no}")
        self.stdout.write("=" * 70)
        self.stdout.write("Rank  Horse No  Horse Name          Base Score  Final Score  Magic Tip")
        self.stdout.write("-" * 70)
        
        for rank, score_data in enumerate(sorted_scores, 1):
            star = "✨" if score_data['is_magic_tip'] else ""
            self.stdout.write(
                f"{rank:2d}    {score_data['horse'].horse_no:2d}      {score_data['horse'].horse_name:<18}  "
                f"{score_data['base_score']:>10.1f}  {score_data['final_score']:>11.1f}  {star}"
            )
        
        self.stdout.write("=" * 70)



    def _display_calculated_rankings(self, race, horse_scores, magic_tips):
        """Fallback display without database"""
        sorted_scores = sorted(horse_scores, key=lambda x: x.overall_score, reverse=True)
        
        self.stdout.write(f"\n🔢 CALCULATED RANKINGS - Race {race.race_no}")
        self.stdout.write("="*70)
        
        for rank, score in enumerate(sorted_scores, 1):
            is_magic_tip = score.horse.horse_no in magic_tips
            final_score = (score.overall_score * 0.5) + (100 * 0.5) if is_magic_tip else score.overall_score
            
            star = "✨" if is_magic_tip else ""
            self.stdout.write(f"{rank:2d}. {star} {score.horse.horse_name}: {final_score:.1f} {star}")
        
        self.stdout.write("="*70)

    def _extract_magic_tips(self, soup):
        """Extract Magic Tips from HTML"""
        import re
        
        self.stdout.write("🔍 Searching for Magic Tips pattern...")
        
        # Convert soup to text and search for pattern
        html_text = str(soup)
        match = re.search(r'Magic Tips:\s*(\d+-\d+-\d+-\d+-\d+)', html_text)
        
        if match:
            numbers = [int(x) for x in match.group(1).split('-')]
            self.stdout.write(f"✅ Found Magic Tips: {numbers}")
            return numbers
        
        # Alternative pattern search
        match = re.search(r'Magic Tips[^0-9]*([0-9][0-9,\-\s]+[0-9])', html_text)
        if match:
            numbers_str = match.group(1)
            numbers = [int(x) for x in re.findall(r'\d+', numbers_str)][:5]  # Take first 5 numbers
            self.stdout.write(f"✅ Found Magic Tips (alt pattern): {numbers}")
            return numbers
        
        self.stdout.write("⚠️ No Magic Tips pattern found - using empty list")
        return []

    def calculate_rankings(self, ranking_date=None, race_id=None):
        """Calculate rankings for specific date or race"""
        from racecard_02.models import Race
        
        self.stdout.write("📊 Calculating rankings...")
        
        if race_id:
            races = Race.objects.filter(id=race_id)
        elif ranking_date:
            races = Race.objects.filter(race_date=ranking_date)
        else:
            # Calculate for recent races
            from django.utils import timezone
            from datetime import timedelta
            recent_date = timezone.now().date() - timedelta(days=7)
            races = Race.objects.filter(race_date__gte=recent_date)
        
        for race in races:
            self.stdout.write(f"🔍 Processing race {race.race_no} on {race.race_date}")
            self._calculate_horse_scores(race)