import logging
from typing import Dict, List
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from races.models import Race, Horse
from rankings.models import HorseScore
from scoring.services.scoring_services import HorseScoringService

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Analyze and score horses for races'
    
    def add_arguments(self, parser):
        parser.add_argument('--race-id', type=int, help='Process specific race')
        parser.add_argument('--venue', type=str, help='Process specific venue')
        parser.add_argument('--debug', action='store_true', help='Enable debug')

    def handle(self, *args, **options):
        self.debug_mode = options.get('debug', False)
        self.stdout.write("🏇 Starting horse scoring analysis...")
        
        races = self._get_races_to_process(options)
        self.stdout.write(f"Found {races.count()} races to process")
        
        total_processed = 0
        for race in races:
            try:
                self.stdout.write(f"\n🎯 Processing Race {race.race_no} at {race.venue}")
                processed = self._calculate_horse_scores(race)
                total_processed += processed
            except Exception as e:
                self.stdout.write(self.style.ERROR(f"❌ Error processing race: {e}"))
                logger.error(f"Error processing race {race.id}: {e}")

        self.stdout.write(f"\n✅ Complete! Processed {total_processed} horses")

    def _get_races_to_process(self, options):
        today = timezone.now().date()
        if options.get('race_id'):
            return Race.objects.filter(id=options['race_id'])
        elif options.get('venue'):
            return Race.objects.filter(venue=options['venue'], race_date=today)
        else:
            return Race.objects.filter(race_date=today)

    def _calculate_horse_scores(self, race: Race) -> int:
        self.stdout.write(f"\n📊 Calculating scores for Race {race.race_no}...")
        
        horses = Horse.objects.filter(race=race).select_related('jockey', 'trainer')
        self.stdout.write(f"Found {horses.count()} horses")
        
        if not horses.exists():
            self.stdout.write("❌ No horses found")
            return 0
        
        scores_data = []
        
        for horse in horses:
            try:
                self.stdout.write(f"\n🐎 Processing {horse.horse_name} (No. {horse.horse_no})...")
                
                # Use the proper HorseScoringService
                scoring_service = HorseScoringService(horse, race, self.stdout.write)
                score_record, created = scoring_service.create_score_record()
                
                status = "Created" if created else "Updated"
                self.stdout.write(f"✅ {status} score: {score_record.overall_score:.2f}")
                
                scores_data.append({
                    'horse': horse,
                    'score_record': score_record,
                    'overall_score': score_record.overall_score
                })
                
            except Exception as e:
                self.stdout.write(f"❌ Error scoring {horse.horse_name}: {e}")
                continue
        
        # Save rankings
        if scores_data:
            self._save_rankings(scores_data, race)
            return len(scores_data)
        return 0

    def _save_rankings(self, scores_data: List[Dict], race: Race):
        """Save ranking positions"""
        try:
            sorted_scores = sorted(scores_data, key=lambda x: x['overall_score'], reverse=True)
            
            with transaction.atomic():
                for position, data in enumerate(sorted_scores, 1):
                    score_record = data['score_record']
                    score_record.ranking_position = position
                    score_record.save()
            
            self.stdout.write(f"✅ Saved rankings for {len(sorted_scores)} horses")
            
        except Exception as e:
            self.stdout.write(f"❌ Error saving rankings: {e}")