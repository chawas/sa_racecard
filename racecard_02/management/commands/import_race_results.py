# management/commands/import_race_results.py
class Command(BaseCommand):
    
    def _calculate_performance_metrics(self, race_result, horse_result, position_data):
        """Calculate advanced performance metrics"""
        # Calculate speed rating (time relative to winner)
        if race_result.winning_time and horse_result.finish_time:
            horse_result.speed_rating = (race_result.winning_time / horse_result.finish_time) * 100
        
        # Calculate pace rating (position at various stages - would need more data)
        # For now, use final position relative to field size
        if race_result.total_runners:
            horse_result.pace_rating = (1 - (horse_result.official_position / race_result.total_runners)) * 100
        
        # Calculate finish rating (based on beaten lengths)
        if horse_result.beaten_lengths is not None:
            # Assuming 1 length ≈ 0.2 seconds
            time_behind = horse_result.beaten_lengths * 0.2
            if race_result.winning_time:
                horse_result.finish_rating = 100 - (time_behind / race_result.winning_time * 100)
    
    def _parse_results(self, soup):
        """Enhanced parsing with performance data"""
        results = []
        result_rows = soup.find_all('tr', class_='result-row')
        
        for row in result_rows:
            try:
                cells = row.find_all('td')
                if len(cells) >= 6:
                    result_data = {
                        'position': int(cells[0].get_text(strip=True)),
                        'horse_number': int(cells[1].get_text(strip=True)),
                        'margin': cells[2].get_text(strip=True),
                        'time': self._parse_time(cells[3].get_text(strip=True)),
                        'beaten_lengths': self._parse_beaten_lengths(cells[2].get_text(strip=True)),
                        'price': self._parse_price(cells[5].get_text(strip=True)),
                    }
                    results.append(result_data)
            except Exception as e:
                self.stdout.write(self.style.WARNING(f"⚠️ Error parsing result row: {e}"))
        
        return results