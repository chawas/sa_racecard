import re
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q

class RunAnalysisService:
    
    def __init__(self):
        pass
    
    import re
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q

class RunAnalysisService:
    
    def __init__(self):
        pass
    
    def analyze_horse_runs(self, horse):
        """Analyze a horse's past runs with detailed performance metrics"""
        from racecard_02.models import Run
        
        # DEBUG: Check what type of object we're receiving
        print(f"DEBUG: analyze_horse_runs received: {type(horse)} - {horse}")
        
        # For Run model with horse ForeignKey, we need to filter by the horse object
        # or by the horse's name through the relationship
        try:
            # If we have a Horse object with ID, query directly
            if hasattr(horse, 'id') and horse.id:
                runs = Run.objects.filter(horse=horse).order_by('-run_date')[:10]
                print(f"DEBUG: Querying runs by horse object ID: {horse.id}")
            else:
                # If we have a horse name, try to find the horse first
                if hasattr(horse, 'horse_name'):
                    horse_name = horse.horse_name
                else:
                    horse_name = str(horse)
                
                print(f"DEBUG: Looking up horse by name: {horse_name}")
                from racecard_02.models import Horse
                try:
                    horse_obj = Horse.objects.get(horse_name=horse_name)
                    runs = Run.objects.filter(horse=horse_obj).order_by('-run_date')[:10]
                    print(f"DEBUG: Found horse object, querying runs by horse ID: {horse_obj.id}")
                except Horse.DoesNotExist:
                    print(f"DEBUG: Horse not found by name: {horse_name}")
                    return self._get_empty_analysis()
                except Horse.MultipleObjectsReturned:
                    print(f"DEBUG: Multiple horses found with name: {horse_name}")
                    horse_obj = Horse.objects.filter(horse_name=horse_name).first()
                    runs = Run.objects.filter(horse=horse_obj).order_by('-run_date')[:10]
        
        except Exception as e:
            print(f"DEBUG: Error querying runs: {e}")
            return self._get_empty_analysis()
        
        print(f"DEBUG: Found {runs.count()} runs for horse")
        
        if not runs:
            print(f"DEBUG: No runs found for horse")
            return self._get_empty_analysis()
        
        positions = []
        margins = []
        distances = []
        class_weights = []
        days_since = []
        performance_scores = []
        
        current_date = timezone.now().date()
        
        for run in runs:
            # Position analysis
            try:
                if run.position:
                    # Handle both string and numeric positions
                    if isinstance(run.position, str) and run.position.isdigit():
                        pos = float(run.position)
                    elif isinstance(run.position, (int, float)):
                        pos = float(run.position)
                    else:
                        pos = None
                    
                    if pos:
                        positions.append(pos)
                        performance_scores.append(self._calculate_performance_score(pos))
            except Exception as e:
                print(f"DEBUG: Error parsing position {run.position}: {e}")
                pass
            
            # Margin analysis
            if run.margin:
                margin = self._parse_margin(run.margin)
                if margin is not None:
                    margins.append(margin)
            
            # Distance analysis
            if run.distance:
                try:
                    # Extract numeric distance from string (e.g., "1200m" -> 1200)
                    distance_match = re.search(r'\d+', str(run.distance))
                    if distance_match:
                        distance = int(distance_match.group())
                        distances.append(distance)
                except Exception as e:
                    print(f"DEBUG: Error parsing distance {run.distance}: {e}")
                    pass
            
            # Class analysis (if race_class field exists)
            if hasattr(run, 'race_class') and run.race_class:
                try:
                    # Check if class_analysis exists, otherwise use simple weighting
                    try:
                        from .class_analysis import ClassAnalysisService
                        class_service = ClassAnalysisService()
                        weight = class_service.get_class_weight(run.race_class)
                    except:
                        # Fallback: simple class weighting
                        weight = self._simple_class_weight(run.race_class)
                    
                    class_weights.append(weight)
                except Exception as e:
                    print(f"DEBUG: Error in class analysis: {e}")
                    pass
            
            # Days since run
            if run.run_date:
                try:
                    days = (current_date - run.run_date).days
                    days_since.append(days)
                except Exception as e:
                    print(f"DEBUG: Error calculating days since run: {e}")
                    pass
        
        analysis_result = {
            'average_position': sum(positions)/len(positions) if positions else None,
            'average_margin': sum(margins)/len(margins) if margins else None,
            'recent_distance': max(set(distances), key=distances.count) if distances else None,
            'average_class': sum(class_weights)/len(class_weights) if class_weights else None,
            'days_since_last_run': min(days_since) if days_since else None,
            'form_rating': self._calculate_form_rating(positions),
            'consistency': self._calculate_consistency(positions),
            'performance_trend': self._calculate_performance_trend(performance_scores),
            'runs_analyzed': len(runs),
            'horse_id': horse.id if hasattr(horse, 'id') else None
        }
        
        print(f"DEBUG: Analysis result: {analysis_result}")
        return analysis_result
    
    def _simple_class_weight(self, race_class):
        """Simple fallback for class weighting"""
        if not race_class:
            return 50
        
        try:
            # Extract numeric part from class (e.g., "Class 5" -> 5)
            class_match = re.search(r'\d+', str(race_class))
            if class_match:
                class_num = int(class_match.group())
                return max(10, 100 - (class_num * 10))  # Class 1 = 90, Class 5 = 50, etc.
            else:
                # Weight based on class text
                class_text = str(race_class).upper()
                if 'MAIDEN' in class_text:
                    return 30
                elif 'CLASS 1' in class_text or 'LISTED' in class_text:
                    return 80
                elif 'CLASS 2' in class_text:
                    return 70
                elif 'CLASS 3' in class_text:
                    return 60
                elif 'CLASS 4' in class_text:
                    return 50
                elif 'CLASS 5' in class_text:
                    return 40
                else:
                    return 50
        except:
            return 50
    
    # Keep the rest of the methods unchanged (_calculate_performance_score, _parse_margin, etc.)
    # ... [rest of the methods from previous version] ...
    
    def _calculate_performance_score(self, position):
        """Calculate performance score (1st=100, 2nd=80, etc.)"""
        try:
            return max(0, 100 - (position * 20))
        except:
            return 50  # Default score if calculation fails
    
    def _parse_margin(self, margin_text):
        """Parse margin text into numeric value"""
        if not margin_text:
            return None
            
        try:
            margin_text = str(margin_text).strip().upper()
            
            if margin_text in ['DH', 'DEAD HEAT']:  # Dead heat
                return 0.0
            elif margin_text in ['HD', 'HEAD']:  # Head
                return 0.2
            elif margin_text in ['SH', 'SHORT HEAD']:  # Short head
                return 0.1
            elif margin_text in ['NSE', 'NOSE']:  # Nose
                return 0.05
            elif margin_text in ['DIST', 'DISTANCE']:  # Distance
                return 10.0
            else:
                # Try to parse numeric margin (e.g., "1.5", "2.25L")
                margin_text = re.sub(r'[^\d.]', '', margin_text)  # Remove non-numeric characters
                if margin_text:
                    return float(margin_text)
                else:
                    return None
        except:
            return None
    
    def _calculate_form_rating(self, positions):
        """Calculate form rating with recent runs weighted more heavily"""
        if not positions:
            return 0
        
        try:
            weighted_sum = 0
            total_weight = 0
            
            for i, pos in enumerate(positions):
                weight = 0.8 ** i  # Recent runs have higher weight
                weighted_sum += pos * weight
                total_weight += weight
            
            return weighted_sum / total_weight
        except:
            return sum(positions) / len(positions) if positions else 0
    
    def _calculate_consistency(self, positions):
        """Calculate consistency percentage"""
        if not positions or len(positions) < 2:
            return 0
        
        try:
            avg_position = sum(positions) / len(positions)
            within_range = sum(1 for p in positions if abs(p - avg_position) <= 2)
            
            return (within_range / len(positions)) * 100
        except:
            return 0
    
    def _calculate_performance_trend(self, performance_scores):
        """Calculate performance trend (improving/declining)"""
        if not performance_scores or len(performance_scores) < 2:
            return "stable"
        
        try:
            recent = performance_scores[0]
            previous = sum(performance_scores[1:]) / len(performance_scores[1:])
            
            if recent > previous + 15:
                return "improving_strong"
            elif recent > previous + 5:
                return "improving"
            elif recent < previous - 15:
                return "declining_strong"
            elif recent < previous - 5:
                return "declining"
            else:
                return "stable"
        except:
            return "stable"
    
    def _get_empty_analysis(self):
        return {
            'average_position': None,
            'average_margin': None,
            'recent_distance': None,
            'average_class': None,
            'days_since_last_run': None,
            'form_rating': 0,
            'consistency': 0,
            'performance_trend': "stable",
            'runs_analyzed': 0,
            'horse_name': "unknown"
        }
    

