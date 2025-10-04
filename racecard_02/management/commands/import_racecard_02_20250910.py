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

from racecard_02.models import Race, Horse, HorseScore, Ranking
from racecard_02.services.scoring_service import HorseScoringService


# Add this to the top of your command file
import django.db.models.sql.query

# Store the original method
_original_check_query_object_type = django.db.models.sql.query.Query.check_query_object_type

def debug_check_query_object_type(self, value, opts, field):
    """Debug version to track down bad queries"""
    if isinstance(value, str) and field.is_relation:
        # This is where the error occurs - a string is passed to a relation field
        print(f"🔴 BAD QUERY DETECTED:")
        print(f"   Field: {field.name}")
        print(f"   Model: {opts.model.__name__}")
        print(f"   Value: '{value}'")
        print(f"   Expected: {field.related_model.__name__} instance")
        
        # Get the stack trace to see where this query originated
        import traceback
        stack = traceback.extract_stack()
        for frame in stack[-6:]:  # Show last 6 frames
            if 'django' not in frame.filename:  # Filter out Django internals
                print(f"   Called from: {frame.filename}:{frame.lineno} in {frame.name}")
        
        print("   Stack trace:")
        traceback.print_stack(limit=8)
        
    return _original_check_query_object_type(self, value, opts, field)

# Monkey patch for debugging
django.db.models.sql.query.Query.check_query_object_type = debug_check_query_object_type

class Command(BaseCommand):
    help = 'Import racecard data from HTML files'
    
    def __init__(self, horse, race, debug_callback=None):
        self.horse = horse
        self.race = race
        self.debug_callback = debug_callback
    
        # Call the parent constructor
        super().__init__(*args, **kwargs)

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
        """
        Parse horse blocks. We only consider tables that:
        - have border="border"
        - contain a <div class="b4"> with a numeric horse number
        """
        self.stdout.write(f"\n🔍 Extracting Horses for Race {race.race_no}...")
        created_or_updated = 0
        horse_tables = soup.select('table[border="border"]')
        self.stdout.write(f"Found {len(horse_tables)} horse tables")
        
        # Debug: show all tables first
        self._debug_tables(soup)
        
        # FIRST: Find and parse the jockey-trainer stats table
        jt_analysis_data = self._parse_jockey_trainer_table(soup)
        
        # FIX: Handle both list and dictionary cases
        self.stdout.write(f"J-T analysis data type: {type(jt_analysis_data)}")
        
        if isinstance(jt_analysis_data, dict):
            self.stdout.write(f"J-T analysis data keys: {list(jt_analysis_data.keys())}")
            # It's already a dictionary, use it as is
            jt_analysis_dict = jt_analysis_data
        elif isinstance(jt_analysis_data, list):
            self.stdout.write(f"J-T analysis data length: {len(jt_analysis_data)}")
            # Convert list to dictionary keyed by horse number
            jt_analysis_dict = {}
            for i, jt_item in enumerate(jt_analysis_data):
                if isinstance(jt_item, dict):
                    # Try to extract horse number from the item or use index
                    horse_no = jt_item.get('horse_no', i + 1)
                    jt_analysis_dict[horse_no] = jt_item
        else:
            self.stdout.write(f"⚠️ Unexpected J-T data type: {type(jt_analysis_data)}")
            jt_analysis_dict = {}
        
        # Store in class cache for later use in score calculation
        self.jt_analysis_cache = jt_analysis_dict
        self.stdout.write(f"✅ Stored J-T data in class cache: {len(self.jt_analysis_cache)} horses")
        
        # Rest of your code remains the same...
        # NEW: Find the PREDICTED FINISH table specifically
        speed_index_data = {}
        
        # Look for the specific table structure with PREDICTED FINISH header
        all_tables = soup.find_all('table')
        for table in all_tables:
            # Check if this table has the PREDICTED FINISH header with class 'bld'
            predicted_finish_header = table.find('td', class_='bld')
            if predicted_finish_header and 'PREDICTED FINISH' in predicted_finish_header.get_text():
                self.stdout.write("✅ Found PREDICTED FINISH table")
                
                # Find all rows in this table (skip the header rows)
                rows = table.find_all('tr')
                for i, row in enumerate(rows):
                    # Skip the first two header rows
                    if i < 2:
                        continue
                        
                    cells = row.find_all('td')
                    if len(cells) >= 4:  # Should have at least No, Horse, Len/Beh, Speed Index
                        try:
                            # First cell should contain horse number
                            horse_no_text = cells[0].get_text(strip=True)
                            if not horse_no_text.isdigit():
                                continue
                            horse_no = int(horse_no_text)
                            
                            # Speed index is typically in the 4th cell (index 3) and is enclosed in []
                            speed_text = cells[3].get_text(strip=True)
                            
                            # Extract number from square brackets [81] -> 81
                            bracket_match = re.search(r'\[(\d+)\]', speed_text)
                            if bracket_match:
                                speed_index = int(bracket_match.group(1))
                                speed_index_data[horse_no] = speed_index
                                self.stdout.write(f"✅ Extracted speed index for horse {horse_no}: {speed_index}")
                            else:
                                # Try to find any numeric value in the cell
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
                # --- DEBUG: Analyze table structure ---
                self.stdout.write(f"\n🔍 Analyzing horse table {idx}...")
                
                first_tr = table.find("tr")
                if not first_tr:
                    self.stdout.write(f"Skipping table {idx}: No rows found")
                    continue
                    
                main_tds = first_tr.find_all("td", recursive=False)
                if len(main_tds) < 2:
                    self.stdout.write(f"Skipping table {idx}: Not enough main TDs ({len(main_tds)})")
                    continue

                # --- TD 0: number/odds/rating ---
                td0 = main_tds[0]
                num_div = td0.find("div", class_="b4")
                if not num_div:
                    # Not a horse row
                    self.stdout.write(f"Skipping table {idx}: No b4 div found")
                    continue
                    
                try:
                    horse_no = int(self._text(num_div))
                    self.stdout.write(f"Processing horse {horse_no}...")
                except Exception as e:
                    self.stdout.write(f"Skipping table {idx}: Could not parse horse number: {e}")
                    continue

                # --- EXTRACT SPEED INDEX ---
                speed_index = None
                
                # First check if we already extracted this from the predicted finish table
                if horse_no in speed_index_data:
                    speed_index = speed_index_data[horse_no]
                    self.stdout.write(f"✅ Using speed index from predicted finish table: {speed_index}")
                else:
                    # If not found in the dedicated table, try other methods
                    self.stdout.write(f"❌ Speed index not found in predicted finish table for horse {horse_no}")
                    
                    # Look for speed index in this specific table (check for bracket format)
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
                    
                    # Default if no speed index found
                    if speed_index is None:
                        speed_index = 50  # Default neutral
                        self.stdout.write(f"ℹ️ Using default speed index for horse {horse_no}: 50")
                    else:
                        # Ensure speed index is within reasonable bounds
                        speed_index = max(0, min(100, speed_index))

                # --- Continue with rest of parsing ---
                odds_el = td0.find("div", class_="b1")
                odds = self._text(odds_el)

                merit_el = td0.find("span", class_="b1")
                horse_merit = None
                if merit_el:
                    m = re.search(r"\d+", merit_el.get_text())
                    if m:
                        horse_merit = int(m.group())

                # --- TD 1: name + age/blinkers ---
                td1 = main_tds[1] if len(main_tds) > 1 else None
                horse_name = ""
                blinkers = False
                age = ""

                if td1:
                    name_cell = td1.find("td", class_="b1")
                    horse_name = self._text(name_cell) or self._text(td1)
                    # Blinkers if "(B)" appears anywhere in the name block
                    block_text_upper = td1.get_text(" ", strip=True).upper()
                    blinkers = "(B" in block_text_upper

                    # Age e.g. "6 y. o. b g."
                    age_text = ""
                    for s in td1.stripped_strings:
                        if re.search(r"\by\.?\s*o\.?", s, flags=re.I):
                            age_text = s
                            break
                    m_age = re.search(r"\b(\d{1,2})\b", age_text)
                    age = m_age.group(1) if m_age else ""

                # --- Extract Best MR from comment section ---
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

                # --- Jockey / Trainer (nested table) ---
                itbld_divs = table.select("div.itbld")
                jockey, trainer = "", ""
                if len(itbld_divs) >= 1:
                    jockey = " ".join(itbld_divs[0].stripped_strings)
                if len(itbld_divs) >= 2:
                    trainer = " ".join(itbld_divs[1].stripped_strings)

                # --- Jockey-Trainer Analysis ---
                jt_score = 50  # Default neutral score
                jt_rating = "Average"
                
                # Use the pre-parsed jockey-trainer data if available
                if horse_no in self.jt_analysis_cache:
                    jt_data = self.jt_analysis_cache[horse_no]
                    jt_score = jt_data.get('score', 50)
                    jt_rating = jt_data.get('rating', 'Average')
                    # Use the jockey/trainer from analysis if available (more accurate)
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
                
                # Verify the save worked
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
        """Debug method to analyze horse tables"""
        self.stdout.write("\n" + "="*50)
        self.stdout.write("🔍 DEBUG: HORSE TABLE ANALYSIS")
        
        for idx, table in enumerate(horse_tables[:3]):
            self.stdout.write(f"\nTable {idx+1}:")
            
            b4_divs = table.find_all('div', class_='b4')
            self.stdout.write(f"b4 divs found: {len(b4_divs)}")
            
            b1_divs = table.find_all('div', class_='b1')
            self.stdout.write(f"b1 divs found: {len(b1_divs)}")
            
            numbers = re.findall(r'\b\d+\b', table.get_text())
            self.stdout.write(f"Numbers found: {numbers}")
        
        self.stdout.write("="*50 + "\n")



    def _debug_tables(self, soup):
        """Debug function to see all tables in the HTML"""
        tables = soup.find_all('table')
        self.stdout.write(f"\n🔍 Found {len(tables)} tables in the HTML:")
        
        for i, table in enumerate(tables):
            self.stdout.write(f"\nTable {i+1}:")
            # Get table classes
            classes = table.get('class', [])
            self.stdout.write(f"   Classes: {classes}")
            
            # Get header text
            headers = table.find_all('th')
            if headers:
                self.stdout.write(f"   Headers: {[h.get_text(strip=True) for h in headers]}")
            
            # Show first row of data
            first_row = table.find('tr')
            if first_row:
                cells = first_row.find_all(['td', 'th'])
                self.stdout.write(f"   First row: {[c.get_text(strip=True)[:30] for c in cells]}")
        



    # Add this helper function to your command file
    def debug_horse_lookup(horse_reference, race):
        """Debug function to help identify horse lookup issues"""
        print(f"🔍 Debugging horse reference: {horse_reference} (type: {type(horse_reference)})")
        
        if isinstance(horse_reference, str):
            print(f"   String detected: '{horse_reference}'")
            print(f"   Looking up in race: {race.race_no}")
            
            # Try to find the horse
            try:
                horse = Horse.objects.get(horse_name=horse_reference, race=race)
                print(f"   ✅ Found horse: {horse.horse_name} (ID: {horse.id})")
                return horse
            except Horse.DoesNotExist:
                print(f"   ❌ Horse '{horse_reference}' not found in race {race.race_no}")
            except Horse.MultipleObjectsReturned:
                horse = Horse.objects.filter(horse_name=horse_reference, race=race).first()
                print(f"   ⚠️ Multiple horses found, using first: {horse.horse_name} (ID: {horse.id})")
                return horse
            except Exception as e:
                print(f"   ❌ Error looking up horse: {e}")
        
        elif isinstance(horse_reference, Horse):
            print(f"   ✅ Horse object: {horse_reference.horse_name} (ID: {horse_reference.id})")
            return horse_reference
        else:
            print(f"   ❓ Unknown type: {type(horse_reference)}")
        
        return None



        
    def _calculate_horse_scores(self, race):
        """Calculate scores for all horses in a race and create rankings"""
        self.stdout.write(f"\n📊 Calculating scores for Race {race.race_no}...")
        created = False  # Initialize the variable
        horses = Horse.objects.filter(race=race)
        self.stdout.write(f"Found {horses.count()} horses in database for this race")
        
        scores_data = []
        all_scores = []  # Track all scores to check for differences
        
        for horse in horses:
            try:
                self.stdout.write(f"\n    🐎 Processing {horse.horse_name} (No. {horse.horse_no})...")


                # DEBUG: Verify we have a Horse object
                if not isinstance(horse, Horse):
                    self.stdout.write(f"❌ ERROR: Expected Horse object, got {type(horse)}: {horse}")
                    continue
                
                # DEBUG: Check horse attributes
                self.stdout.write(f"      Horse ID: {horse.id}, Name: '{horse.horse_name}'")
                
                scoring_service = BaseCommand(horse, race, debug_callback=self.stdout.write)
                score_record, created = scoring_service.create_score_record()
                
                # Or use the factory function if you need lookup capability
                # scoring_service = create_scoring_service(horse, race, debug_callback=self.stdout.write)
                
            except Exception as e:
                self.stdout.write(f"❌ Error creating scoring service: {e}")
                
                status = "Created" if created else "Updated"
                self.stdout.write(f"    ✅ {status} score for {horse.horse_name}: {score_record.overall_score}")
                
                all_scores.append(score_record.overall_score)
                scores_data.append({
                    'horse': horse,
                    'score_record': score_record,
                    'overall_score': score_record.overall_score
                })
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    ❌ Error scoring {getattr(horse, 'horse_name', 'unknown')}: {e}"))
                import traceback
                self.stdout.write(traceback.format_exc())
        


                
                # DEBUG: Show what data we have for scoring
                self.stdout.write(f"      Speed: {getattr(horse, 'speed_rating', 'N/A')}, "
                                f"Merit: {getattr(horse, 'horse_merit', 'N/A')}, "
                                f"Best MR: {getattr(horse, 'best_merit_rating', 'N/A')}, "
                                f"JT: {getattr(horse, 'jt_score', 'N/A')}")
                
                # Pass the horse object directly, not the name
                scoring_service = HorseScoringService(horse, race, debug_callback=self.stdout.write)
                score_record, created = scoring_service.create_score_record()


                


                        # DEBUG: Get detailed breakdown of scores with exception handling
                self.stdout.write(f"      🔍 Calculating detailed score breakdown...")
                
                # Calculate individual components with detailed debug
                try:
                    form_score = scoring_service._calculate_form_score()
                    self.stdout.write(f"      📊 Form score calculated: {form_score}")
                except Exception as e:
                    form_score = 50
                    self.stdout.write(f"      ⚠️ Form score error: {e}, using default: 50")
                
                try:
                    class_score = scoring_service._calculate_class_score()
                    self.stdout.write(f"      📊 Class score calculated: {class_score}")
                except Exception as e:
                    class_score = 50
                    self.stdout.write(f"      ⚠️ Class score error: {e}, using default: 50")
                
                try:
                    jockey_score = scoring_service._calculate_jockey_score()
                    self.stdout.write(f"      📊 Jockey score calculated: {jockey_score}")
                except Exception as e:
                    jockey_score = 50
                    self.stdout.write(f"      ⚠️ Jockey score error: {e}, using default: 50")
                
                try:
                    trainer_score = scoring_service._calculate_trainer_score()
                    self.stdout.write(f"      📊 Trainer score calculated: {trainer_score}")
                except Exception as e:
                    trainer_score = 50
                    self.stdout.write(f"      ⚠️ Trainer score error: {e}, using default: 50")
                
                try:
                    speed_score = scoring_service._calculate_speed_score()
                    self.stdout.write(f"      📊 Speed score calculated: {speed_score}")
                except Exception as e:
                    speed_score = 50
                    self.stdout.write(f"      ⚠️ Speed score error: {e}, using default: 50")
                
                # Show weight distribution
                weights = {
                    'form': 0.3,      # 30% weight to form
                    'class': 0.25,    # 25% weight to class suitability
                    'jockey': 0.15,   # 15% weight to jockey
                    'trainer': 0.15,  # 15% weight to trainer
                    'speed': 0.15     # 15% weight to speed
                }
                
                self.stdout.write(f"      ⚖️  Weight distribution:")
                self.stdout.write(f"        Form: {weights['form'] * 100}%")
                self.stdout.write(f"        Class: {weights['class'] * 100}%")
                self.stdout.write(f"        Jockey: {weights['jockey'] * 100}%")
                self.stdout.write(f"        Trainer: {weights['trainer'] * 100}%")
                self.stdout.write(f"        Speed: {weights['speed'] * 100}%")
                
                # Calculate weighted components
                weighted_form = form_score * weights['form']
                weighted_class = class_score * weights['class']
                weighted_jockey = jockey_score * weights['jockey']
                weighted_trainer = trainer_score * weights['trainer']
                weighted_speed = speed_score * weights['speed']
                
                self.stdout.write(f"      🧮 Weighted components:")
                self.stdout.write(f"        Form: {form_score} × {weights['form']} = {weighted_form:.2f}")
                self.stdout.write(f"        Class: {class_score} × {weights['class']} = {weighted_class:.2f}")
                self.stdout.write(f"        Jockey: {jockey_score} × {weights['jockey']} = {weighted_jockey:.2f}")
                self.stdout.write(f"        Trainer: {trainer_score} × {weights['trainer']} = {weighted_trainer:.2f}")
                self.stdout.write(f"        Speed: {speed_score} × {weights['speed']} = {weighted_speed:.2f}")
                
                # Calculate overall score manually to verify
                manual_score = weighted_form + weighted_class + weighted_jockey + weighted_trainer + weighted_speed
                self.stdout.write(f"      🧾 Manual calculation: {manual_score:.2f}")
                
                # Create the score record using the service (this might use different logic)
                score_record, created = scoring_service.create_score_record()
                
                status = "Created" if created else "Updated"
                self.stdout.write(f"    ✅ {status} score for {horse.horse_name}: {score_record.overall_score}")
                
                # Compare manual vs service calculation
                if abs(manual_score - score_record.overall_score) > 0.1:
                    self.stdout.write(f"      ⚠️  DISCREPANCY: Manual calc ({manual_score:.2f}) vs Service calc ({score_record.overall_score:.2f})")
                
                all_scores.append(score_record.overall_score)
                scores_data.append({
                    'horse': horse,
                    'score_record': score_record,
                    'overall_score': score_record.overall_score,
                    'form_score': form_score,
                    'class_score': class_score,
                    'jockey_score': jockey_score,
                    'trainer_score': trainer_score,
                    'speed_score': speed_score
                })
                
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"    ❌ Error scoring {horse.horse_name}: {e}"))
                import traceback
                self.stdout.write(traceback.format_exc())
        
        # Check if scores are different with more detailed analysis
        if all_scores:
            unique_scores = set(all_scores)
            self.stdout.write(f"\n📈 Score analysis: {len(unique_scores)} unique scores out of {len(all_scores)} horses")
            self.stdout.write(f"📊 Score range: {min(all_scores)} to {max(all_scores)}")
            
            # Show component analysis to understand why scores might be similar
            self.stdout.write(f"\n🔍 Component score analysis:")
            form_scores = [data['form_score'] for data in scores_data]
            class_scores = [data['class_score'] for data in scores_data]
            jockey_scores = [data['jockey_score'] for data in scores_data]
            trainer_scores = [data['trainer_score'] for data in scores_data]
            speed_scores = [data['speed_score'] for data in scores_data]
            
            self.stdout.write(f"   Form scores: {min(form_scores)}-{max(form_scores)} (unique: {len(set(form_scores))})")
            self.stdout.write(f"   Class scores: {min(class_scores)}-{max(class_scores)} (unique: {len(set(class_scores))})")
            self.stdout.write(f"   Jockey scores: {min(jockey_scores)}-{max(jockey_scores)} (unique: {len(set(jockey_scores))})")
            self.stdout.write(f"   Trainer scores: {min(trainer_scores)}-{max(trainer_scores)} (unique: {len(set(trainer_scores))})")
            self.stdout.write(f"   Speed scores: {min(speed_scores)}-{max(speed_scores)} (unique: {len(set(speed_scores))})")
            
            # Check if form and class scores are all 50 (default)
            if all(score == 50 for score in form_scores):
                self.stdout.write(self.style.WARNING("⚠️  ALL FORM SCORES ARE DEFAULT 50!"))
                self.stdout.write(self.style.WARNING("   Check _calculate_form_score() method for errors"))
            
            if all(score == 50 for score in class_scores):
                self.stdout.write(self.style.WARNING("⚠️  ALL CLASS SCORES ARE DEFAULT 50!"))
                self.stdout.write(self.style.WARNING("   Check _calculate_class_score() method for errors"))
            
            if len(unique_scores) <= 1:
                self.stdout.write(self.style.WARNING("⚠️  WARNING: All horses have the same or very similar scores!"))
                
                # Debug specific cases where scores are identical
                if len(unique_scores) == 1:
                    identical_score = list(unique_scores)[0]
                    self.stdout.write(f"   All horses have score: {identical_score}")
                    
                    # Show what components are causing this
                    if len(set(form_scores)) == 1:
                        self.stdout.write(f"   → All form scores are identical: {form_scores[0]}")
                    if len(set(class_scores)) == 1:
                        self.stdout.write(f"   → All class scores are identical: {class_scores[0]}")
                    if len(set(jockey_scores)) == 1:
                        self.stdout.write(f"   → All jockey scores are identical: {jockey_scores[0]}")
                    if len(set(trainer_scores)) == 1:
                        self.stdout.write(f"   → All trainer scores are identical: {trainer_scores[0]}")
                    if len(set(speed_scores)) == 1:
                        self.stdout.write(f"   → All speed scores are identical: {speed_scores[0]}")
            else:
                self.stdout.write("✅ Good score variation for ranking")
        else:
            self.stdout.write("❌ No scores calculated")
            return
        
        # Display rankings on screen with component breakdown
        if scores_data:
            self.stdout.write(f"\n🏆 DETAILED RANKINGS for Race {race.race_no}:")
            sorted_rankings = sorted(scores_data, key=lambda x: x['overall_score'], reverse=True)
            
            for position, data in enumerate(sorted_rankings, 1):
                horse = data['horse']
                score = data['overall_score']
                self.stdout.write(f"\n#{position}: {horse.horse_name} (Score: {score:.2f})")
                self.stdout.write(f"   Form: {data['form_score']:.2f}, "
                                f"Class: {data['class_score']:.2f}, "
                                f"Jockey: {data['jockey_score']:.2f}, "
                                f"Trainer: {data['trainer_score']:.2f}, "
                                f"Speed: {data['speed_score']:.2f}")
            
            rankings_saved = self._display_detailed_rankings(scores_data, race)
            self.stdout.write(f"\n✅ Successfully displayed and saved {rankings_saved} rankings")
        else:
            self.stdout.write("❌ No scores calculated for ranking display")
        
        return len(scores_data)
    


    def _parse_jockey_trainer_table(self, soup):
        """Find and parse jockey-trainer statistics table"""
        jt_analysis_data = {}
        
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
                        except (ValueError, KeyError):
                            continue
                
                if jt_analysis_data:
                    break
        
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
                
            except Exception:
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





    def _parse_predicted_finish_table(self, soup):
        """Parse the predicted finish table for speed indexes"""
        speed_data = {}
        
        predicted_finish_headers = soup.find_all(['td', 'th'], 
            string=lambda text: text and 'PREDICTED FINISH' in text.upper())
        
        if not predicted_finish_headers:
            return speed_data
        
        for header in predicted_finish_headers:
            table = header.find_parent('table')
            if not table:
                continue
                
            rows = table.find_all('tr')
            if len(rows) < 2:
                continue
                
            for row in rows[1:]:
                cells = row.find_all('td')
                if len(cells) >= 4:
                    try:
                        horse_no = int(self._text(cells[0]))
                        speed_index_text = self._text(cells[3])
                        
                        try:
                            speed_score = float(speed_index_text)
                        except ValueError:
                            speed_score = 50
                        
                        speed_data[horse_no] = {
                            'speed_index': speed_index_text,
                            'speed_score': speed_score
                        }
                        
                    except (ValueError, IndexError):
                        continue
            
            if speed_data:
                break
        
        return speed_data

    def _display_detailed_rankings(self, scores_data, race):
        """Display detailed rankings with component scores AND save to database"""
        self.stdout.write("\n" + "="*100)
        self.stdout.write(f"📊 DETAILED RANKINGS - Race {race.race_no}")
        self.stdout.write("="*100)
        
        # Sort by overall score descending
        sorted_rankings = sorted(scores_data, key=lambda x: x['overall_score'], reverse=True)
        
        # Display header
        header = f"{'Pos':<4} {'No':<4} {'Horse':<20} {'Total':<6} {'BestMR':<6} {'CurMR':<6} {'JT':<6} {'Form':<6} {'Class':<6} {'Speed':<6}"
        self.stdout.write(header)
        self.stdout.write("-" * 100)
        
        rankings_created = 0
        rankings_updated = 0
        
        for position, data in enumerate(sorted_rankings, 1):
            horse = data['horse']
            score_record = data['score_record']
            
            # Display on screen
            self.stdout.write(
                f"{position:<4} "
                f"{horse.horse_no:<4} "
                f"{horse.horse_name:<20} "
                f"{score_record.overall_score:<6} "
                f"{score_record.best_mr_score:<6} "
                f"{score_record.current_mr_score:<6} "
                f"{score_record.jt_score:<6} "
                f"{score_record.form_score:<6} "
                f"{score_record.class_score:<6} "
                f"{score_record.speed_rating:<6} "
            )
            
            # ✅ SAVE TO DATABASE
            try:
                ranking, created = Ranking.objects.update_or_create(
                    race=race,
                    horse=horse,
                    defaults={
                        'rank': position,
                        'score': score_record.overall_score,
                        'merit_score': score_record.current_mr_score,
                        'class_score': score_record.class_score,
                        'form_score': score_record.form_score,
                        'jt_score': score_record.jt_score,
                        'jt_rating': getattr(horse, 'jt_rating', ''),
                        'jockey': getattr(horse, 'jockey', ''),
                        'trainer': getattr(horse, 'trainer', ''),
                        'class_trend': 'stable',
                    }
                )
                
                if created:
                    rankings_created += 1
                    self.stdout.write(f"      💾 Saved to database as position #{position}")
                else:
                    rankings_updated += 1
                    self.stdout.write(f"      🔄 Updated database ranking #{position}")
                    
            except Exception as e:
                self.stdout.write(f"      ❌ Error saving ranking to database: {e}")
                import traceback
                self.stdout.write(traceback.format_exc())
        
        self.stdout.write("=" * 100)
        
        # Show summary
        self.stdout.write(f"💾 Database: {rankings_created} rankings created, {rankings_updated} updated")
        self.stdout.write(f"📊 Total horses ranked: {len(sorted_rankings)}")
        
        return rankings_created + rankings_updated
    
    # Add this to your command file
def find_bad_queries():
    """Function to help identify where bad queries are coming from"""
    # Check your model definitions for any issues
    from racecard_02.models import Horse, Run, Race, HorseScore
    
    # Look for any queries that might be passing strings instead of objects
    print("🔍 Checking for potential bad query patterns...")
    
    # Common places where this error occurs:
    # 1. Filter queries with string instead of object
    # 2. Foreign key assignments with string instead of object
    # 3. Related object lookups with string instead of object
    
    # Add debug prints to track queries
    import django.db.models.query
    original_filter = django.db.models.query.QuerySet.filter

    def debug_filter(self, *args, **kwargs):
        for key, value in kwargs.items():
            if isinstance(value, str) and '__' in key:  # This suggests a relation lookup
                print(f"⚠️ Potential bad filter: {key}={value}")
        return original_filter(self, *args, **kwargs)
    
    django.db.models.query.QuerySet.filter = debug_filter