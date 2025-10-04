# racecard_02/services/db_service.py
from django.utils import timezone
from racecard_02.models import Ranking, HorseScore, Horse

class DatabaseService:
    def __init__(self, debug_callback=None):
        self.debug_callback = debug_callback if debug_callback else print
    
    def _debug(self, message):
        """Safe debug output"""
        try:
            self.debug_callback(message)
        except:
            print(message)
    
    def save_rankings(self, race, horse_scores, magic_tips=None):
        """Save rankings to database with PROPER ranking logic"""
        try:
            self._debug(f"💾 Saving rankings for Race {race.race_no}...")
            
            if not horse_scores:
                self._debug("❌ No horse scores to save")
                return 0
            
            # Handle both dictionaries and model objects
            def get_score_value(score_obj):
                """Safely extract score value from either dict or model object"""
                if isinstance(score_obj, dict):
                    return score_obj.get('composite_score', 0)
                else:
                    return getattr(score_obj, 'overall_score', 0)
            
            def get_horse_from_score(score_obj):
                """Safely extract horse from either dict or model object"""
                if isinstance(score_obj, dict):
                    horse_no = score_obj.get('horse_no')
                    if horse_no:
                        try:
                            return Horse.objects.get(race=race, horse_no=horse_no)
                        except Horse.DoesNotExist:
                            return None
                else:
                    return getattr(score_obj, 'horse', None)
            
            # First, apply Magic Tips boost and create a list with final scores
            magic_tips = magic_tips or []
            ranked_horses = []
            
            for score_data in horse_scores:
                try:
                    horse = get_horse_from_score(score_data)
                    if not horse:
                        continue
                    
                    # Get base score value
                    base_score = get_score_value(score_data)
                    
                    # Check if magic tip
                    is_magic_tip = horse.horse_no in magic_tips
                    
                    # Apply magic tip boost (60% base score + 40% of 100)
                    final_score = base_score
                    if is_magic_tip:
                        final_score = (base_score * 0.6) + (100 * 0.4)
                        self._debug(f"✨ Magic Tips boost: {horse.horse_name} {base_score:.1f} → {final_score:.1f}")
                    
                    ranked_horses.append({
                        'horse': horse,
                        'base_score': base_score,
                        'final_score': final_score,
                        'is_magic_tip': is_magic_tip,
                        'score_data': score_data
                    })
                    
                except Exception as e:
                    self._debug(f"❌ Error processing horse for ranking: {e}")
                    continue
            
            # NOW sort by final_score (after applying all boosts)
            ranked_horses.sort(key=lambda x: x['final_score'], reverse=True)
            
            rankings_created = 0
            
            for rank, horse_data in enumerate(ranked_horses, 1):
                try:
                    horse = horse_data['horse']
                    final_score = horse_data['final_score']
                    base_score = horse_data['base_score']
                    is_magic_tip = horse_data['is_magic_tip']
                    
                    # Create or update ranking - using only fields that exist in Ranking model
                    ranking_defaults = {
                        'rank': rank,
                        'is_magic_tip': is_magic_tip,
                        'calculated_at': timezone.now(),
                    }
                    
                    # Add score field only if it exists in the model
                    if hasattr(Ranking, 'score'):
                        ranking_defaults['score'] = final_score
                    elif hasattr(Ranking, 'overall_score'):
                        ranking_defaults['overall_score'] = final_score
                    
                    ranking, created = Ranking.objects.update_or_create(
                        race=race,
                        horse=horse,
                        defaults=ranking_defaults
                    )
                    
                    rankings_created += 1
                    status = "Created" if created else "Updated"
                    
                    # Show the transformation for Magic Tips horses
                    if is_magic_tip:
                        self._debug(f"   {status} ranking: {rank}. {horse.horse_name} - Base: {base_score:.1f} → Final: {final_score:.1f} ✨")
                    else:
                        self._debug(f"   {status} ranking: {rank}. {horse.horse_name} - Score: {final_score:.1f}")
                    
                except Exception as e:
                    self._debug(f"❌ Error saving ranking for position {rank}: {e}")
                    continue
            
            self._debug(f"✅ Successfully saved {rankings_created} rankings for Race {race.race_no}")
            return rankings_created
            
        except Exception as e:
            self._debug(f"❌ Error saving rankings to database: {e}")
            import traceback
            self._debug(f"Traceback: {traceback.format_exc()}")
            return 0
    
    def display_rankings(self, race):
        """Display rankings from database"""
        try:
            rankings = Ranking.objects.filter(race=race).select_related('horse').order_by('rank')
            
            self._debug(f"\n🏆 FINAL RANKINGS - Race {race.race_no}")
            self._debug("=" * 70)
            
            # Display based on available score field
            if hasattr(Ranking, 'score'):
                self._debug("Rank  Horse No  Horse Name          Score  Magic Tip")
                self._debug("-" * 70)
                for ranking in rankings:
                    magic_star = "✨" if ranking.is_magic_tip else ""
                    self._debug(
                        f"{ranking.rank:2d}    {ranking.horse.horse_no:2d}      "
                        f"{ranking.horse.horse_name:<18}  {ranking.score:>5.1f}  {magic_star}"
                    )
            elif hasattr(Ranking, 'overall_score'):
                self._debug("Rank  Horse No  Horse Name          Overall Score  Magic Tip")
                self._debug("-" * 70)
                for ranking in rankings:
                    magic_star = "✨" if ranking.is_magic_tip else ""
                    self._debug(
                        f"{ranking.rank:2d}    {ranking.horse.horse_no:2d}      "
                        f"{ranking.horse.horse_name:<18}  {ranking.overall_score:>12.1f}  {magic_star}"
                    )
            else:
                self._debug("Rank  Horse No  Horse Name          Magic Tip")
                self._debug("-" * 70)
                for ranking in rankings:
                    magic_star = "✨" if ranking.is_magic_tip else ""
                    self._debug(
                        f"{ranking.rank:2d}    {ranking.horse.horse_no:2d}      "
                        f"{ranking.horse.horse_name:<18}  {magic_star}"
                    )
            
            self._debug("=" * 70)
            
        except Exception as e:
            self._debug(f"❌ Error displaying rankings: {e}")