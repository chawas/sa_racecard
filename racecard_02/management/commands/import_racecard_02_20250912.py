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
            self.stdout.write(f"    ❌ Error importing runs: {e}")