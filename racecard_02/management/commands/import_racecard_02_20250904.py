"""
Training command: import the race header details (and horses) from a single
racecard HTML file and write them to the DB.

Run:
  python manage.py import_racecard path/to/file.html
  python manage.py import_racecard path/to/file.html --update

This prints detailed debug info at each step so you can see how parsing flows.
"""

import os
import re
from datetime import datetime, date, time
from django.utils import timezone  # Add this import

from bs4 import BeautifulSoup
from django.core.management.base import BaseCommand
from racecard_02.models import Race, Horse, Run, Ranking, HorseResult, HorseScore, ManualHorseResult, ManualResult
import json
from django.db.models import Q

# Import the services
from racecard_02.services.class_analysis import ClassAnalysisService
from racecard_02.services.run_analysis import RunAnalysisService

# -------------------------
# Helpers
# -------------------------
def ensure_date(val):
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    if isinstance(val, str):
        # Clean the string first
        clean_val = val.strip()
        # Handle cases like "(5) 24.10.05" or "(20)25.01.11"
        if '(' in clean_val and ')' in clean_val:
            clean_val = clean_val.split(')')[-1].strip()
        
        # Try different date formats
        for fmt in ("%y.%m.%d", "%d.%m.%y", "%y%m%d", "%d/%m/%Y", "%d/%m/%y"):
            try:
                return datetime.strptime(clean_val, fmt).date()
            except ValueError:
                continue
    raise ValueError(f"Cannot parse date from value: {val!r}")


def ensure_time(val):
    if isinstance(val, time):
        return val
    if isinstance(val, str):
        s = val.strip().replace(".", ":")
        if ":" in s:
            h, m = map(int, s.split(":")[:2])
        else:
            h, m = divmod(int(s), 100)
        return time(h, m)
    if isinstance(val, int):
        h, m = divmod(val, 100)
        return time(h, m)
    raise ValueError(f"Cannot parse time from value: {val!r}")


def _text(node, default=""):
    return node.get_text(strip=True) if node else default


class Command(BaseCommand):
    help = (
        "Import race header and horses from a racecard HTML file. "
        "Use --update to update existing DB rows."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Initialize the services
        self.class_analyzer = ClassAnalysisService()
        self.run_analyzer = RunAnalysisService()
        # Cache for J-T data (persists throughout command execution)
        self.jt_analysis_cache = {}

    # -------------------------
    # CLI arguments
    # -------------------------
    def add_arguments(self, parser):
        parser.add_argument("html_file", type=str, help="Path to a single racecard HTML file")
        parser.add_argument(
            "--update",
            action="store_true",
            dest="update",
            help="If set, update the existing Race (and Horses) with parsed values.",
        )

    # -------------------------
    # Jockey-Trainer Analysis Functions
    # -------------------------
    def analyze_jockey_trainer_combination(self, html_row):
        """
        Analyze jockey-trainer combination from HTML row
        """
        cells = html_row.find_all('td')
        cell_texts = [cell.get_text(strip=True) for cell in cells]
        
        self.stdout.write(f"🔍 ANALYZING J-T ROW: {cell_texts}")
        
        results = []
        
        # Helper function to parse numeric values safely
        def safe_int(value, default=0):
            try:
                return int(value.replace(',', '').replace('%', '').strip())
            except (ValueError, AttributeError):
                return default
        
        # Check if this is a two-column layout (horses 1-7 in first column, 8-13 in second)
        if len(cell_texts) >= 18:  # Two columns of data (9 cells per column)
            self.stdout.write("📊 Found two-column J-T layout")
            
            # Parse first column (horses 1-7)
            if len(cell_texts) >= 9:
                first_column = cell_texts[:9]
                try:
                    horse_number = first_column[0]
                    trainer = first_column[1]
                    jockey = first_column[2]
                    
                    # Parse numeric values
                    starts = safe_int(first_column[3])
                    first_places = safe_int(first_column[4])
                    second_places = safe_int(first_column[5])
                    third_places = safe_int(first_column[6])
                    win_percentage = safe_int(first_column[7])
                    place_percentage = safe_int(first_column[8])
                    
                    # Calculate score
                    score = (
                        (place_percentage * 0.4) +
                        (win_percentage * 0.3) +
                        (min(starts, 50) * 0.1) +
                        (25 if starts > 10 else 0)
                    )
                    score = max(0, min(100, round(score, 2)))
                    
                    results.append({
                        'horse_number': horse_number,
                        'jockey': jockey,
                        'trainer': trainer,
                        'score': score,
                        'rating': self.get_jt_rating(score)
                    })
                    
                    self.stdout.write(f"✅ First column: Horse {horse_number}, Score={score}")
                except Exception as e:
                    self.stdout.write(f"❌ Error parsing first column: {e}")
            
            # Parse second column (horses 8-13)
            if len(cell_texts) >= 18:
                second_column = cell_texts[9:18]  # Cells 9-17
                try:
                    horse_number = second_column[0]
                    trainer = second_column[1]
                    jockey = second_column[2]
                    
                    # Parse numeric values
                    starts = safe_int(second_column[3])
                    first_places = safe_int(second_column[4])
                    second_places = safe_int(second_column[5])
                    third_places = safe_int(second_column[6])
                    win_percentage = safe_int(second_column[7])
                    place_percentage = safe_int(second_column[8])
                    
                    # Calculate score
                    score = (
                        (place_percentage * 0.4) +
                        (win_percentage * 0.3) +
                        (min(starts, 50) * 0.1) +
                        (25 if starts > 10 else 0)
                    )
                    score = max(0, min(100, round(score, 2)))
                    
                    results.append({
                        'horse_number': horse_number,
                        'jockey': jockey,
                        'trainer': trainer,
                        'score': score,
                        'rating': self.get_jt_rating(score)
                    })
                    
                    self.stdout.write(f"✅ Second column: Horse {horse_number}, Score={score}")
                except Exception as e:
                    self.stdout.write(f"❌ Error parsing second column: {e}")
        
        else:
            # Single column layout (original logic)
            if len(cell_texts) >= 9:
                try:
                    horse_number = cell_texts[0]
                    trainer = cell_texts[1]
                    jockey = cell_texts[2]
                    
                    # Parse numeric values
                    starts = safe_int(cell_texts[3])
                    first_places = safe_int(cell_texts[4])
                    second_places = safe_int(cell_texts[5])
                    third_places = safe_int(cell_texts[6])
                    win_percentage = safe_int(cell_texts[7])
                    place_percentage = safe_int(cell_texts[8])
                    
                    # Calculate score
                    score = (
                        (place_percentage * 0.4) +
                        (win_percentage * 0.3) +
                        (min(starts, 50) * 0.1) +
                        (25 if starts > 10 else 0)
                    )
                    score = max(0, min(100, round(score, 2)))
                    
                    results.append({
                        'horse_number': horse_number,
                        'jockey': jockey,
                        'trainer': trainer,
                        'score': score,
                        'rating': self.get_jt_rating(score)
                    })
                    
                    self.stdout.write(f"✅ Single column: Horse {horse_number}, Score={score}")
                except Exception as e:
                    self.stdout.write(f"❌ Error parsing single column: {e}")
        
        return results

    def get_jt_rating(self, score):
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

    # -------------------------
    # Header parsing
    # -------------------------
    @staticmethod
    def _parse_header_td(soup):
        td = soup.find("td", align="center")
        if not td:
            return {}

        lines = list(td.stripped_strings)
        result = {
            "lines": lines,
            "course": lines[0] if lines else None,
            "date_text": None,
            "race_date": None,
            "race_no": None,
            "race_time_text": None,
            "race_time_hhmm": None,
        }

        # Date detection (accept 25/07/2025 or 25/07/25)
        for text in lines[1:4]:
            clean = text.strip()
            if re.fullmatch(r"\d{2}/\d{2}/\d{4}", clean):
                parsed_date = datetime.strptime(clean, "%d/%m/%Y").date()
                result["date_text"] = clean
                result["race_date"] = parsed_date
                break
            if re.fullmatch(r"\d{2}/\d{2}/\d{2}", clean):
                parsed_date = datetime.strptime(clean, "%d/%m/%y").date()
                result["date_text"] = clean
                result["race_date"] = parsed_date
                break

        # Race number in <div class="rev4">
        rev4 = td.find("div", class_="rev4")
        if rev4:
            m = re.search(r"\d+", rev4.get_text(strip=True))
            if m:
                result["race_no"] = int(m.group())

        # Race time in <div class="b1">
        b1 = td.find("div", class_="b1")
        if b1:
            raw = b1.get_text(strip=True)
            result["race_time_text"] = raw
            normalized = raw.replace(".", ":")
            try:
                t = datetime.strptime(normalized, "%H:%M").time()
                result["race_time_hhmm"] = t.hour * 100 + t.minute
            except Exception:
                m2 = re.search(r"\b(\d{3,4})\b", raw)
                if m2:
                    try:
                        result["race_time_hhmm"] = int(m2.group(1))
                    except Exception:
                        result["race_time_hhmm"] = None

        return result

    @staticmethod
    def _parse_right_td_for_details(right_td):
        result = {
            "race_name": None,
            "race_distance": None,
            "race_class": None,
            "race_merit": None,
        }
        if not right_td:
            return result

        b2 = right_td.find("div", class_="b2")
        if b2:
            b2_lines = list(b2.stripped_strings)
            if b2_lines:
                result["race_name"] = b2_lines[0]
            if len(b2_lines) > 1:
                m = re.search(r"(\d+)\s*Metres", b2_lines[1], flags=re.I)
                if m:
                    result["race_distance"] = m.group(1)

        for text in (t.strip() for t in right_td.stripped_strings if t.strip()):
            low = text.lower()
            if any(k in low for k in (
                "class", "maiden", "merit rated", "benchmark", "handicap",
                "stakes", "conditions", "plate", "allowance", "apprentice",
                "novice", "graduation", "restricted"
            )):
                result["race_class"] = text
                m = re.search(r"Merit\s*Rated\s*(\d{1,3})", text, flags=re.I)
                if not m:
                    m = re.search(r"Benchmark\s*(\d{1,3})", text, flags=re.I)
                if not m:
                    m = re.search(r"\b(\d{2,3})\b", text)
                if m:
                    try:
                        result["race_merit"] = int(m.group(1))
                    except Exception:
                        result["race_merit"] = 0
                else:
                    result["race_merit"] = 0
                break

        return result

    def _parse_horse_runs(self, horse_table, horse_obj):
        """Extract and save the last 4 runs for a horse"""
        runs = []
        
        # Find all run rows - looking for class="small" in your HTML
        run_rows = horse_table.find_all('tr', class_='small') or []
        
        for run_row in run_rows[:4]:  # Only take last 4 runs
            try:
                cols = [td.get_text(strip=True) for td in run_row.find_all('td')]
                if len(cols) < 15:  # Make sure we have enough columns
                    continue
                    
                # Extract and parse date
                date_text = cols[0]
                run_date = ensure_date(date_text)
                
                # Extract position (from what appears to be column 13 in debug output)
                position = cols[12] if len(cols) > 12 else ""
                
                # Extract margin (from column 13 in debug output)
                margin = cols[13] if len(cols) > 13 else ""
                
                # Extract distance (from column 7 in debug output)
                distance = cols[6] if len(cols) > 6 else ""
                
                # Extract race class (from column 5 in debug output)
                race_class = cols[4] if len(cols) > 4 else ""
                
                # Create the run record
                Run.objects.create(
                    horse=horse_obj,
                    run_date=run_date,
                    position=position,
                    margin=margin,
                    distance=distance,
                    race_class=race_class
                )
                runs.append({
                    'date': run_date,
                    'position': position,
                    'margin': margin,
                    'distance': distance,
                    'class': race_class
                })
                
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Could not parse run row: {e}"))
                continue
                
        return runs

    # -------------------------
    # Horse parsing
    # -------------------------
    def _parse_horses(self, soup, race, update_existing: bool):
        """
        Parse horse blocks. We only consider tables that:
        - have border="border"
        - contain a <div class="b4"> with a numeric horse number
        """
        self.stdout.write("\n🔍 Extracting Horses...")
        created_or_updated = 0
        horse_tables = soup.select('table[border="border"]')
        self.stdout.write(f"Found {len(horse_tables)} horse tables")
        
        # FIRST: Find and parse the jockey-trainer stats table
        jt_analysis_data = self._parse_jockey_trainer_table(soup)
        self.stdout.write(f"J-T analysis data keys: {list(jt_analysis_data.keys())}")
        
        # Store in class cache for later use in score calculation
        self.jt_analysis_cache = jt_analysis_data
        self.stdout.write(f"✅ Stored J-T data in class cache: {len(self.jt_analysis_cache)} horses")
        
        for idx, table in enumerate(horse_tables, start=1):
            try:
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
                    horse_no = int(_text(num_div))
                    self.stdout.write(f"Processing horse {horse_no}...")
                except Exception as e:
                    self.stdout.write(f"Skipping table {idx}: Could not parse horse number: {e}")
                    continue

                odds_el = td0.find("div", class_="b1")
                odds = _text(odds_el)

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
                    horse_name = _text(name_cell) or _text(td1)
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

                # --- Jockey / Trainer (nested table) ---
                # Look inside the current horse's table for any "div.itbld"
                itbld_divs = table.select("div.itbld")
                jockey, trainer = "", ""
                if len(itbld_divs) >= 1:
                    jockey = " ".join(itbld_divs[0].stripped_strings)
                if len(itbld_divs) >= 2:
                    trainer = " ".join(itbld_divs[1].stripped_strings)

                # --- Jockey-Trainer Analysis ---
                jt_score = 50  # Default neutral score
                jt_rating = "Average"
                
                self.stdout.write(f"Looking for J-T data for horse {horse_no}...")
                self.stdout.write(f"Available J-T keys: {list(jt_analysis_data.keys())}")
                
                # Use the pre-parsed jockey-trainer data if available
                if horse_no in jt_analysis_data:
                    jt_data = jt_analysis_data[horse_no]
                    jt_score = jt_data['score']
                    jt_rating = jt_data['rating']
                    # Use the jockey/trainer from analysis if available (more accurate)
                    jockey = jt_data.get('jockey', jockey)
                    trainer = jt_data.get('trainer', trainer)
                    self.stdout.write(f"✅ Found J-T data for horse {horse_no}: Score={jt_score}")
                else:
                    self.stdout.write(f"❌ No J-T data found for horse {horse_no}, using default score 50")
                    self.stdout.write(f"Available horse numbers in J-T data: {list(jt_analysis_data.keys())}")

                # --- Debug prints ---
                self.stdout.write(f"[DEBUG] Horse {horse_no}: name={horse_name}")
                self.stdout.write(f"[DEBUG]  -> Odds={odds}, Merit={horse_merit}, Blinkers={blinkers}, Age={age}")
                self.stdout.write(f"[DEBUG]  -> Jockey={jockey}, Trainer={trainer}")
                self.stdout.write(f"[DEBUG]  -> Jockey-Trainer Score={jt_score}, Rating={jt_rating}")

                self.stdout.write(f"🐎 FINAL JT SCORE FOR HORSE {horse_no}: {jt_score}")

                # Ensure safe field lengths
                age = (age or "")[:10]
                odds = (odds or "")[:20]

                # Upsert
                defaults = dict(
                    horse_name=horse_name,
                    blinkers=bool(blinkers),
                    age=age,
                    dob="",  # not present in provided markup
                    odds=odds,
                    horse_merit=horse_merit if horse_merit is not None else 0,
                    race_class=race.race_class or "",
                    trainer=trainer,
                    jockey=jockey,
                    jt_score=jt_score,        # ADD THIS
                    jt_rating=jt_rating,      # ADD THIS
                )
                obj, created = Horse.objects.update_or_create(
                    race=race, horse_no=horse_no, defaults=defaults
                )
                created_or_updated += 1
                self.stdout.write(
                    f"🐎 Horse {horse_no}: {horse_name} | "
                    f"Blinkers={blinkers} | Odds={odds or '-'} | "
                    f"Merit={defaults['horse_merit']} | "
                    f"Jockey={jockey or '-'} | Trainer={trainer or '-'} | "
                    f"J-T Score={jt_score} | J-T Rating={jt_rating}"
                )

                # Add runs extraction
                runs = self._parse_horse_runs(table, obj)
                if runs:
                    self.stdout.write(f"    📜 Added {len(runs)} past runs:")
                    for run in runs:
                        self.stdout.write(f"      - {run['date']}: Pos {run['position']} ({run['margin']}) {run['distance']}m {run['class']}")

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
        
        # Look for ALL tables to find the right one
        for i, table in enumerate(soup.find_all('table')):
            # Get the first row to see table structure
            first_row = table.find('tr')
            if not first_row:
                continue
                
            cells = first_row.find_all(['td', 'th'])
            cell_texts = [cell.get_text(strip=True) for cell in cells]
            
            self.stdout.write(f"Table {i}: First row cells: {cell_texts}")
            
            # Check if this looks like a J-T table
            has_jockey = any('jockey' in text.lower() for text in cell_texts)
            has_trainer = any('trainer' in text.lower() for text in cell_texts)
            has_rns = any('rns' in text.lower() for text in cell_texts)
            
            if has_jockey and has_trainer:
                self.stdout.write(f"🎯 FOUND POTENTIAL J-T TABLE {i}!")
                self.stdout.write("Let me examine this table more closely...")
                
                # Examine all rows in this table
                for j, row in enumerate(table.find_all('tr')):
                    row_cells = row.find_all('td')
                    row_texts = [cell.get_text(strip=True) for cell in row_cells]
                    
                    if len(row_texts) < 5:  # Skip short rows
                        continue
                        
                    # Skip header rows
                    if any(text.lower() in ['jockey', 'trainer', 'rns', 'no'] for text in row_texts):
                        self.stdout.write(f"  📋 Header row: {row_texts}")
                        continue
                    
                    self.stdout.write(f"  📊 Row {j}: {row_texts}")
                    
                    # Parse the J-T data - you'll need to implement this method
                    jt_results = self._analyze_jockey_trainer_combination(row)
                    
                    for result in jt_results:
                        try:
                            horse_no = int(result['horse_number'])
                            jt_analysis_data[horse_no] = {
                                'score': result['score'],
                                'rating': result['rating'],
                                'jockey': result['jockey'],
                                'trainer': result['trainer']
                            }
                            self.stdout.write(f"  🎯 Horse {horse_no}: J-T Score={result['score']}, Jockey={result['jockey']}, Trainer={result['trainer']}")
                        except (ValueError, KeyError) as e:
                            self.stdout.write(f"  ❌ Could not parse J-T result: {e}")
                            continue
                
                if jt_analysis_data:
                    self.stdout.write(f"✅ Successfully parsed J-T data from table {i}")
                    break
                else:
                    self.stdout.write(f"❌ No J-T data parsed from table {i}")
        
        if not jt_analysis_data:
            self.stdout.write("❌ CRITICAL: No J-T table found or no data parsed!")
            self.stdout.write("Please check if the HTML contains a jockey-trainer stats table")
            self.stdout.write("The table should have columns: HorseNo, Trainer, Jockey, Rns, 1st, 2nd, 3rd, Win%, PLC%")
        else:
            self.stdout.write(f"✅ SUCCESS: Parsed J-T data for {len(jt_analysis_data)} horses: {list(jt_analysis_data.keys())}")
            for horse_no, data in jt_analysis_data.items():
                self.stdout.write(f"   Horse {horse_no}: Score={data['score']}, Jockey={data['jockey']}, Trainer={data['trainer']}")
        
        return jt_analysis_data




    def _analyze_jockey_trainer_combination(self, row):
        """
        Analyze jockey-trainer combination from a table row
        Returns a list of results (usually one result per row)
        """
        results = []
        
        try:
            cells = row.find_all('td')
            if len(cells) < 8:  # Need enough columns for proper analysis
                return results
            
            # Extract data from cells - adjust these indices based on your table structure
            horse_no = cells[0].get_text(strip=True)
            trainer = cells[1].get_text(strip=True)
            jockey = cells[2].get_text(strip=True)
            runs = cells[3].get_text(strip=True)
            wins = cells[4].get_text(strip=True)
            
            # Calculate score based on win percentage
            try:
                runs_int = int(runs) if runs else 0
                wins_int = int(wins) if wins else 0
                win_percentage = (wins_int / runs_int * 100) if runs_int > 0 else 0
                
                # Convert win percentage to a score (0-100)
                score = min(100, win_percentage * 2)  # Scale appropriately
                
                # Determine rating
                if score >= 80:
                    rating = "Excellent"
                elif score >= 60:
                    rating = "Very Good"
                elif score >= 40:
                    rating = "Good"
                elif score >= 20:
                    rating = "Average"
                else:
                    rating = "Poor"
                    
                results.append({
                    'horse_number': horse_no,
                    'jockey': jockey,
                    'trainer': trainer,
                    'runs': runs_int,
                    'wins': wins_int,
                    'win_percentage': win_percentage,
                    'score': round(score),
                    'rating': rating
                })
                
            except (ValueError, ZeroDivisionError):
                # If parsing numbers fails, use default score
                results.append({
                    'horse_number': horse_no,
                    'jockey': jockey,
                    'trainer': trainer,
                    'score': 50,
                    'rating': "Average"
                })
                
        except Exception as e:
            self.stdout.write(f"❌ Error analyzing J-T combination: {e}")
        
        return results







    # In your run analyzer class
    def analyze_horse_runs(self, horse):
        """
        Analyze all runs for a specific horse
        """
        # Ensure we have a Horse instance with an ID
        if not hasattr(horse, 'id') or not horse.id:
            self.stdout.write(f"DEBUG: Invalid horse object received: {horse}")
            return None
        
        try:
            # Get all runs for this horse by name (since runs might not be linked by FK)
            runs = Run.objects.filter(horse_name=horse.horse_name).order_by('-date')
            
            if not runs.exists():
                self.stdout.write(f"DEBUG: No runs found for horse: {horse.horse_name}")
                return {
                    'total_runs': 0,
                    'recent_form': [],
                    'avg_finish_position': None,
                    'consistency': None,
                    'last_5_starts': [],
                    'best_finish': None,
                    'win_percentage': 0,
                    'place_percentage': 0
                }
            
            # Perform analysis on the runs
            analysis = {
                'total_runs': runs.count(),
                'recent_form': [run.finish_position for run in runs[:5] if run.finish_position],
                'avg_finish_position': runs.aggregate(avg=models.Avg('finish_position'))['avg__avg'],
                'last_5_starts': [{
                    'date': run.date,
                    'position': run.finish_position,
                    'track': run.track,
                    'distance': run.distance
                } for run in runs[:5]],
                # Add more analysis as needed
            }
            
            return analysis
            
        except Exception as e:
            self.stdout.write(f"DEBUG: Error in analyze_horse_runs: {str(e)}")
            return None



    
    def calculate_form_score(self, run_analysis):
        """
        Calculate form score based on run analysis
        """
        if not run_analysis or run_analysis['runs_analyzed'] == 0:
            return 50  # Default score
        
        try:
            # Lower average position = better form
            avg_position = run_analysis['average_position']
            if avg_position is None:
                return 50
                
            # Convert average position to score (1st = 100, 10th = 0)
            form_score = max(0, 100 - (avg_position * 10))
            
            # Adjust based on form rating (lower form_rating is better)
            form_rating = run_analysis.get('form_rating', 0)
            if form_rating > 0:
                form_score = form_score * (1 - (form_rating / 100))
            
            # Adjust based on consistency
            consistency = run_analysis.get('consistency', 0)
            form_score = form_score * (consistency / 100)
            
            return min(100, max(0, form_score))
            
        except Exception as e:
            print(f"ERROR calculating form score: {e}")
            return 50
    
    def calculate_speed_rating(self, run_analysis):
        """
        Calculate speed rating (was calculate_speed_score)
        """
        if not run_analysis or run_analysis['runs_analyzed'] == 0:
            return 50
            
        try:
            # Your speed calculation logic
            avg_position = run_analysis['average_position']
            if avg_position is None:
                return 50
                
            # Better positions = higher speed rating
            speed_rating = max(0, 100 - (avg_position * 8))
            
            return min(100, max(0, speed_rating))
            
        except Exception as e:
            print(f"ERROR calculating speed rating: {e}")
            return 50

# Remove the old calculate_speed_score method if it exists
# def calculate_speed_score(self, run_analysis):  # DELETE THIS
    
    def calculate_class_score(self, run_analysis):
        """
        Calculate class score based on race class analysis
        """
        if not run_analysis or run_analysis['runs_analyzed'] == 0:
            return 50
            
        try:
            avg_class = run_analysis.get('average_class')
            if avg_class is None:
                return 50
                
            # Higher class weight = better class = higher score
            # Assuming class weights are 0-100 where higher is better
            class_score = avg_class
            
            return min(100, max(0, class_score))
            
        except Exception as e:
            print(f"ERROR calculating class score: {e}")
            return 50
    
    def calculate_jockey_score(self, jockey_name):
        """
        Calculate jockey score based on jockey name
        """
        if not jockey_name:
            return 50
            
        try:
            # Placeholder - implement proper jockey rating system
            # For now, return a fixed score or base it on some metric
            
            # Simple implementation: return fixed score based on jockey "quality"
            # You should replace this with actual jockey performance data
            
            jockey_name_lower = jockey_name.lower()
            
            # Example: give higher scores to jockeys with certain names
            # This is just a placeholder - use actual jockey statistics
            if any(name in jockey_name_lower for name in ['smith', 'jones', 'brown']):
                return 75
            elif any(name in jockey_name_lower for name in ['wilson', 'taylor', 'davis']):
                return 65
            else:
                return 55
                
        except Exception as e:
            print(f"ERROR calculating jockey score: {e}")
            return 50
        
    
    def calculate_trainer_score(self, trainer_name):
        """
        Calculate trainer score based on trainer name
        """
        if not trainer_name:
            return 50
            
        try:
            # Placeholder - implement proper trainer rating system
            trainer_name_lower = trainer_name.lower()
            
            # Give higher scores to more successful/experienced trainers
            if any(name in trainer_name_lower for name in ['bass', 'smith', 'jones', 'brown', 'master']):
                return 75
            elif any(name in trainer_name_lower for name in ['wilson', 'taylor', 'davis', 'murray', 'coach']):
                return 65
            else:
                return 55
                
        except Exception as e:
            self.stdout.write(f"ERROR calculating trainer score for {trainer_name}: {e}")
            return 50
        
        
    def calculate_weight_score(self, weight):
        """
        Calculate weight score based on carried weight
        """
        if not weight:
            return 50
            
        try:
            # Convert weight to numeric if it's a string
            if isinstance(weight, str):
                # Remove non-numeric characters
                weight_value = float(''.join(filter(str.isdigit, weight)))
            else:
                weight_value = float(weight)
                
            # Lower weight = better score (typically)
            # Adjust this formula based on your specific requirements
            if weight_value < 52:
                return 80  # Very light weight
            elif weight_value < 55:
                return 70  # Light weight
            elif weight_value < 58:
                return 60  # Medium weight
            elif weight_value < 61:
                return 50  # Average weight
            else:
                return 40  # Heavy weight
                
        except Exception as e:
            print(f"ERROR calculating weight score: {e}")
            return 50
    
    # ... rest of your existing code ...
  

    def calculate_horse_score(self, horse):
        """
        Calculate score for a single horse - using correct field names
        """
        try:
            # DEBUG: Check what we're receiving
            self.stdout.write(f"DEBUG: calculate_horse_score received {type(horse)}: {horse}")
            
            # If horse is a string, try to find the Horse instance
            if isinstance(horse, str):
                self.stdout.write(f"DEBUG: Looking up horse by name: {horse}")
                try:
                    horse_instance = Horse.objects.get(horse_name=horse)
                    horse = horse_instance
                    self.stdout.write(f"DEBUG: Found horse instance: {horse}")
                except Horse.DoesNotExist:
                    self.stdout.write(self.style.ERROR(f"    ❌ Horse not found: {horse}"))
                    return None
                except Horse.MultipleObjectsReturned:
                    self.stdout.write(self.style.WARNING(f"    ⚠️ Multiple horses found with name: {horse}"))
                    horse_instance = Horse.objects.filter(horse_name=horse).first()
                    horse = horse_instance
                    self.stdout.write(f"DEBUG: Using first match: {horse}")
            
            self.stdout.write(f"    🏇 Calculating score for {horse.horse_name}...")
            
            # Get run analysis
            run_analysis = self.run_analyzer.analyze_horse_runs(horse)
            
            if not run_analysis:
                self.stdout.write(f"    ⚠️ No run analysis available for {horse.horse_name}")
                # Set default scores if no analysis available
                form_score = 50
                class_score = 50
                consistency_score = 50
                speed_rating = 50
            else:
                # Calculate scores based on different factors - using correct field names
                form_score = self.calculate_form_score(run_analysis)
                class_score = self.calculate_class_score(run_analysis)
                consistency_score = run_analysis.get('consistency', 50)
                speed_rating = self.calculate_speed_rating(run_analysis)  # Changed from speed_score
            
            # Safely get jockey and trainer using getattr
            jockey = getattr(horse, 'jockey', None)
            trainer = getattr(horse, 'trainer', None)
            
            jockey_score = self.calculate_jockey_score(jockey) if jockey else 50
            trainer_score = self.calculate_trainer_score(trainer) if trainer else 50
            
            # For fields that might not be calculated yet, set defaults
            merit_score = 50  # You might want to calculate this
            distance_score = 50  # You might want to calculate this
            stamina_index = 50  # You might want to calculate this
            track_affinity = 50  # You might want to calculate this
            days_since_last_run = run_analysis.get('days_since_last_run', 0) if run_analysis else 0
            recovery_score = 50  # You might want to calculate this
            
            # Calculate overall score (adjust weights as needed)
            overall_score = (
                form_score * 0.2 +
                class_score * 0.15 +
                consistency_score * 0.1 +
                speed_rating * 0.1 +
                jockey_score * 0.1 +
                trainer_score * 0.05 +
                merit_score * 0.1 +
                distance_score * 0.05 +
                stamina_index * 0.05 +
                track_affinity * 0.05 +
                recovery_score * 0.05
            )
            
            # Create or update HorseScore with CORRECT field names
            horse_score, created = HorseScore.objects.update_or_create(
                horse=horse,
                race=horse.race,
                defaults={
                    'overall_score': overall_score,
                    'merit_score': merit_score,
                    'form_score': form_score,
                    'class_score': class_score,
                    'distance_score': distance_score,
                    'consistency_score': consistency_score,
                    'speed_rating': speed_rating,  # Correct field name
                    'stamina_index': stamina_index,
                    'track_affinity': track_affinity,
                    'jockey_score': jockey_score,
                    'trainer_score': trainer_score,
                    'days_since_last_run': days_since_last_run,
                    'recovery_score': recovery_score,
                    'calculated_at': timezone.now()
                }
            )
            
            self.stdout.write(f"    ✅ Score calculated: {overall_score:.2f}")
            return horse_score
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"    ❌ Error calculating score for {horse}: {str(e)}"))
            import traceback
            self.stdout.write(self.style.ERROR(f"    Traceback: {traceback.format_exc()}"))
            return None





    def rank_horses(self, race):
        """
        Rank horses in a race based on their scores
        """
        ranked_horses = []
        
        # Get all horses in this race
        horses = Horse.objects.filter(race=race)
        
        for horse in horses:
            horse_score = self.calculate_horse_score(horse)
            if horse_score:
                # Get the actual scores for each category
                ranked_horses.append({
                    'horse': horse,
                    'score': horse_score.overall_score,
                    'merit_score': getattr(horse, 'horse_merit', 0) or 0,
                    'class_score': horse_score.class_score,
                    'form_score': horse_score.form_score,
                    'jt_score': horse_score.jockey_score + (getattr(horse_score, 'trainer_score', 0) or 0),
                    'rank': 0,  # Will be set after sorting
                    'jockey': getattr(horse, 'jockey', ''),
                    'trainer': getattr(horse, 'trainer', ''),
                    'class_trend': "stable"
                })
        
        # Sort by overall score (descending)
        ranked_horses.sort(key=lambda x: x['score'], reverse=True)
        
        # Set actual ranks
        for i, horse_data in enumerate(ranked_horses, 1):
            horse_data['rank'] = i
        
        # Print the rankings
        self.print_horse_rankings(ranked_horses)
        
        # Save to database
        self._save_rankings_to_db(race, ranked_horses)
        
        return ranked_horses


    def print_horse_rankings(self, ranked_horses):
        """Print the horse rankings in a readable format"""
        if not ranked_horses:
            return
            
        self.stdout.write("\n🏇 Horse Rankings:")
        self.stdout.write("{:<5} {:<5} {:<20} {:<8} {:<8} {:<8} {:<8} {:<8} {:<10}".format(
            "Rank", "No", "Name", "Score", "Merit", "Class", "Form", "J-T", "Trend"
        ))
        
        for horse_data in ranked_horses:
            horse = horse_data['horse']
            rank = horse_data['rank']
            score = horse_data['score']
            merit_score = horse_data.get('merit_score', 0)
            class_score = horse_data.get('class_score', 0)
            form_score = horse_data.get('form_score', 0)
            jt_score = horse_data.get('jt_score', 0)
            
            horse_no = getattr(horse, 'horse_no', 'N/A')
            horse_name = getattr(horse, 'horse_name', 'Unknown')[:18]
            
            self.stdout.write("{:<5} {:<5} {:<20} {:<8.1f} {:<8} {:<8.1f} {:<8.1f} {:<8.1f} {:<10}".format(
                rank,
                horse_no,
                horse_name,
                score,
                merit_score,
                class_score,
                form_score,
                jt_score,
                "stable"  # placeholder
            ))
    def _save_rankings_to_db(self, race, ranked_horses):
        """Save rankings to the database - clear existing first"""
        # Clear existing rankings for this race
        deleted_count, _ = Ranking.objects.filter(race=race).delete()
        self.stdout.write(f"  🗑️ Cleared {deleted_count} existing rankings")
        
        # Create new rankings
        for horse_data in ranked_horses:
            ranking_data = {
                'race': race,
                'horse': horse_data['horse'],
                'score': horse_data['score'],
                'merit_score': horse_data.get('merit_score', 0),
                'class_score': horse_data.get('class_score', 0),
                'form_score': horse_data.get('form_score', 0),
                'rank': horse_data['rank'],
                'jt_score': horse_data.get('jt_score', 0),
                'jt_rating': self.get_jt_rating(horse_data.get('jt_score', 0)),
                'jockey': horse_data.get('jockey', ''),
                'trainer': horse_data.get('trainer', ''),
                'class_trend': horse_data.get('class_trend', 'stable'),
            }
            Ranking.objects.create(**ranking_data)
        
        self.stdout.write(f"  ✅ Created {len(ranked_horses)} new rankings")
    def _calculate_advanced_scores(self, race):
        """Calculate and store advanced HorseScore records"""
        from racecard.services.scoring_service import HorseScoringService
        
        self.stdout.write("\n[STEP 9] Calculating advanced horse scores...")
        
        horses = Horse.objects.filter(race=race)
        scores_created = 0
        scores_updated = 0
        

        for horse in horses:
            try:
                scoring_service = HorseScoringService(horse, race)
                score_record, created = scoring_service.create_score_record()
                
                action = "Created" if created else "Updated"
                if created:
                    scores_created += 1
                else:
                    scores_updated += 1
                    
                self.stdout.write(
                    f"  📊 {horse.horse_name}: {action} score - Overall={score_record.overall_score:.3f} "
                    f"(M:{score_record.merit_score:.3f}, F:{score_record.form_score:.3f}, "
                    f"D:{score_record.distance_score:.3f}, C:{score_record.consistency_score:.3f})"
                )
                
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Could not calculate score for {horse.horse_name}: {e}"))
        
        self.stdout.write(self.style.SUCCESS(
            f"✅ Advanced scores processed: {scores_created} created, {scores_updated} updated"
        ))
        return scores_created + scores_updated
    


# Add to your existing import_racecard.py Command class

    def _create_manual_results(self, race, ranked_horses):
        """Create manual result entries for the new racecard_02 app"""
        try:
            
            # Get or create manual result
            manual_result, created = ManualResult.objects.get_or_create(
                race=race,
                defaults={
                    'entered_by': User.objects.first(),  # Or use a specific user
                    'verified': True
                }
            )
            
            # Create horse results based on predictions (not actual results yet)
            for horse_data in ranked_horses:
                ManualHorseResult.objects.get_or_create(
                    manual_result=manual_result,
                    horse=horse_data['horse'],
                    defaults={
                        'position': horse_data['rank'],  # Predicted position
                        'margin': '',
                        'time': '',
                    }
                )
            
            self.stdout.write(f"✅ Created manual results for racecard_02")
            
        except ImportError:
            self.stdout.write(self.style.WARNING("⚠️ racecard_02 app not available"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️ Error creating manual results: {e}"))

    def _update_with_actual_results(self, race, actual_results):
        """Update manual results with actual race outcomes when available"""
        try:
            from racecard_02.models import ManualResult, ManualHorseResult
            
            # Get the manual result for this race
            manual_result = ManualResult.objects.get(race=race)
            
            # Update with actual results
            for horse_no, position in actual_results.items():
                try:
                    horse = Horse.objects.get(race=race, horse_no=horse_no)
                    horse_result = ManualHorseResult.objects.get(
                        manual_result=manual_result,
                        horse=horse
                    )
                    horse_result.position = position
                    horse_result.save()
                except (Horse.DoesNotExist, ManualHorseResult.DoesNotExist):
                    continue
            
            self.stdout.write(f"✅ Updated with actual results for {len(actual_results)} horses")
            
        except ImportError:
            self.stdout.write(self.style.WARNING("⚠️ racecard_02 app not available"))
        except ManualResult.DoesNotExist:
            self.stdout.write(self.style.WARNING("⚠️ No manual result found for race"))
        except Exception as e:
            self.stdout.write(self.style.WARNING(f"⚠️ Error updating results: {e}"))





    # -------------------------
    # Main handler
    # -------------------------
    def handle(self, *args, **options):
        html_file = options["html_file"]
        update_existing = options["update"]

        # Step 1: file existence
        self.stdout.write(f"\n[STEP 1] Checking file: {html_file}")
        if not os.path.exists(html_file):
            self.stdout.write(self.style.ERROR("❌ File not found. Aborting."))
            return
        self.stdout.write(self.style.SUCCESS("✅ File exists."))

        # Step 2: load HTML
        self.stdout.write("\n[STEP 2] Loading and parsing HTML...")
        with open(html_file, "r", encoding="utf-8") as fh:
            soup = BeautifulSoup(fh, "html.parser")
        self.stdout.write(self.style.SUCCESS("✅ HTML loaded into BeautifulSoup."))

        # Step 3: parse header (left) td
        self.stdout.write("\n[STEP 3] Extracting header block (course/date/no/time)...")
        header = self._parse_header_td(soup)

        self.stdout.write(f"  • Raw header lines: {header.get('lines')}")
        self.stdout.write(f"  • Course/Field: {header.get('course')!r}")
        self.stdout.write(f"  • Date text: {header.get('date_text')!r} -> Parsed: {header.get('race_date')!r}")
        self.stdout.write(f"  • Race No (rev4): {header.get('race_no')!r}")
        self.stdout.write(f"  • Race time raw: {header.get('race_time_text')!r} -> HHMM: {header.get('race_time_hhmm')!r}")

        essential_ok = all([
            bool(header.get("course")),
            bool(header.get("race_date")),
            header.get("race_no") is not None,
        ])
        if not essential_ok:
            self.stdout.write(self.style.ERROR("❌ Missing essential header info (course/date/race_no). Aborting."))
            return
        self.stdout.write(self.style.SUCCESS("✅ Header looks good."))

        # Step 4: parse right td for name/distance/class/merit
        self.stdout.write("\n[STEP 4] Extracting race details (name/distance/class/merit)...")
        left_td = soup.find("td", align="center")
        right_td = left_td.find_next_sibling("td") if left_td else None
        details = self._parse_right_td_for_details(right_td)

        self.stdout.write(f"  • race_name: {details.get('race_name')!r}")
        self.stdout.write(f"  • race_distance: {details.get('race_distance')!r}")
        self.stdout.write(f"  • race_class: {details.get('race_class')!r}")
        self.stdout.write(f"  • race_merit: {details.get('race_merit')!r}")
        self.stdout.write(self.style.SUCCESS("✅ Details extracted."))

        # Step 5: prepare DB fields (match your Race model fields)
        race_date = ensure_date(header["race_date"])
        race_no = int(header["race_no"])
        race_time_obj = ensure_time(header["race_time_hhmm"])  # -> datetime.time
        race_field = header["course"].strip()
        race_name = details.get("race_name") or ""
        race_distance = details.get("race_distance") or ""
        race_class = details.get("race_class") or ""
        race_merit = details.get("race_merit") or 0

        self.stdout.write("\n[STEP 5] Prepared DB values:")
        self.stdout.write(f"  • race_date={race_date}, race_no={race_no}, race_time={race_time_obj}")
        self.stdout.write(f"  • race_field={race_field!r}, race_name={race_name!r}")
        self.stdout.write(f"  • race_distance={race_distance!r}, race_class={race_class!r}, race_merit={race_merit!r}")

        # Step 6: write Race to DB
        self.stdout.write("\n[STEP 6] Writing Race to database...")
        try:
            race, created = Race.objects.get_or_create(
                race_date=race_date,
                race_no=race_no,
                race_field=race_field,
                defaults={
                    "race_time": race_time_obj,
                    "race_name": race_name,
                    "race_distance": race_distance,
                    "race_class": race_class,
                    "race_merit": race_merit,
                },
            )

            if not created and update_existing:
                race.race_time = race_time_obj
                race.race_name = race_name
                race.race_distance = race_distance
                race.race_class = race_class
                race.race_merit = race_merit
                race.save()
                self.stdout.write(self.style.SUCCESS("🔄 Updated existing Race (because --update was used)."))
            elif created:
                self.stdout.write(self.style.SUCCESS("✅ Created new Race row."))
            else:
                self.stdout.write("ℹ️ Race already exists (same date/no/field).")

            self.stdout.write(
                f"  id={race.id} | date={race.race_date} | no={race.race_no} | "
                f"field={race.race_field} | time={race.race_time} | "
                f"name={race.race_name!r} | distance={race.race_distance!r} | "
                f"class={race.race_class!r} | merit={race.race_merit!r}"
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ DB write failed (Race): {e}"))
            return

        # Step 7: write Horses to DB
        self._parse_horses(soup, race, update_existing)

        # Step 8: Calculate and store rankings
        self.stdout.write("\n[STEP 8] Calculating horse rankings...")
        try:
            ranked_horses = self.rank_horses(race)
            self.print_horse_rankings(ranked_horses)
            self._save_rankings_to_db(race, ranked_horses)
            self.stdout.write(self.style.SUCCESS("✅ Rankings calculated and stored."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error calculating rankings: {e}"))
            import traceback
            self.stdout.write(traceback.format_exc())

        self.stdout.write(self.style.SUCCESS("\n✅ Done. Racecard import finished."))

        # Step 9: Calculate advanced scores for AI
        self._calculate_advanced_scores(race)


    
        
         # Step 8: Calculate and store rankings
        self.stdout.write("\n[STEP 8] Calculating horse rankings...")
        try:
            ranked_horses = self.rank_horses(race)
            self.print_horse_rankings(ranked_horses)
            self._save_rankings_to_db(race, ranked_horses)
            self.stdout.write(self.style.SUCCESS("✅ Rankings calculated and stored."))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error calculating rankings: {e}"))
            import traceback
            self.stdout.write(traceback.format_exc())

        self.stdout.write(self.style.SUCCESS("\n✅ Done. Racecard import finished."))

        # Step 9: Calculate advanced scores for AI
        self._calculate_advanced_scores(race)