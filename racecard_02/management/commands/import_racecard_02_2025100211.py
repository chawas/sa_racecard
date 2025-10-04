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
        self.enhanced_scoring_service = EnhancedScoringService(debug_callback=self.stdout.write)

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
        self.stdout.write("🚀 STARTING RACECARD IMPORT - ENHANCED SCORING SYSTEM")
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
                        self._calculate_enhanced_horse_scores(race)  # ENHANCED METHOD
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

    def _calculate_enhanced_horse_scores(self, race):
        """ENHANCED: Calculate horse scores with robust error handling"""
        from racecard_02.models import Horse, HorseScore
        
        self.stdout.write(f"🎯 ENHANCED SCORING for Race {race.race_no}")
        self.stdout.write("=" * 60)
        
        try:
            # Get all horses for this race
            horses = Horse.objects.filter(race=race)
            self.stdout.write(f"📊 Processing {horses.count()} horses")
            
            horse_scores_data = []
            
            for horse in horses:
                try:
                    self.stdout.write(f"🐎 Scoring {horse.horse_name} (#{horse.horse_no})...")
                    
                    # Extract horse data with safe defaults
                    horse_data = {
                        'name': horse.horse_name,
                        'horse_no': horse.horse_no,
                        'rating': self._safe_float(horse.horse_merit),
                        'current_mr': self._safe_float(horse.horse_merit),
                        'best_mr': self._safe_float(horse.best_merit_rating),
                        'speed_rating': self._safe_float(horse.speed_rating),
                        'jt_score': self._safe_float(horse.jt_score),
                        'weight': self._safe_float(horse.weight),
                        'trainer': horse.trainer,
                        'jockey': horse.jockey,
                        'last_races': self._get_horse_last_runs(horse)  # Get recent runs
                    }
                    
                    # Calculate enhanced scores
                    scores = self._calculate_enhanced_scores(horse_data)
                    
                    # Create or update HorseScore
                    horse_score, created = HorseScore.objects.update_or_create(
                        horse=horse,
                        race=race,
                        defaults={
                            'speed_score': scores['speed_score'],
                            'form_score': scores['form_score'],
                            'consistency_score': scores['consistency_score'],
                            'overall_score': scores['composite_score'],
                            'is_maiden': scores['is_maiden'],
                            'current_mr': scores['current_mr'],
                            'best_mr': scores['best_mr'],
                            'rating': scores['rating']
                        }
                    )
                    
                    horse_scores_data.append({
                        'horse': horse,
                        'scores': scores,
                        'horse_score_obj': horse_score
                    })
                    
                    self.stdout.write(
                        f"   ✅ {horse.horse_name}: "
                        f"Composite={scores['composite_score']:.1f}, "
                        f"Speed={scores['speed_score']:.1f}, "
                        f"Form={scores['form_score']:.1f}, "
                        f"Consistency={scores['consistency_score']:.1f}%, "
                        f"Maiden={scores['is_maiden']}"
                    )
                    
                except Exception as e:
                    self.stdout.write(f"   ❌ Error scoring {horse.horse_name}: {e}")
                    continue
            
            # Display rankings
            self._display_enhanced_rankings(race, horse_scores_data)
            
        except Exception as e:
            self.stdout.write(f"❌ Error in enhanced scoring: {e}")
            import traceback
            self.stdout.write(f"Traceback: {traceback.format_exc()}")

    def _calculate_enhanced_scores(self, horse_data):
        """Calculate enhanced scores with robust error handling"""
        try:
            # Safe value extraction
            rating = self._safe_float(horse_data.get('rating'), 0.0)
            current_mr = self._safe_float(horse_data.get('current_mr'), 0.0)
            best_mr = self._safe_float(horse_data.get('best_mr'), 0.0)
            speed_rating = self._safe_float(horse_data.get('speed_rating'), 50.0)
            jt_score = self._safe_float(horse_data.get('jt_score'), 50.0)
            weight = self._safe_float(horse_data.get('weight'), 57.0)
            last_races = horse_data.get('last_races', [])
            
            # 1. Maiden Check (FIXED LOGIC)
            is_maiden = self._is_maiden_horse(best_mr, current_mr)
            
            # 2. Speed Score (combining rating and speed_rating)
            speed_score = self._calculate_speed_score(rating, speed_rating, current_mr)
            
            # 3. Form Score (based on recent runs)
            form_score = self._calculate_form_score(current_mr, last_races)
            
            # 4. Consistency Score
            consistency_score = self._calculate_consistency_score(best_mr, current_mr)
            
            # 5. Jockey-Trainer Score
            jt_adjusted = jt_score * 0.1  # Convert to 0-10 scale
            
            # 6. Weight Adjustment
            weight_adjustment = self._calculate_weight_adjustment(weight)
            
            # Composite Score Calculation
            composite_score = (
                speed_score * 0.35 +        # 35% speed
                form_score * 0.25 +         # 25% recent form  
                consistency_score * 0.20 +  # 20% consistency
                jt_adjusted * 0.15 +        # 15% jockey-trainer
                weight_adjustment * 0.05    # 5% weight
            )
            
            # Maiden penalty
            if is_maiden:
                composite_score *= 0.9  # 10% penalty for maidens
            
            return {
                'composite_score': round(composite_score, 2),
                'speed_score': round(speed_score, 2),
                'form_score': round(form_score, 2),
                'consistency_score': round(consistency_score, 2),
                'is_maiden': is_maiden,
                'current_mr': current_mr,
                'best_mr': best_mr,
                'rating': rating
            }
            
        except Exception as e:
            self.stdout.write(f"❌ Error in score calculation: {e}")
            # Return safe defaults
            return {
                'composite_score': 0.0,
                'speed_score': 0.0,
                'form_score': 0.0,
                'consistency_score': 0.0,
                'is_maiden': True,
                'current_mr': 0.0,
                'best_mr': 0.0,
                'rating': 0.0
            }

    def _is_maiden_horse(self, best_mr, current_mr, winning_threshold=80):
        """ROBUST: Determine if horse is maiden (never won)"""
        try:
            # Handle None values safely
            if best_mr is None:
                return True  # No best MR = maiden
            
            # Convert to float for comparison
            best_mr_safe = float(best_mr) if best_mr is not None else 0.0
            
            # Maiden if best performance never reached winning threshold
            return best_mr_safe < winning_threshold
            
        except (TypeError, ValueError) as e:
            self.stdout.write(f"⚠️ Maiden check error: {e}, defaulting to True")
            return True  # Conservative approach

    def _safe_float(self, value, default=0.0):
        """Safely convert any value to float"""
        try:
            if value is None:
                return default
            return float(value)
        except (TypeError, ValueError):
            return default

    def _calculate_speed_score(self, rating, speed_rating, current_mr):
        """Calculate speed score combining multiple factors"""
        try:
            # Base speed from rating (0-100 scale)
            base_speed = min(rating * 1.5, 100)  # Convert to 0-100 scale
            
            # Speed rating contribution (already 0-100)
            speed_contrib = speed_rating * 0.8  # Weighted contribution
            
            # Current MR contribution
            mr_contrib = min(current_mr * 1.2, 100) * 0.6
            
            # Combined speed score
            speed_score = (base_speed * 0.4) + (speed_contrib * 0.4) + (mr_contrib * 0.2)
            return max(0, min(100, speed_score))
            
        except Exception as e:
            self.stdout.write(f"⚠️ Speed score error: {e}")
            return 50.0  # Default average

    def _calculate_form_score(self, current_mr, last_races):
        """Calculate form score from recent performances"""
        try:
            current_mr_safe = self._safe_float(current_mr)
            
            if not last_races:
                return current_mr_safe * 0.8  # Base on current MR only
            
            # Calculate average of last 3 races
            recent_scores = []
            for race in last_races[:3]:  # Last 3 races
                mr = self._safe_float(race.get('merit_rating', 0))
                if mr > 0:  # Only include valid MRs
                    recent_scores.append(mr)
            
            if recent_scores:
                avg_recent = sum(recent_scores) / len(recent_scores)
                # Weighted: 60% current form, 40% recent average
                form_score = (current_mr_safe * 0.6) + (avg_recent * 0.4)
            else:
                form_score = current_mr_safe * 0.8
                
            return max(0, min(100, form_score))
            
        except Exception as e:
            self.stdout.write(f"⚠️ Form score error: {e}")
            return self._safe_float(current_mr) * 0.8

    def _calculate_consistency_score(self, best_mr, current_mr):
        """Calculate how close current form is to best"""
        try:
            best_mr_safe = self._safe_float(best_mr)
            current_mr_safe = self._safe_float(current_mr)
            
            if best_mr_safe <= 0:
                return 0.0
            
            # Consistency ratio (0-100 scale)
            consistency_ratio = current_mr_safe / best_mr_safe
            consistency_score = min(consistency_ratio, 1.0) * 100
            
            return round(consistency_score, 2)
            
        except Exception as e:
            self.stdout.write(f"⚠️ Consistency score error: {e}")
            return 0.0

    def _calculate_weight_adjustment(self, weight):
        """Calculate weight adjustment factor"""
        try:
            # Normalize weight to 0-100 scale (lighter = better)
            # Assuming typical weight range: 52-65kg
            base_weight = 57.0  # Average weight
            weight_diff = weight - base_weight
            
            # Adjustment: lighter horses get bonus, heavier get penalty
            adjustment = max(0, 100 - (abs(weight_diff) * 10))
            return max(0, min(100, adjustment))
            
        except Exception as e:
            self.stdout.write(f"⚠️ Weight adjustment error: {e}")
            return 50.0

    def _get_horse_last_runs(self, horse):
        """Get last 5 runs for a horse"""
        try:
            from racecard_02.models import Run
            runs = Run.objects.filter(horse=horse).order_by('-run_date')[:5]
            
            run_data = []
            for run in runs:
                run_data.append({
                    'date': run.run_date,
                    'merit_rating': run.merit_rating,
                    'position': run.position,
                    'track': run.track,
                    'distance': run.distance
                })
            
            return run_data
            
        except Exception as e:
            self.stdout.write(f"⚠️ Error getting runs for {horse.horse_name}: {e}")
            return []

    

    # KEEP ALL YOUR EXISTING METHODS BELOW (they remain unchanged)
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

            # ADD THIS LINE:
            self.current_file_path = file_path  # ← This is missing!
            
            # Store the soup as instance variable for run parsing
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
            
            # Calculate scores after all data is imported (NOW USING ENHANCED METHOD)
            for race in races:
                self.stdout.write(f"📊 Calculating ENHANCED scores for Race {race.race_no}...")
                self._calculate_enhanced_horse_scores(race)  # ENHANCED METHOD
            
            return races
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"❌ Error processing file {file_path}: {str(e)}"))
            import traceback
            self.stdout.write(self.style.ERROR(f"Traceback: {traceback.format_exc()}"))
            return []

    # KEEP ALL YOUR EXISTING PARSING METHODS (they remain exactly the same)
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

    # ... [KEEP ALL YOUR EXISTING METHODS EXACTLY AS THEY ARE]
    # _parse_horses, _parse_jockey_trainer_table, analyze_jockey_trainer_combination,
    # _get_jt_rating, _verify_speed_data, parse_horse_runs, 
    # _get_horse_past_performance_compartment, _import_runs_for_all_horses,
    # _extract_magic_tips, calculate_rankings, _test_basic_functionality

    # Just add this one method to maintain compatibility with your existing service calls
    def _calculate_horse_scores(self, race):
        """USE BULLETPROOF ENHANCED SCORING SERVICE"""
        from racecard_02.models import HorseScore
        
        self.stdout.write(f"🎯 BULLETPROOF SCORING for Race {race.race_no}")
        
        # Extract Magic Tips
        magic_tips = self._extract_magic_tips(self.soup)
        self.stdout.write(f"🎯 Magic Tips horses: {magic_tips}")
        
        try:
            # Set Magic Tips in enhanced service
            self.enhanced_scoring_service.set_magic_tips(magic_tips)
            
            # Calculate scores using BULLETPROOF service
            horse_scores_data = self.enhanced_scoring_service.calculate_scores_for_race(race)
            
            if not horse_scores_data:
                self.stdout.write("❌ No horse scores calculated")
                return
            
            # Save to database
            rankings_count = 0
            for score_data in horse_scores_data:
                try:
                    horse = Horse.objects.get(race=race, horse_no=score_data['horse_no'])
                    
                    horse_score, created = HorseScore.objects.update_or_create(
                        horse=horse,
                        race=race,
                        defaults={
                            'speed_score': score_data['speed_score'],
                            'form_score': score_data['form_score'],
                            'consistency_score': score_data['consistency_score'],
                            'overall_score': score_data['composite_score'],
                            'is_maiden': score_data['is_maiden'],
                            'current_mr': score_data['current_mr'],
                            'best_mr': score_data['best_mr'],
                            'rating': score_data['rating']
                        }
                    )
                    rankings_count += 1
                    
                except Exception as e:
                    self.stdout.write(f"❌ Error saving score for {score_data['horse_name']}: {e}")
                    continue
            
            # Display results
            self._display_enhanced_rankings(race, horse_scores_data)
            
        except Exception as e:
            self.stdout.write(f"❌ CRITICAL error in scoring pipeline: {e}")
            import traceback
            self.stdout.write(f"Traceback: {traceback.format_exc()}")

    def _display_enhanced_rankings(self, race, horse_scores_data):
        """Display enhanced rankings"""
        sorted_scores = sorted(horse_scores_data, 
                            key=lambda x: x['composite_score'], 
                            reverse=True)
        
        self.stdout.write(f"\n🏆 BULLETPROOF RANKINGS - Race {race.race_no}")
        self.stdout.write("=" * 90)
        self.stdout.write("Rank  Horse No  Horse Name          Score  Speed  Form   Consist  Maiden")
        self.stdout.write("-" * 90)
        
        for rank, score_data in enumerate(sorted_scores, 1):
            maiden_flag = "✓" if score_data['is_maiden'] else "✗"
            magic_star = "✨" if score_data.get('horse_no') in getattr(self.enhanced_scoring_service, 'magic_tips', []) else ""
            
            self.stdout.write(
                f"{rank:2d}    {score_data['horse_no']:2d}      {score_data['horse_name']:<18}  "
                f"{score_data['composite_score']:>5.1f}  {score_data['speed_score']:>5.1f}  "
                f"{score_data['form_score']:>5.1f}  {score_data['consistency_score']:>7.1f}%  "
                f"{maiden_flag:>6} {magic_star}"
            )
        
        self.stdout.write("=" * 90)
