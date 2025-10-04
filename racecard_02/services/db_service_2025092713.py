# racecard_02/services/db_service.py
import logging
from django.db import transaction

logger = logging.getLogger(__name__)

class DatabaseService:
    """
    Simple database service that works with your existing models
    """
    
    def __init__(self, debug_callback=None):
        self.debug_callback = debug_callback
        self.logger = logging.getLogger(__name__)
    
    def log(self, message):
        """Log message to both logger and debug callback"""
        self.logger.info(message)
        if self.debug_callback:
            self.debug_callback(message)
    
    @transaction.atomic
    def save_rankings(self, race, horse_scores, magic_tips):
        """
        Save rankings to database - with correct data types
        """
        from racecard_02.models import Ranking
        
        self.log(f"    💾 Saving rankings to database for race {race.race_no}...")
        
        try:
            # Clear existing rankings for this race
            deleted_count, _ = Ranking.objects.filter(race=race).delete()
            if deleted_count:
                self.log(f"    🗑️ Cleared {deleted_count} existing rankings")
            
            # Sort by overall_score (descending)
            sorted_scores = sorted(horse_scores, key=lambda x: x.overall_score, reverse=True)
            rankings_created = 0
            
            # Create new rankings with Magic Tips boost
            for rank, score in enumerate(sorted_scores, 1):
                is_magic_tip = score.horse.horse_no in magic_tips
                magic_boost = 100.0 if is_magic_tip else 0.0
                final_score = (score.overall_score * 0.6) + (magic_boost * 0.4)
                
                # Get blinkers value as boolean
                blinkers_bool = getattr(score.horse, 'blinkers', False)
                
                # Create the ranking with correct data types
                ranking = Ranking(
                    race=race,
                    horse=score.horse,
                    rank=rank,
                    overall_score=float(final_score),
                    is_magic_tip=is_magic_tip,
                    magic_tips_boost=float(magic_boost),
                    adjusted_score=float(final_score),
                    
                    # Core scores - float values
                    speed_score=float(getattr(score, 'speed_score', 0.0)),
                    form_score=float(getattr(score, 'form_score', 0.0)),
                    class_score=float(getattr(score, 'class_score', 0.0)),
                    consistency_score=float(getattr(score, 'consistency_score', 0.0)),
                    value_score=float(getattr(score, 'value_score', 0.0)),
                    physical_score=float(getattr(score, 'physical_score', 0.0)),
                    intangible_score=float(getattr(score, 'intangible_score', 0.0)),
                    
                    # Individual parameter scores - float values
                    speed_rating_score=float(getattr(score, 'speed_rating_score', 0.0)),
                    best_mr_score=float(getattr(score, 'best_mr_score', 0.0)),
                    current_mr_score=float(getattr(score, 'current_mr_score', 0.0)),
                    jt_score=float(getattr(score, 'jt_score', 0.0)),
                    odds_score=float(getattr(score, 'odds_score', 0.0)),
                    weight_score=float(getattr(score, 'weight_score', 0.0)),
                    draw_score=float(getattr(score, 'draw_score', 0.0)),
                    blinkers_score=float(getattr(score, 'blinkers_score', 0.0)),  # FLOAT
                    
                    # Raw values - correct data types
                    best_mr_value=float(getattr(score, 'best_mr_value', 0.0)),
                    current_mr_value=float(getattr(score, 'current_mr_value', 0.0)),
                    jt_value=float(getattr(score, 'jt_value', 0.0)),
                    odds_value=float(getattr(score, 'odds_value', 0.0)),
                    weight_value=float(getattr(score, 'weight_value', 0.0)),
                    draw_value=float(getattr(score.horse, 'horse_no', 0)),
                    blinkers_value=blinkers_bool,  # BOOLEAN (True/False)
                )
                ranking.save()
                rankings_created += 1
                
                if is_magic_tip:
                    self.log(f"    ✨ Magic Tip #{rank}: {score.horse.horse_name} = {final_score:.1f}")
            
            self.log(f"    ✅ Saved {rankings_created} rankings to database!")
            return rankings_created
            
        except Exception as e:
            self.log(f"    ❌ Error saving rankings to database: {e}")
            import traceback
            self.log(f"    Traceback: {traceback.format_exc()}")
            raise
    
    def get_race_rankings(self, race):
        """Get rankings for a specific race"""
        from racecard_02.models import Ranking
        return Ranking.objects.filter(race=race).select_related('horse').order_by('rank')
    
    def display_rankings(self, race):
        """Display rankings in your preferred format"""
        rankings = self.get_race_rankings(race)
        
        if not rankings.exists():
            self.log("    ⚠️ No rankings found in database")
            return
        
        self.log(f"\n🏆 DATABASE RANKINGS - Race {race.race_no}")
        self.log("="*70)
        self.log("Rank  Horse No  Horse Name          Score  Magic Tip")
        self.log("-"*70)
        
        for ranking in rankings:
            star = "✨" if ranking.is_magic_tip else ""
            self.log(f"{ranking.rank:2d}    {ranking.horse.horse_no:2d}      {ranking.horse.horse_name:<18}  {ranking.adjusted_score:5.1f}  {star}")
        
        self.log("="*70)
        
        # Show Magic Tips summary
        magic_tips_count = rankings.filter(is_magic_tip=True).count()
        self.log(f"🎯 Magic Tips applied to {magic_tips_count} horses (40% boost)")