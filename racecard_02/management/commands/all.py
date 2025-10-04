1. we already have a working implementation except the class and form are not yet ingesting into database. we have to work on it now.

so i will attach the relevant scripts so that you can put the methods into appropriate scripts remove redundant defs and cleanup everything into a working system::

the scripts are long but we need to streamline them first::

# racecard_02/management/commands/import_racecard_02.py
import os
import sys
import django
import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests

# Django setup
sys.path.append('/home/wrf/deployed/django/projects/sa_racecard')
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'sa_racecard.settings')
django.setup()

from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import transaction
from django.shortcuts import get_object_or_404

from racecard_02.models import Race, Horse, HorseScore
from racecard_02.services.scoring_service import ScoringService

from racecard_02.services.run_analysis import RunAnalysisService
from racecard_02.services.scoring_service import ScoringService


# Initialize the service
run_service = RunAnalysisService(debug_callback=print)
scoring_service = ScoringService(debug_callback=print)

class Command(BaseCommand):
    help = 'Import racecard data from HTML files'
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.jt_analysis_cache = {}
        self.current_file_path = None

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


        # After importing horses, import their runs
        self._import_runs_for_all_horses()


        # After importing horses and races, you need to get the race object
        try:
            from racecard_02.models import Race
            
            # Get the race you just imported (adjust this based on your logic)
            # Example: get the most recent race or a specific race
            race = Race.objects.order_by('-id').first()  # Gets the most recent race
            
            if race:
                self.stdout.write(f"📊 Calculating scores for race: {getattr(race, 'race_name', 'Unknown')}")
                
                # First import runs if needed
                self._import_runs_for_all_horses()
                
                # Then calculate scores
                self._calculate_horse_scores(race)
            else:
                self.stdout.write("❌ No races found in database")
                
        except Exception as e:
            self.stdout.write(f"❌ Error in score calculation: {e}")
            
        # Then calculate scores
        self._calculate_horse_scores(race)
            
    def _process_date(self, date_str, update_existing):
        """Process all files for a given date"""
        self.stdout.write(f"📅 Processing date: {date_str}")
        self.stdout.write(self.style.WARNING("⚠️ Date processing not fully implemented yet"))
    
    def _process_single_file(self, file_path, update_existing):
        """Process a single HTML file and return the races"""
        self.stdout.write(f"📁 Processing file: {file_path}")
        self.current_file_path = file_path
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                html_content = f.read()
            
            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Parse races
            races = self._parse_races(soup, update_existing)
            self.stdout.write(self.style.SUCCESS(f"✅ Races processed: {len(races)}"))
            
            # Parse horses for each race from this file
            for race in races:
                horses_created = self._parse_horses(soup, race, update_existing)
                self.stdout.write(self.style.SUCCESS(f"✅ Horses processed for race {race.race_no}: {horses_created}"))
                
                # Verify speed data is stored correctly
                self._verify_speed_data(race)
                # Calculate scores
                self._calculate_horse_scores(race)
            
            return races
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error processing file {file_path}: {str(e)}"))
            import traceback
            self.stdout.write(self.style.ERROR(f"Traceback: {traceback.format_exc()}"))
            return []
    
    def _parse_races(self, soup, update_existing):
        """Parse race information from HTML and return race objects"""
        self.stdout.write("🔍 Extracting Races...")
        races = []
        
        # DEBUG: Let's see what's actually in the HTML
        self.stdout.write("=== DEBUG: Looking for race elements ===")
        
        # Try different selectors to find races
        possible_selectors = [
            'div.race-header', 'div.race', 'table.race', 
            'div.event', 'div.race-card', 'div.raceinfo',
            'h2', 'h3', '.race-title', '.race-name'
        ]
        
        for selector in possible_selectors:
            elements = soup.select(selector)
            if elements:
                self.stdout.write(f"Found {len(elements)} elements with selector: '{selector}'")
                for i, elem in enumerate(elements[:3]):
                    text = elem.get_text(strip=True)
                    self.stdout.write(f"  {i+1}. '{text}'")
        
        # Fallback: Create a race from filename
        self.stdout.write("⚠️ No races found with selectors, creating from filename...")
        
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

    def _parse_horses(self, soup, race, update_existing: bool):
        """Parse horse blocks"""
        self.stdout.write(f"\n🔍 Extracting Horses for Race {race.race_no}...")
        created_or_updated = 0
        horse_tables = soup.select('table[border="border"]')
        self.stdout.write(f"Found {len(horse_tables)} horse tables")
        
        # DEBUG: See what's in the tables
        self._debug_horse_tables(horse_tables)
        
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

    def _debug_horse_tables(self, horse_tables):
        """Debug method to see what's in the horse tables"""
        self.stdout.write("\n" + "="*50)
        self.stdout.write("🔍 DEBUG: HORSE TABLE ANALYSIS")
        self.stdout.write("="*50)
        
        for idx, table in enumerate(horse_tables[:3]):
            self.stdout.write(f"\nTable {idx+1}:")
            self.stdout.write(f"HTML: {str(table)[:200]}...")
            
            b4_divs = table.find_all('div', class_='b4')
            self.stdout.write(f"b4 divs found: {len(b4_divs)}")
            for div in b4_divs:
                self.stdout.write(f"  b4 text: '{div.get_text(strip=True)}'")
            
            b1_divs = table.find_all('div', class_='b1')
            self.stdout.write(f"b1 divs found: {len(b1_divs)}")
            for div in b1_divs:
                self.stdout.write(f"  b1 text: '{div.get_text(strip=True)}'")
            
            numbers = re.findall(r'\b\d+\b', table.get_text())
            self.stdout.write(f"Numbers found: {numbers}")
        
        self.stdout.write("="*50 + "\n")
        
    def _calculate_horse_scores(self, race):
        """Calculate scores for all horses in a race and display rankings"""
        self.stdout.write(f"\n📊 Calculating scores for Race {race.race_no}...")
        
        horses = Horse.objects.filter(race=race)
        self.stdout.write(f"Found {horses.count()} horses in database for this race")
        
        scores_data = []
        
        for horse in horses:
            try:
                self.stdout.write(f"    🐎 Processing {horse.horse_name} (No. {horse.horse_no})...")
                
                # Use debug callback for scoring service


                scoring_service = ScoringService(
                    debug_callback=lambda msg: self.stdout.write(f"    📊 {msg}")
                )
                score_record, created = scoring_service.create_score_record(horse, race)
                
                status = "Created" if created else "Updated"
                self.stdout.write(f"    ✅ {status} score for {horse.horse_name}: {score_record.overall_score}")
                
                scores_data.append({
                    'horse': horse,
                    'score_record': score_record,
                    'overall_score': score_record.overall_score
                })
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    ❌ Error scoring {horse.horse_name}: {e}"))
                import traceback
                self.stdout.write(self.style.ERROR(f"    Traceback: {traceback.format_exc()}"))
        
        if scores_data:
            self._display_detailed_rankings(scores_data, race)
        else:
            self.stdout.write("❌ No scores calculated for ranking display")

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

    def _display_detailed_rankings(self, scores_data, race):
        """Display detailed rankings with component scores"""
        self.stdout.write("\n" + "="*100)
        self.stdout.write(f"📊 DETAILED RANKINGS - Race {race.race_no}")
        self.stdout.write("="*100)
        
        sorted_rankings = sorted(scores_data, key=lambda x: x['overall_score'], reverse=True)
        
        header = f"{'Pos':<4} {'No':<4} {'Horse':<20} {'Total':<6} {'BestMR':<6} {'CurMR':<6} {'JT':<6} {'Form':<6} {'Class':<6} {'Speed':<6}"
        self.stdout.write(header)
        self.stdout.write("-" * 100)
        
        for position, data in enumerate(sorted_rankings, 1):
            horse = data['horse']
            score_record = data['score_record']
            
            # Debug: Show what speed data we have
            speed_debug = f" (Horse speed_rating: {getattr(horse, 'speed_rating', 'N/A')})"
            
            self.stdout.write(
                f"{position:<4} "
                f"{horse.horse_no:<4} "
                f"{horse.horse_name:<20.20} "  # Truncate long names
                f"{score_record.overall_score:<6.1f} "
                f"{getattr(score_record, 'best_mr_score', 0):<6.1f} "
                f"{getattr(score_record, 'current_mr_score', 0):<6.1f} "
                f"{getattr(score_record, 'jt_score', 0):<6.1f} "
                f"{getattr(score_record, 'form_score', 0):<6.1f} "
                f"{getattr(score_record, 'class_score', 0):<6.1f} "
                f"{getattr(score_record, 'speed_rating', 0):<6.1f}"
            )
            # Show debug info for speed
            self.stdout.write(f"      Speed debug: {speed_debug}")
        
        self.stdout.write("="*100)

    def _verify_speed_data(self, race):
        """Verify that speed data is being stored correctly"""
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




    def link_existing_runs(self):
        """Link runs to horses based on horse name"""
        from racecard_02.models import Horse, Run
        
        self.stdout.write("=== LINKING EXISTING RUNS TO HORSES ===")
        
        # Get all unlinked runs (where horse is None)
        unlinked_runs = Run.objects.filter(horse__isnull=True)
        self.stdout.write(f"Found {unlinked_runs.count()} unlinked runs")
        
        linked_count = 0
        for run in unlinked_runs:
            # Try to find a horse by name (you might need to adjust this logic)
            try:
                # Check if run has a horse_name field, otherwise we need another approach
                if hasattr(run, 'horse_name') and run.horse_name:
                    horse = Horse.objects.get(horse_name=run.horse_name)
                    run.horse = horse
                    run.save()
                    linked_count += 1
                    self.stdout.write(f"Linked run {run.id} to horse {horse.id} ({horse.horse_name})")
            except Horse.DoesNotExist:
                continue
            except Horse.MultipleObjectsReturned:
                self.stdout.write(f"Multiple horses found for name '{run.horse_name}' - need manual linking")
            except Exception as e:
                self.stdout.write(f"Error linking run {run.id}: {e}")
        
        self.stdout.write(f"Successfully linked {linked_count} runs")





    def _calculate_horse_scores(self, race):
        """Calculate scores for all horses in a race"""
        from racecard_02.models import Run
        from racecard_02.services.scoring_service import ScoringService
        
        self.stdout.write(f"    Calculating scores for Race {race.race_no}...")
        
        # First, try to link any unlinked runs
        self.link_existing_runs()
        
        horses = race.horse_set.all()
        self.stdout.write(f"    Found {horses.count()} horses in race")
        
        for i, horse in enumerate(horses, 1):
            self.stdout.write(f"    🐎 Processing {horse.horse_name} (Horse {i} of {horses.count()})...")
            
            # Get all runs for this horse (linked + by name)
            linked_runs = Run.objects.filter(horse=horse)
            
            # Check if Run model has horse_name field for fallback lookup
            run_has_horse_name = hasattr(Run, 'horse_name')
            if run_has_horse_name:
                runs_by_name = Run.objects.filter(horse_name__iexact=horse.horse_name).exclude(horse=horse)
            else:
                runs_by_name = Run.objects.none()
            
            self.stdout.write(f"    🔍 Linked runs: {linked_runs.count()}")
            self.stdout.write(f"    🔍 Runs by name: {runs_by_name.count()}")
            
            # Combine all runs and extract data for scoring
            all_runs = list(linked_runs) + list(runs_by_name)
            self.stdout.write(f"    🔍 Total runs available: {len(all_runs)}")
            
            # Extract run data for scoring service
            run_data = []
            for run in all_runs:
                run_data.append({
                    'id': run.id,
                    'run_date': getattr(run, 'run_date', None),
                    'position': getattr(run, 'position', None),
                    'distance': getattr(run, 'distance', None),
                    'margin': getattr(run, 'margin', None),
                    'race_class': getattr(run, 'race_class', None),
                    'horse_name': getattr(run, 'horse_name', None),
                    'horse_no': getattr(run, 'horse_no', None),
                    # Add any other run fields needed for scoring
                })
            
            # Extract horse data for scoring service
            horse_data = {
                'id': horse.id,
                'horse_name': horse.horse_name,
                'horse_no': horse.horse_no,
                'blinkers': horse.blinkers,
                # Add any other horse fields needed for scoring
            }
            
            # Use debug callback for scoring service
            scoring_service = ScoringService(
                debug_callback=lambda msg: self.stdout.write(f"    📊 {msg}")
            )
            
            try:
                # Pass data to scoring service instead of ORM objects
                score_record, created = scoring_service.create_score_record(
                    horse_data=horse_data,
                    run_data=run_data,
                    race_data={
                        'id': race.id,
                        'race_no': race.race_no,
                        'race_name': race.race_name,
                        'race_date': race.race_date,
                        'race_distance': race.race_distance,
                        'race_class': race.race_class,
                        # Add any other race fields needed for scoring
                    }
                )
                
                # Handle the score record response
                if isinstance(score_record, dict) and 'overall_score' in score_record:
                    overall_score = score_record['overall_score']
                    status = "Created" if created else "Updated"
                    self.stdout.write(f"    ✅ {status} score for {horse.horse_name}: {overall_score}")
                elif hasattr(score_record, 'overall_score'):
                    overall_score = score_record.overall_score
                    status = "Created" if created else "Updated"
                    self.stdout.write(f"    ✅ {status} score for {horse.horse_name}: {overall_score}")
                else:
                    self.stdout.write(f"    ⚠️ Could not calculate score for {horse.horse_name}")
                    
            except Exception as e:
                self.stdout.write(f"    ❌ Error scoring {horse.horse_name}: {e}")
                import traceback
                self.stdout.write(f"    🔍 Full traceback: {traceback.format_exc()}")
            
            self.stdout.write(f"    {'='*60}")


    def _import_runs_for_horse(self, horse, run_data):
        """Import runs for a specific horse"""
        try:
            from racecard_02.models import Run
            from datetime import datetime
            
            imported_count = 0
            for run_info in run_data:
                # Create or update run record
                run, created = Run.objects.get_or_create(
                    horse=horse,
                    run_date=run_info['date'],
                    defaults={
                        'track': run_info.get('track', ''),
                        'race_class': run_info.get('race_class', ''),
                        'distance': run_info.get('distance', ''),
                        'position': run_info.get('position', ''),
                        'jockey': run_info.get('jockey', ''),
                        'margin': run_info.get('margin', ''),
                        'weight': run_info.get('weight', ''),
                        # Add other run fields as needed
                    }
                )
                
                if created:
                    imported_count += 1
                    
            return imported_count
            
        except Exception as e:
            self.stdout.write(f"    ❌ Error importing runs for {horse.horse_name}: {e}")
            return 0
        

    def _parse_runs_from_html(self, html_content, horse_name):
        """Parse run data from HTML content"""
        try:
            from bs4 import BeautifulSoup
            import re
            from datetime import datetime
            
            soup = BeautifulSoup(html_content, 'html.parser')
            runs = []
            
            # Find all run rows (adjust selector based on your HTML structure)
            run_rows = soup.find_all('tr', class_='small')
            
            for row in run_rows:
                try:
                    cells = row.find_all('td')
                    if len(cells) < 15:  # Adjust based on your column count
                        continue
                    
                    # Extract data from each cell - adjust based on your HTML structure
                    date_str = cells[0].get_text().strip()
                    track = cells[1].get_text().strip()
                    race_class = cells[4].get_text().strip()
                    distance_str = cells[6].get_text().strip()
                    jockey = cells[7].get_text().strip()
                    weight = cells[8].get_text().strip()
                    
                    # Extract position (from the span with class "r")
                    position_span = cells[11].find('span', class_='r')
                    position = position_span.get_text().strip() if position_span else None
                    
                    # Extract margin (remove quotes)
                    margin = cells[11].get_text().replace('"', '').strip()
                    
                    # Parse date
                    try:
                        run_date = datetime.strptime(date_str, '%d.%m.%y').date()
                    except:
                        # Try different date formats if needed
                        try:
                            run_date = datetime.strptime(date_str, '%y.%m.%d').date()
                        except:
                            run_date = None
                    
                    # Parse distance
                    distance_match = re.search(r'\d+', distance_str)
                    distance = distance_match.group() if distance_match else None
                    
                    if run_date:  # Only add if we have a valid date
                        runs.append({
                            'date': run_date,
                            'track': track,
                            'race_class': race_class,
                            'distance': distance,
                            'jockey': jockey,
                            'position': position,
                            'margin': margin,
                            'weight': weight,
                        })
                        
                except Exception as e:
                    self.stdout.write(f"    ⚠️ Error parsing run row: {e}")
                    continue
                    
            return runs
            
        except Exception as e:
            self.stdout.write(f"    ❌ Error parsing HTML: {e}")
            return []
        

    def _import_runs_for_all_horses(self):
        """Import runs for all horses"""
        self.stdout.write("\n=== IMPORTING RUNS FOR HORSES ===")
        
        try:
            from racecard_02.models import Horse
            
            total_imported = 0
            horses = Horse.objects.all()
            
            for horse in horses:
                self.stdout.write(f"    📥 Importing runs for {horse.horse_name}...")
                
                # TODO: You need to get the HTML content for each horse's runs
                # This could be from a file, URL, or stored data
                html_content = self._get_horse_runs_html(horse)
                
                if html_content:
                    runs_data = self._parse_runs_from_html(html_content, horse.horse_name)
                    imported_count = self._import_runs_for_horse(horse, runs_data)
                    total_imported += imported_count
                    self.stdout.write(f"    ✅ Imported {imported_count} runs for {horse.horse_name}")
                else:
                    self.stdout.write(f"    ⚠️ No HTML content found for {horse.horse_name}")
                    
            self.stdout.write(f"    🎯 Total runs imported: {total_imported}")
            
        except Exception as e:
            self.stdout.write(f"    ❌ Error importing runs: {e}")::

"""
Scoring Service Module
Handles horse racing scoring calculations without Django dependencies
"""

import math
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Any


class ScoringService:
    """
    Service for calculating horse racing performance scores
    """
    
    def __init__(self, debug_callback=None):
        """
        Initialize scoring service
        
        Args:
            debug_callback: Function to call with debug messages
        """
        self.debug_callback = debug_callback
        self.default_score = 50.0
    
    def _debug(self, msg: str) -> None:
        """Send debug message if callback is provided"""
        if self.debug_callback:
            self.debug_callback(msg)
    
    def create_score_record(self, horse_data: Dict, run_data: List[Dict], 
                          race_data: Dict) -> Tuple[Dict, bool]:
        """
        Calculate scores for a horse based on its past runs
        
        Args:
            horse_data: Dictionary containing horse information
            run_data: List of dictionaries containing past run data
            race_data: Dictionary containing current race information
            
        Returns:
            Tuple of (score_record_dict, created_flag)
        """
        self._debug(f"🐎 Scoring horse: {horse_data.get('horse_name', 'Unknown')}")
        self._debug(f"🏇 Current race: R{race_data.get('race_no', '?')} - {race_data.get('race_name', 'Unknown')}")
        self._debug(f"📊 Analyzing {len(run_data)} past runs")
        
        # Calculate various score components
        scores = self._calculate_all_scores(run_data, horse_data, race_data)
        
        # Calculate overall weighted score
        overall_score = self._calculate_overall_score(scores)
        
        # Prepare score record
        score_record = {
            'overall_score': overall_score,
            'speed_score': scores['speed'],
            'consistency_score': scores['consistency'],
            'recent_form_score': scores['recent_form'],
            'class_score': scores['class'],
            'distance_score': scores['distance'],
            'horse_id': horse_data.get('id'),
            'horse_name': horse_data.get('horse_name'),
            'race_id': race_data.get('id'),
            'race_no': race_data.get('race_no'),
            'calculated_at': datetime.now().isoformat(),
            'run_count': len(run_data),
            'metadata': {
                'weighting_used': self._get_score_weights(),
                'run_dates_analyzed': [run.get('run_date') for run in run_data[:5]]  # First 5 runs
            }
        }
        
        self._debug(f"✅ Final score: {overall_score:.1f}")
        return score_record, True
    
    def _calculate_all_scores(self, run_data: List[Dict], 
                            horse_data: Dict, 
                            race_data: Dict) -> Dict[str, float]:
        """Calculate all individual score components"""
        if not run_data:
            self._debug("📭 No past runs - using default scores")
            return self._get_default_scores()
        
        return {
            'speed': self._calculate_speed_score(run_data),
            'consistency': self._calculate_consistency_score(run_data),
            'recent_form': self._calculate_recent_form_score(run_data),
            'class': self._calculate_class_score(run_data, race_data),
            'distance': self._calculate_distance_score(run_data, race_data),
        }
    
    def _calculate_speed_score(self, run_data: List[Dict]) -> float:
        """Calculate score based on finishing positions"""
        valid_positions = []
        
        for run in run_data:
            position = self._parse_position(run.get('position'))
            if position is not None and position > 0:
                valid_positions.append(position)
        
        if not valid_positions:
            return self.default_score
        
        # Convert positions to scores (1st = 100, 2nd = 90, etc.)
        position_scores = [max(0, 100 - (pos * 10)) for pos in valid_positions]
        avg_score = sum(position_scores) / len(position_scores)
        
        self._debug(f"   🏁 Speed score: {avg_score:.1f} (from {len(valid_positions)} positions)")
        return avg_score
    
    def _calculate_consistency_score(self, run_data: List[Dict]) -> float:
        """Calculate consistency based on position variance"""
        positions = []
        
        for run in run_data:
            position = self._parse_position(run.get('position'))
            if position is not None and position > 0:
                positions.append(position)
        
        if len(positions) < 2:
            return self.default_score
        
        # Lower variance = more consistent = higher score
        avg_position = sum(positions) / len(positions)
        variance = sum((p - avg_position) ** 2 for p in positions) / len(positions)
        consistency = max(0, 100 - (variance * 5))
        
        self._debug(f"   📈 Consistency: {consistency:.1f} (variance: {variance:.2f})")
        return consistency
    
    def _calculate_recent_form_score(self, run_data: List[Dict]) -> float:
        """Give more weight to recent performances"""
        if not run_data:
            return self.default_score
        
        # Sort runs by date (most recent first)
        dated_runs = []
        for run in run_data:
            run_date = self._parse_date(run.get('run_date'))
            if run_date:
                dated_runs.append((run_date, run))
        
        if not dated_runs:
            return self.default_score
        
        dated_runs.sort(key=lambda x: x[0], reverse=True)
        
        # Weight recent runs more heavily (last 3 runs)
        recent_runs = dated_runs[:3]
        total_weight, weighted_score = 0, 0
        
        for i, (date, run) in enumerate(recent_runs):
            weight = 3 - i  # 3, 2, 1 weights for most recent to least recent
            position = self._parse_position(run.get('position'))
            
            if position and position > 0:
                run_score = max(0, 100 - (position * 10))
                weighted_score += run_score * weight
                total_weight += weight
        
        if total_weight > 0:
            form_score = weighted_score / total_weight
            self._debug(f"   🔥 Recent form: {form_score:.1f} (last {len(recent_runs)} runs)")
            return form_score
        
        return self.default_score
    
    def _calculate_class_score(self, run_data: List[Dict], race_data: Dict) -> float:
        """Score based on class of previous races vs current race"""
        # This is a simplified implementation
        # You would expand this with actual class comparison logic
        current_class = race_data.get('race_class', '')

        if not run_data:
            return self.default_score
        
        # Count runs in similar or better class
        similar_class_runs = 0
        for run in run_data:
            run_class = run.get('race_class', '')
            if run_class and current_class:
                # Simple class comparison - expand with actual logic
                if run_class == current_class:
                    similar_class_runs += 1
        
        class_score = min(100, self.default_score + (similar_class_runs * 5))
        self._debug(f"   🏆 Class score: {class_score:.1f} ({similar_class_runs} similar class runs)")
        return class_score
    
    def _calculate_distance_score(self, run_data: List[Dict], race_data: Dict) -> float:
        """Score based on distance suitability"""
        # Simplified distance analysis
        current_distance = race_data.get('race_distance', '')
        
        if not run_data or not current_distance:
            return self.default_score
        
        # Count runs at similar distance
        similar_distance_runs = 0
        for run in run_data:
            run_distance = run.get('distance', '')
            if run_distance and self._is_similar_distance(run_distance, current_distance):
                similar_distance_runs += 1
        
        distance_score = min(100, self.default_score + (similar_distance_runs * 3))
        self._debug(f"   📏 Distance score: {distance_score:.1f} ({similar_distance_runs} similar distance runs)")
        return distance_score
    
    def _calculate_overall_score(self, scores: Dict[str, float]) -> float:
        """Calculate weighted overall score"""
        weights = self._get_score_weights()
        
        total_weight = 0
        weighted_sum = 0
        
        for score_type, weight in weights.items():
            if score_type in scores:
                weighted_sum += scores[score_type] * weight
                total_weight += weight
        
        if total_weight > 0:
            overall_score = weighted_sum / total_weight
            return round(overall_score, 1)
        
        return self.default_score
    
    def _get_score_weights(self) -> Dict[str, float]:
        """Get weights for different score components"""
        return {
            'speed': 0.4,           # 40% weight to speed/position
            'recent_form': 0.3,      # 30% to recent form
            'consistency': 0.15,     # 15% to consistency
            'class': 0.1,            # 10% to class
            'distance': 0.05,        # 5% to distance
        }
    
    def _get_default_scores(self) -> Dict[str, float]:
        """Return default scores when no run data is available"""
        return {key: self.default_score for key in self._get_score_weights().keys()}
    
    def _parse_position(self, position: Any) -> Optional[int]:
        """Parse finishing position from various formats"""
        if position is None:
            return None
        
        try:
            if isinstance(position, (int, float)):
                return int(position)
            elif isinstance(position, str):
                # Handle positions like "1", "2nd", "3rd", etc.
                if position.isdigit():
                    return int(position)
                # Remove non-numeric characters and try to parse
                clean_pos = ''.join(c for c in position if c.isdigit())
                if clean_pos:
                    return int(clean_pos)
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _parse_date(self, date_str: Any) -> Optional[datetime]:
        """Parse date from various formats"""
        if not date_str:
            return None
        
        try:
            if isinstance(date_str, datetime):
                return date_str
            elif isinstance(date_str, str):
                # Try common date formats
                for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y%m%d']:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except ValueError:
                        continue
        except (ValueError, TypeError):
            pass
        
        return None
    
    def _is_similar_distance(self, dist1: str, dist2: str) -> bool:
        """Check if two distances are similar"""
        if not dist1 or not dist2:
            return False
        
        # Simple implementation - expand with actual distance comparison logic
        try:
            # Extract numeric part of distance
            num1 = float(''.join(c for c in dist1 if c.isdigit() or c == '.'))
            num2 = float(''.join(c for c in dist2 if c.isdigit() or c == '.'))
            return abs(num1 - num2) <= 200  # Within 200m considered similar
        except (ValueError, TypeError):
            return dist1 == dist2


# Example usage (for testing)
if __name__ == "__main__":
    # Test the scoring service
    service = ScoringService(debug_callback=print)
    
    test_horse = {
        'id': 123,
        'horse_name': 'Test Horse',
        'horse_no': 5,
        'blinkers': False
    }
    
    test_runs = [
        {'run_date': '2024-01-15', 'position': 1, 'distance': '1200m', 'race_class': 'Class 5'},
        {'run_date': '2024-01-01', 'position': 3, 'distance': '1400m', 'race_class': 'Class 5'},
        {'run_date': '2023-12-20', 'position': 2, 'distance': '1200m', 'race_class': 'Class 4'},
    ]
    
    test_race = {
        'id': 456,
        'race_no': 3,
        'race_name': 'Test Race',
        'race_date': '2024-02-01',
        'race_distance': '1200m',
        'race_class': 'Class 5'
    }
    
    score_record, created = service.create_score_record(test_horse, test_runs, test_race)
    print(f"\n🎯 Final Score Record: {score_record}")


    import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any, List
from django.utils import timezone
from django.db.models import Q
from django.conf import settings

class RunAnalysisService:
    
    def __init__(self, debug_callback=None):
        self._debug_callback = debug_callback
        self.class_groups = self._load_class_groups()
        self._log_debug("🔧 RunAnalysisService initialized with Class Analysis")
    
    def _log_debug(self, message):
        """Internal debug logging method"""
        if self._debug_callback and callable(self._debug_callback):
            self._debug_callback(message)
        # Also log to console for visibility
        print(f"RUN ANALYSIS: {message}")
    
    def _load_class_groups(self):
        """Load class groups from JSON file with debug output"""
        try:
            groups_path = os.path.join(settings.BASE_DIR, 'racecard_02', 'data', 'class_weights.json')
            with open(groups_path, 'r') as f:
                data = json.load(f)
                self._log_debug(f"✅ Loaded class groups from JSON: {list(data['class_groups'].keys())}")
                return data['class_groups']
        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            self._log_debug(f"⚠️ Could not load class groups: {e}. Using default groups.")
            return self._get_default_groups()
    
    def _get_default_groups(self):
        """Default class groups if JSON file not found"""
        self._log_debug("📋 Using default class groups")
        return {
            "Group 1": {"min_merit": 100, "max_merit": 120, "weight": 20, "equivalent_names": ["Group 1", "G1", "Classic", "Grade 1"]},
            "Group 2": {"min_merit": 90, "max_merit": 99, "weight": 18, "equivalent_names": ["Group 2", "G2", "Stakes", "Grade 2"]},
            "Group 3": {"min_merit": 80, "max_merit": 89, "weight": 16, "equivalent_names": ["Group 3", "G3", "Listed", "Grade 3"]},
            "Premier": {"min_merit": 70, "max_merit": 79, "weight": 14, "equivalent_names": ["Premier", "MR70+", "Feature", "Premier Handicap"]},
            "Middle": {"min_merit": 60, "max_merit": 69, "weight": 12, "equivalent_names": ["Middle", "MR60+", "Mddle", "Middle Stakes", "MR64"]},
            "Moderate": {"min_merit": 50, "max_merit": 59, "weight": 10, "equivalent_names": ["Moderate", "MR50+", "MR55", "Handicap"]},
            "Standard": {"min_merit": 40, "max_merit": 49, "weight": 8, "equivalent_names": ["Standard", "MR40+", "MR45", "Class 4"]},
            "Basic": {"min_merit": 30, "max_merit": 39, "weight": 6, "equivalent_names": ["Basic", "MR30+", "MR35", "Class 5"]},
            "Maiden": {"min_merit": 0, "max_merit": 29, "weight": 4, "equivalent_names": ["Maiden", "MP", "OM", "Novice", "Class 6"]}
        }
    
    def find_class_group(self, race_class: Optional[str]) -> Tuple[Optional[str], int]:
        """Find which group a race class belongs to with debug info"""
        if not race_class:
            self._log_debug("🔍 Class analysis: No race class provided")
            return None, 0
        
        race_class_upper = race_class.upper().strip()
        self._log_debug(f"🔍 Analyzing race class: '{race_class}' -> '{race_class_upper}'")
        
        # First, try to extract merit rating
        merit_match = re.search(r'MR\s*(\d+)', race_class_upper)
        if merit_match:
            merit_value = int(merit_match.group(1))
            self._log_debug(f"📊 Found merit rating: MR{merit_value}")
            
            for group_name, group_data in self.class_groups.items():
                if group_data['min_merit'] <= merit_value <= group_data['max_merit']:
                    self._log_debug(f"✅ Matched MR{merit_value} to group: {group_name} (weight: {group_data['weight']})")
                    return group_name, group_data['weight']
            self._log_debug(f"❌ MR{merit_value} doesn't match any group range")
        
        # Then try to match by equivalent names
        for group_name, group_data in self.class_groups.items():
            for equivalent_name in group_data['equivalent_names']:
                if equivalent_name.upper() in race_class_upper:
                    self._log_debug(f"✅ Matched '{equivalent_name}' to group: {group_name} (weight: {group_data['weight']})")
                    return group_name, group_data['weight']
        
        # Default to Maiden if no match found
        self._log_debug(f"⚠️ No specific match found for '{race_class}', defaulting to Maiden")
        return "Maiden", self.class_groups["Maiden"]["weight"]
    
    def calculate_run_score(self, race_class: Optional[str], position: Optional[str]) -> Dict[str, Any]:
        """Calculate a score for a single run with debug info"""
        self._log_debug(f"🎯 Calculating run score for class: '{race_class}', position: {position}")
        
        group_name, class_weight = self.find_class_group(race_class)
        self._log_debug(f"📦 Class group: {group_name}, Weight: {class_weight}")
        
        # Convert position to performance score
        try:
            if position and str(position).isdigit():
                pos = float(position)
                # Better performance scoring: 1st=100, 2nd=80, 3rd=60, etc.
                if pos == 1:
                    performance_score = 100
                elif pos == 2:
                    performance_score = 80
                elif pos == 3:
                    performance_score = 60
                elif pos <= 5:
                    performance_score = 40
                elif pos <= 10:
                    performance_score = 20
                else:
                    performance_score = 10
            else:
                performance_score = 30  # Default for non-finishers or unknown positions
            self._log_debug(f"📈 Position {position} -> performance score: {performance_score}")
        except (ValueError, TypeError):
            performance_score = 30
            self._log_debug(f"⚠️ Could not parse position '{position}', using default: 30")
        
        # Combine class weight and performance (weighted average)
        run_score = (class_weight * 0.7) + (performance_score * 0.3)
        
        self._log_debug(f"🧮 Run score calculation:")
        self._log_debug(f"   Class component: {class_weight} × 0.7 = {class_weight * 0.7:.2f}")
        self._log_debug(f"   Performance component: {performance_score} × 0.3 = {performance_score * 0.3:.2f}")
        self._log_debug(f"   Final run score: {run_score:.2f}")
        
        return {
            'class_group': group_name,
            'class_weight': class_weight,
            'performance_score': performance_score,
            'run_score': round(run_score, 2),
            'position': position
        }
    
    def analyze_horse_runs(self, horse):
        """Comprehensive analysis of a horse's past runs including class analysis"""
        self._log_debug(f"\n📊 ===== ANALYZING RUNS FOR {getattr(horse, 'horse_name', 'Unknown')} =====")
        
        # Try to import Run model
        try:
            from racecard_02.models import Run
            runs = Run.objects.filter(horse=horse).order_by('-run_date')[:10]  # Last 10 runs
        except ImportError:
            self._log_debug("❌ Could not import Run model")
            return self._get_empty_analysis()
        except Exception as e:
            self._log_debug(f"❌ Error querying runs: {e}")
            return self._get_empty_analysis()
        
        if not runs:
            self._log_debug("ℹ️ No past runs found for this horse")
            return self._get_empty_analysis()
        
        self._log_debug(f"📅 Found {len(runs)} recent runs:")
        
        # Initialize analysis data structures
        positions = []
        margins = []
        distances = []
        class_weights = []
        days_since = []
        performance_scores = []
        run_analyses = []
        total_score = 0
        
        current_date = timezone.now().date()
        
        for i, run in enumerate(runs, 1):
            run_class = getattr(run, 'race_class', 'Unknown')
            position = getattr(run, 'position', None)
            self._log_debug(f"\n  🏇 Run {i}: {getattr(run, 'run_date', 'Unknown')} - {run_class} - Pos: {position}")
            
            # Run-level analysis (class + performance)
            run_analysis = self.calculate_run_score(run_class, position)
            run_analyses.append(run_analysis)
            total_score += run_analysis['run_score']
            self._log_debug(f"  → Final score: {run_analysis['run_score']:.2f}")
            
            # Position analysis
            pos = self._parse_position(position)
            if pos is not None:
                positions.append(pos)
                performance_scores.append(self._calculate_performance_score(pos))
            
            # Margin analysis
            margin = self._parse_margin(getattr(run, 'margin', None))
            if margin is not None:
                margins.append(margin)
            
            # Distance analysis
            distance = self._parse_distance(getattr(run, 'distance', None))
            if distance is not None:
                distances.append(distance)
            
            # Class weight (from class analysis)
            class_weights.append(run_analysis['class_weight'])
            
            # Days since run
            if hasattr(run, 'run_date') and run.run_date:
                try:
                    days = (current_date - run.run_date).days
                    days_since.append(days)
                except:
                    pass
        
        # Calculate overall metrics
        avg_score = total_score / len(runs) if runs else 0
        self._log_debug(f"\n📈 Average run score: {total_score:.2f} / {len(runs)} = {avg_score:.2f}")
        
        # Find best performance
        best_performance = None
        for analysis in run_analyses:
            if analysis['performance_score'] >= 60:  # Good performance (top 3)
                if not best_performance or analysis['class_weight'] > best_performance['class_weight']:
                    best_performance = analysis
        
        if best_performance:
            self._log_debug(f"⭐ Best performance: {best_performance['class_group']} (weight: {best_performance['class_weight']}), Score: {best_performance['run_score']:.2f}")
        else:
            self._log_debug(f"ℹ️ No standout best performance found")
        
        # Calculate form and class trends
        class_trend = self._get_class_trend(run_analyses)
        performance_trend = self._calculate_performance_trend(performance_scores)
        
        # Compile comprehensive analysis
        analysis_result = {
            # Run performance metrics
            'average_position': self._safe_average(positions),
            'average_margin': self._safe_average(margins),
            'recent_distance': self._most_common_value(distances),
            'days_since_last_run': min(days_since) if days_since else None,
            'form_rating': self._calculate_form_rating(positions),
            'consistency': self._calculate_consistency(positions),
            'performance_trend': performance_trend,
            
            # Class analysis metrics
            'average_class': self._safe_average(class_weights),
            'class_trend': class_trend,
            'run_analyses': run_analyses,
            'average_score': round(avg_score, 2),
            'best_performance': best_performance,
            'recent_class': run_analyses[0]['class_group'] if run_analyses else None,
            'recent_performance': run_analyses[0]['performance_score'] if run_analyses else 0,
            
            # Metadata
            'runs_analyzed': len(runs),
            'horse_id': getattr(horse, 'id', None)
        }
        
        self._log_debug(f"🏁 Comprehensive analysis completed")
        return analysis_result
    
    def calculate_class_suitability(self, horse, race) -> float:
        """Calculate class suitability score with proper error handling"""
        try:
            # Input validation
            if not hasattr(horse, 'horse_name'):
                error_msg = f"Invalid horse object: {horse}"
                self._log_debug(f"❌ {error_msg}")
                return 50.0
            
            if not hasattr(race, 'race_class'):
                error_msg = f"Invalid race object: {race}"
                self._log_debug(f"❌ {error_msg}")
                return 50.0
            
            # Get current race class and weight
            race_class = getattr(race, 'race_class', '')
            current_group, current_weight = self.find_class_group(race_class)
            
            # Analyze horse's class history
            class_history = self.analyze_horse_class_history(horse)
            
            if class_history['runs_analyzed'] == 0:
                self._log_debug("📊 No class history found, using base suitability based on current race class")
                # Base suitability on current race class weight
                suitability = current_weight * 2.5  # Convert weight (4-20) to score (10-50)
                self._log_debug(f"📊 Base suitability from current class: {suitability:.2f}")
                return min(100, max(0, suitability))
            
            # Base suitability based on average performance
            suitability = class_history['average_score']
            self._log_debug(f"📊 Base suitability (average score): {suitability:.2f}")
            
            # Adjust based on current race class
            suitability = suitability * 0.7 + (current_weight * 2.5 * 0.3)
            self._log_debug(f"📊 Adjusted for current class: {suitability:.2f}")
            
            # Bonus if horse has proven ability at this level or higher
            if class_history['best_performance']:
                best_weight = class_history['best_performance']['class_weight']
                self._log_debug(f"📊 Best performance weight: {best_weight}, Current race weight: {current_weight}")
                
                if best_weight >= current_weight:
                    old_suitability = suitability
                    suitability = min(100, suitability * 1.2)  # 20% bonus
                    self._log_debug(f"🎯 Bonus: Proven ability at this level or higher (+20%)")
                    self._log_debug(f"   {old_suitability:.2f} → {suitability:.2f}")
                else:
                    # Small penalty for moving up significantly
                    if current_weight > best_weight + 4:
                        old_suitability = suitability
                        suitability *= 0.9  # 10% penalty
                        self._log_debug(f"⚠️ Penalty: Moving up significantly in class (-10%)")
                        self._log_debug(f"   {old_suitability:.2f} → {suitability:.2f}")
            
            final_score = min(100, max(0, suitability))
            self._log_debug(f"🏁 Final class suitability score: {final_score:.2f}")
            
            return float(final_score)
            
        except Exception as e:
            error_msg = f"Error in class suitability calculation for {getattr(horse, 'horse_name', 'unknown')}: {e}"
            self._log_debug(f"❌ {error_msg}")
            return 50.0  # Fallback score

    def calculate_form_score(self, horse) -> float:
        """Calculate form score based on recent class performance"""
        try:
            class_history = self.analyze_horse_class_history(horse)
            
            if class_history['runs_analyzed'] == 0:
                self._log_debug("No class history for form calculation")
                return 50.0
            
            # Use recent performance as form indicator
            if class_history['recent_performance'] > 0:
                form_score = class_history['recent_performance']  # Recent performance score
                self._log_debug(f"Form score from recent performance: {form_score:.2f}")
            else:
                form_score = class_history['average_score']  # Fallback to average
                self._log_debug(f"Form score from average: {form_score:.2f}")
            
            # Apply trend adjustment
            trend = self.get_class_trend(horse)
            if trend == "improving":
                form_score = min(100, form_score * 1.1)
                self._log_debug(f"📈 Form improving bonus: +10%")
            elif trend == "declining":
                form_score = max(0, form_score * 0.9)
                self._log_debug(f"📉 Form declining penalty: -10%")
            
            return float(form_score)
            
        except Exception as e:
            self._log_debug(f"Error calculating form score: {e}")
            return 50.0

    def analyze_horse_class_history(self, horse) -> Dict[str, Any]:
        """Analyze a horse's class history with detailed debug"""
        self._log_debug(f"\n📊 ===== ANALYZING CLASS HISTORY FOR {getattr(horse, 'horse_name', 'Unknown')} =====")
        
        # Get runs for the horse
        runs = self._get_horse_runs(horse)
        
        if not runs:
            self._log_debug("ℹ️ No past runs found for this horse")
            return self._get_empty_class_analysis()
        
        self._log_debug(f"📅 Found {len(runs)} recent runs:")
        
        run_analyses = []
        total_score = 0
        
        for i, run in enumerate(runs, 1):
            run_class = getattr(run, 'race_class', 'Unknown')
            position = getattr(run, 'position', None)
            self._log_debug(f"\n  🏇 Run {i}: {getattr(run, 'run_date', 'Unknown')} - {run_class} - Pos: {position}")
            
            analysis = self.calculate_run_score(run_class, position)
            run_analyses.append(analysis)
            total_score += analysis['run_score']
            self._log_debug(f"  → Final score: {analysis['run_score']:.2f}")
        
        avg_score = total_score / len(runs) if runs else 0
        self._log_debug(f"\n📈 Average run score: {total_score:.2f} / {len(runs)} = {avg_score:.2f}")
        
        # Find best performance
        best_performance = None
        for analysis in run_analyses:
            if analysis['performance_score'] >= 60:  # Good performance (top 3)
                if not best_performance or analysis['class_weight'] > best_performance['class_weight']:
                    best_performance = analysis
        
        if best_performance:
            self._log_debug(f"⭐ Best performance: {best_performance['class_group']} (weight: {best_performance['class_weight']}), Score: {best_performance['run_score']:.2f}")
        else:
            self._log_debug(f"ℹ️ No standout best performance found")
        
        return {
            'run_analyses': run_analyses,
            'average_score': round(avg_score, 2),
            'best_performance': best_performance,
            'runs_analyzed': len(runs),
            'recent_class': run_analyses[0]['class_group'] if run_analyses else None,
            'recent_performance': run_analyses[0]['performance_score'] if run_analyses else 0
        }
    
    def get_class_trend(self, horse) -> str:
        """Analyze if horse is moving up or down in class"""
        self._log_debug(f"\n📈 Analyzing class trend for {getattr(horse, 'horse_name', 'Unknown')}")
        class_history = self.analyze_horse_class_history(horse)
        
        if class_history['runs_analyzed'] < 2:
            self._log_debug("ℹ️ Not enough runs to determine trend, returning 'stable'")
            return "stable"
        
        return self._get_class_trend(class_history['run_analyses'])
    
    def _get_class_trend(self, run_analyses):
        """Internal method to calculate class trend from run analyses"""
        if len(run_analyses) < 2:
            return "stable"
        
        # Get average class weight of last 2 runs vs previous runs
        recent_runs = run_analyses[:2]
        previous_runs = run_analyses[2:]
        
        if not previous_runs:
            self._log_debug("ℹ️ Not enough previous runs for comparison")
            return "stable"
        
        recent_avg = sum(run['class_weight'] for run in recent_runs) / len(recent_runs)
        previous_avg = sum(run['class_weight'] for run in previous_runs) / len(previous_runs)
        
        self._log_debug(f"📊 Recent avg class weight: {recent_avg:.2f}, Previous avg: {previous_avg:.2f}")
        
        if recent_avg > previous_avg + 2:
            self._log_debug("📈 Trend: Moving up in class")
            return "improving"
        elif recent_avg < previous_avg - 2:
            self._log_debug("📉 Trend: Moving down in class")
            return "declining"
        else:
            self._log_debug("➡️ Trend: Stable class level")
            return "stable"
    
    def get_class_weight(self, race_class: Optional[str]) -> int:
        """Get the weight for a given race class"""
        self._log_debug(f"⚖️ Getting class weight for: '{race_class}'")
        _, weight = self.find_class_group(race_class)
        self._log_debug(f"⚖️ Weight: {weight}")
        return weight
    
    def _get_horse_runs(self, horse):
        """Get runs for the horse"""
        from racecard_02.models import Run, Horse
        
        try:
            if hasattr(horse, 'id') and horse.id:
                return Run.objects.filter(horse=horse).order_by('-run_date')[:6]  # Last 6 runs for class analysis
            else:
                horse_name = getattr(horse, 'horse_name', str(horse))
                horse_obj = Horse.objects.filter(horse_name=horse_name).first()
                if horse_obj:
                    return Run.objects.filter(horse=horse_obj).order_by('-run_date')[:6]
                return []
        except Exception as e:
            self._log_debug(f"DEBUG: Error getting runs: {e}")
            return []
    
    # Helper methods from the original RunAnalysisService
    def _parse_position(self, position):
        """Parse position value"""
        if position is None:
            return None
        
        try:
            if isinstance(position, str):
                # Handle DNF, DNS, etc.
                if position.upper() in ['DNF', 'DNS', 'WD', 'SCR']:
                    return 20  # Penalty for non-finishers
                elif position.isdigit():
                    return float(position)
            elif isinstance(position, (int, float)):
                return float(position)
        except:
            pass
        return None
    
    def _parse_distance(self, distance):
        """Parse distance value"""
        if not distance:
            return None
        
        try:
            distance_str = str(distance)
            # Extract numeric distance (e.g., "1200m" -> 1200)
            match = re.search(r'\d+', distance_str)
            if match:
                return int(match.group())
        except:
            pass
        return None
    
    def _calculate_performance_score(self, position):
        """Calculate performance score (1st=100, 2nd=80, etc.)"""
        if position is None:
            return 50
        
        try:
            # Better scoring: 1st=100, 2nd=85, 3rd=70, etc.
            if position <= 1:
                return 100
            elif position <= 3:
                return 100 - (position * 15)
            else:
                return max(10, 70 - (position * 5))
        except:
            return 50
    
    def _parse_margin(self, margin_text):
        """Parse margin text into numeric value"""
        if not margin_text:
            return None
            
        try:
            margin_text = str(margin_text).strip().upper()
            
            # Common margin abbreviations
            margin_map = {
                'DH': 0.0, 'DEAD HEAT': 0.0,
                'NSE': 0.05, 'NOSE': 0.05,
                'SH': 0.1, 'SHORT HEAD': 0.1,
                'HD': 0.2, 'HEAD': 0.2,
                'NK': 0.3, 'NECK': 0.3,
                'DIST': 10.0, 'DISTANCE': 10.0
            }
            
            if margin_text in margin_map:
                return margin_map[margin_text]
            
            # Try to parse numeric margin
            margin_text = re.sub(r'[^\d.]', '', margin_text)
            if margin_text:
                return float(margin_text)
                
        except:
            pass
        return None
    
    def _calculate_form_rating(self, positions):
        """Calculate form rating with better weighting"""
        if not positions:
            return 0
        
        try:
            # Weight recent runs more heavily
            weighted_sum = 0
            total_weight = 0
            
            for i, pos in enumerate(positions):
                weight = 0.9 ** i  # More emphasis on recent runs
                weighted_sum += pos * weight
                total_weight += weight
            
            return round(weighted_sum / total_weight, 2)
        except:
            return round(sum(positions) / len(positions), 2) if positions else 0
    
    def _calculate_consistency(self, positions):
        """Calculate consistency percentage"""
        if not positions or len(positions) < 2:
            return 0
        
        try:
            avg_position = sum(positions) / len(positions)
            # Count runs within 2 positions of average
            within_range = sum(1 for p in positions if abs(p - avg_position) <= 2)
            
            return round((within_range / len(positions)) * 100, 1)
        except:
            return 0
    
    def _calculate_performance_trend(self, performance_scores):
        """Calculate performance trend"""
        if not performance_scores or len(performance_scores) < 3:
            return "stable"
        
        try:
            # Use weighted average of last 3 runs vs previous 3
            recent_avg = sum(performance_scores[:3]) / min(3, len(performance_scores))
            previous_avg = sum(performance_scores[3:6]) / min(3, len(performance_scores[3:6])) if len(performance_scores) > 3 else recent_avg
            
            if recent_avg > previous_avg + 20:
                return "improving_strong"
            elif recent_avg > previous_avg + 10:
                return "improving"
            elif recent_avg < previous_avg - 20:
                return "declining_strong"
            elif recent_avg < previous_avg - 10:
                return "declining"
            else:
                return "stable"
        except:
            return "stable"
    
    def _safe_average(self, values):
        """Calculate average safely"""
        valid_values = [v for v in values if v is not None]
        return round(sum(valid_values) / len(valid_values), 2) if valid_values else None
    
    def _most_common_value(self, values):
        """Get most common value"""
        valid_values = [v for v in values if v is not None]
        if not valid_values:
            return None
        return max(set(valid_values), key=valid_values.count)
    
    def _get_empty_analysis(self):
        return {
            'average_position': None,
            'average_margin': None,
            'recent_distance': None,
            'days_since_last_run': None,
            'form_rating': 0,
            'consistency': 0,
            'performance_trend': "stable",
            'average_class': None,
            'class_trend': "stable",
            'run_analyses': [],
            'average_score': 0,
            'best_performance': None,
            'recent_class': None,
            'recent_performance': 0,
            'runs_analyzed': 0,
            'horse_id': None
        }
    
    def _get_empty_class_analysis(self):
        return {
            'run_analyses': [],
            'average_score': 0,
            'best_performance': None,
            'runs_analyzed': 0,
            'recent_class': None,
            'recent_performance': 0
        }::


those are the working files of courses there are also some data file json:
Server busy, please try again later.

