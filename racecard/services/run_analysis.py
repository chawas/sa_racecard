import re
from datetime import datetime, timedelta
from django.utils import timezone

class RunAnalysisService:
    
    def __init__(self):
        pass
    
    def analyze_horse_runs(self, horse):
        """Analyze a horse's past runs with detailed performance metrics"""
        from racecard.models import Run
        
        runs = Run.objects.filter(horse=horse).order_by('-run_date')[:4]
        
        if not runs:
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
                pos = float(run.position) if run.position and run.position.isdigit() else None
                if pos:
                    positions.append(pos)
                    performance_scores.append(self._calculate_performance_score(pos))
            except:
                pass
            
            # Margin analysis
            if run.margin:
                margin = self._parse_margin(run.margin)
                if margin is not None:
                    margins.append(margin)
            
            # Distance analysis
            if run.distance:
                try:
                    distance = int(re.search(r'\d+', run.distance).group())
                    distances.append(distance)
                except:
                    pass
            
            # Class analysis
            if run.race_class:
                from .class_analysis import ClassAnalysisService
                class_service = ClassAnalysisService()
                weight = class_service.get_class_weight(run.race_class)
                class_weights.append(weight)
            
            # Days since run
            if run.run_date:
                days = (current_date - run.run_date).days
                days_since.append(days)
        
        return {
            'average_position': sum(positions)/len(positions) if positions else None,
            'average_margin': sum(margins)/len(margins) if margins else None,
            'recent_distance': max(set(distances), key=distances.count) if distances else None,
            'average_class': sum(class_weights)/len(class_weights) if class_weights else None,
            'days_since_last_run': min(days_since) if days_since else None,
            'form_rating': self._calculate_form_rating(positions),
            'consistency': self._calculate_consistency(positions),
            'performance_trend': self._calculate_performance_trend(performance_scores),
            'runs_analyzed': len(runs)
        }
    
    def _calculate_performance_score(self, position):
        """Calculate performance score (1st=100, 2nd=80, etc.)"""
        return max(0, 100 - (position * 20))
    
    def _parse_margin(self, margin_text):
        """Parse margin text into numeric value"""
        try:
            if margin_text in ['DH', 'HD', 'SH']:  # Dead heat, head, short head
                return 0.1
            elif margin_text == 'NSE':  # Nose
                return 0.05
            else:
                # Try to parse numeric margin
                return float(margin_text)
        except:
            return None
    
    def _calculate_form_rating(self, positions):
        """Calculate form rating with recent runs weighted more heavily"""
        if not positions:
            return 0
        
        weighted_sum = 0
        total_weight = 0
        
        for i, pos in enumerate(positions):
            weight = 0.8 ** i  # Recent runs have higher weight
            weighted_sum += pos * weight
            total_weight += weight
        
        return weighted_sum / total_weight
    
    def _calculate_consistency(self, positions):
        """Calculate consistency percentage"""
        if not positions or len(positions) < 2:
            return 0
        
        avg_position = sum(positions) / len(positions)
        within_range = sum(1 for p in positions if abs(p - avg_position) <= 2)
        
        return (within_range / len(positions)) * 100
    
    def _calculate_performance_trend(self, performance_scores):
        """Calculate performance trend (improving/declining)"""
        if not performance_scores or len(performance_scores) < 2:
            return "stable"
        
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
            'runs_analyzed': 0
        }