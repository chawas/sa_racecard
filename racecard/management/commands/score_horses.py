from django.core.management.base import BaseCommand
from racecard.models4 import Horse, Run, RankedHorse

def class_score(class_str):
    class_map = {
        "FM": 1, "MP": 2, "MR": 2,
        "WrkR": 3, "Clss": 4,
        "SCC": 5, "Nov": 6,
    }
    for key, val in class_map.items():
        if key.lower() in class_str.lower():
            return val
    return 7

def comment_score(comment):
    if not comment:
        return 0
    comment = comment.lower()
    pos_keywords = ['ran on', 'prominent', 'stayed on', 'flew up', 'strong']
    neg_keywords = ['lacked', 'never', 'green', 'no threat', 'pulled']
    score = 0
    for word in pos_keywords:
        if word in comment:
            score += 1
    for word in neg_keywords:
        if word in comment:
            score -= 1
    return score

class Command(BaseCommand):
    help = "Compute scores and populate RankedHorse table"

    def handle(self, *args, **kwargs):
        RankedHorse.objects.all().delete()
        horses = Horse.objects.all()
        print(f"Scoring {horses.count()} horses...")

        for horse in horses:
            runs = horse.runs.order_by('-date')[:4]
            if not runs:
                continue

            avg_pos = sum(r.position_num for r in runs) / len(runs)
            avg_class = sum(class_score(r.race_class) for r in runs) / len(runs)
            avg_comment = sum(comment_score(r.comment) for r in runs) / len(runs)
            merit = horse.merit or 0

            score = (
                (100 - avg_pos * 10) +      # lower avg_pos is better
                (50 - avg_class * 5) +      # lower class score is better
                merit +                     # high merit is better
                (avg_comment * 2)           # more positive comments
            )

            RankedHorse.objects.create(
                horse=horse,
                score=score,
                avg_position=avg_pos,
                merit=merit,
                class_score=avg_class,
                comment_strength=avg_comment
            )

            print(f"[✅] Ranked: {horse.name} — Score: {score:.2f}")

        print("🎯 Ranking complete.")
