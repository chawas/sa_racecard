from django.core.management.base import BaseCommand
from bs4 import BeautifulSoup
import re
from datetime import datetime
from pathlib import Path
from tabulate import tabulate

class Command(BaseCommand):
    help = 'Parse horse racing HTML data and display as formatted table using tabulate'

    def add_arguments(self, parser):
        parser.add_argument(
            'filename',
            nargs='?',
            type=str,
            help='Path to HTML file to parse',
            default='racing_data.html'
        )
        parser.add_argument(
            '--view',
            type=str,
            choices=['compact', 'detailed', 'raw', 'all'],
            default='compact',
            help='Display format: compact, detailed, raw, or all'
        )
        parser.add_argument(
            '--output',
            type=str,
            choices=['table', 'grid', 'simple', 'fancy_grid'],
            default='grid',
            help='Table format: table, grid, simple, fancy_grid'
        )

    def parse_racing_html(self, html_content, verbosity=1):
        """
        Parses the horse racing HTML content and returns structured data.
        """
        if verbosity >= 2:
            self.stdout.write("Parsing HTML content...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all('tr', class_='small')
        
        parsed_runs = []
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 21:
                continue
                
            try:
                # Column 0: Date & Days
                days_date_str = cells[0].get_text(strip=True)
                match = re.match(r'\((\d+)\)\s*(\d{2}\.\d{2}\.\d{2})', days_date_str)
                if match:
                    days_since_last_run = match.group(1)
                    raw_date = match.group(2)
                    # Convert date from YY.MM.DD to YYYY-MM-DD
                    try:
                        run_date = datetime.strptime(raw_date, '%y.%m.%d').strftime('%Y-%m-%d')
                    except ValueError:
                        run_date = raw_date
                else:
                    days_since_last_run = None
                    run_date = days_date_str


                # Column 3: Race Class
                race_class = cells[1].get_text(strip=True)
                # Column 1: Track Condition

                going = cells[2].get_text(strip=True)
                
                # Column 2: Race Number
                race_number = cells[3].get_text(strip=True)
                
                
                
                # Column 4: Track Name
                track = cells[4].get_text(strip=True)
                
                # Column 6: Distance
                distance = cells[6].get_text(strip=True)
                
                # Column 7: Jockey
                jockey = cells[7].get_text(strip=True)
                
                # Column 8: Weight
                weight = cells[8].get_text(strip=True)
                
                # Column 9: Merit Rating
                merit_rating = cells[9].get_text(strip=True).strip('()')
                
                # Column 10: Equipment
                equipment = cells[10].get_text(strip=True)
                
                # Column 11: Draw and Field Size
                draw_info = cells[11].get_text(strip=True)
                if '-' in draw_info:
                    draw, field_size = draw_info.split('-')
                else:
                    draw, field_size = None, None
                
                # Column 12: Finishing Position
                position = cells[12].get_text(strip=True)
                
                # Column 13: Lengths Behind
                margin = cells[13].get_text(strip=True)
                
                # Column 15: Time
                time_seconds = cells[15].get_text(strip=True)
                
                # Column 16: Speed Figure
                speed_figure = cells[16].get_text(strip=True)
                
                # Column 17: Starting Price
                sp_price = cells[17].get_text(strip=True)
                
                # Column 20: Comment
                comment = cells[20].get_text(strip=True) if len(cells) > 20 else ""

                run_data = {
                    'date': run_date,
                    'days': days_since_last_run,
                    'track': track,
                    'going': going,
                    'class': race_class,
                    'distance': distance,
                    'position': position,
                    'lengths': margin,
                    'weight': weight,
                    'mr': merit_rating,
                    'jockey': jockey,
                    'draw': draw,
                    'field_size': field_size,
                    'time': time_seconds,
                    'sp': sp_price,
                    'comment': comment
                }
                
                parsed_runs.append(run_data)
                
            except IndexError as e:
                if verbosity >= 1:
                    self.stderr.write(f"Index error parsing row: {e}")
                continue
            except Exception as e:
                if verbosity >= 1:
                    self.stderr.write(f"Error parsing row: {e}")
                continue
        
        return parsed_runs

    def display_compact_table(self, parsed_runs, table_format='grid'):
        """
        Display a compact table view using tabulate.
        """
        if not parsed_runs:
            self.stdout.write("No data to display.")
            return
        
        # Prepare data for tabulate
        headers = ['Date', 'Class', 'Race No', 'Track', 'Dist', 'Pos', 'Len', 'Wgt', 'MR', 'Jockey', 'Draw', 'SP']
        table_data = []
        
        for run in parsed_runs:
            row = [
                run['date'],
                run['track'],
                run['going'],
                run['class'],
                run['distance'],
                run['position'],
                run['lengths'],
                run['weight'],
                run['mr'],
                run['jockey'],
                f"{run['draw']}/{run['field_size']}" if run['draw'] and run['field_size'] else '-',
                run['sp']
            ]
            table_data.append(row)
        
        # Display the table
        self.stdout.write("\n" + "=" * 120)
        self.stdout.write("HORSE RACING PAST PERFORMANCES - COMPACT VIEW")
        self.stdout.write("=" * 120)
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt=table_format, stralign='left'))
        self.stdout.write(f"\nTotal runs parsed: {len(parsed_runs)}")

    def display_detailed_table(self, parsed_runs, table_format='grid'):
        """
        Display a more detailed table view.
        """
        if not parsed_runs:
            self.stdout.write("No data to display.")
            return
        
        headers = ['Date', 'Days', 'Track', 'Going', 'Class', 'Dist', 'Pos', 'Len', 'Wgt', 'MR', 'Jockey', 'Draw', 'Time', 'SP', 'Comment']
        table_data = []
        
        for run in parsed_runs:
            # Truncate long comments
            comment = run['comment']
            if len(comment) > 30:
                comment = comment[:27] + '...'
            
            row = [
                run['date'],
                run['days'],
                run['track'],
                run['going'],
                run['class'],
                run['distance'],
                run['position'],
                run['lengths'],
                run['weight'],
                run['mr'],
                run['jockey'],
                f"{run['draw']}/{run['field_size']}" if run['draw'] and run['field_size'] else '-',
                run['time'],
                run['sp'],
                comment
            ]
            table_data.append(row)
        
        self.stdout.write("\n" + "=" * 150)
        self.stdout.write("HORSE RACING PAST PERFORMANCES - DETAILED VIEW")
        self.stdout.write("=" * 150)
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt=table_format, stralign='left'))
        self.stdout.write(f"\nTotal runs parsed: {len(parsed_runs)}")

    def display_raw_data(self, parsed_runs):
        """
        Display raw parsed data for debugging.
        """
        self.stdout.write("\n" + "=" * 80)
        self.stdout.write("RAW PARSED DATA (FOR DEBUGGING)")
        self.stdout.write("=" * 80)
        
        for i, run in enumerate(parsed_runs, 1):
            self.stdout.write(f"\n--- Run {i} ---")
            for key, value in run.items():
                self.stdout.write(f"  {key:12}: {value}")

    def handle(self, *args, **options):
        filename = options['filename']
        view_type = options['view']
        table_format = options['output']
        verbosity = options.get('verbosity', 1)
        
        # Check if file exists
        if not Path(filename).exists():
            self.stderr.write(f"Error: File '{filename}' not found.")
            self.stdout.write("Please provide a valid HTML file path")
            return
        
        try:
            if verbosity >= 2:
                self.stdout.write(f"Reading from file: {filename}")
            with open(filename, 'r', encoding='utf-8') as file:
                html_content = file.read()
        except Exception as e:
            self.stderr.write(f"Error reading file: {e}")
            return
        
        # Parse the HTML
        parsed_data = self.parse_racing_html(html_content, verbosity)
        
        if not parsed_data:
            self.stdout.write("No data was parsed. Check the HTML file content.")
            return
        
        if verbosity >= 1:
            self.stdout.write(f"Successfully parsed {len(parsed_data)} runs!")
        
        # Display based on chosen view
        if view_type == 'compact':
            self.display_compact_table(parsed_data, table_format)
        elif view_type == 'detailed':
            self.display_detailed_table(parsed_data, table_format)
        elif view_type == 'raw':
            self.display_raw_data(parsed_data)
        elif view_type == 'all':
            self.display_compact_table(parsed_data, table_format)
            self.display_detailed_table(parsed_data, table_format)
            self.display_raw_data(parsed_data)



    def parse_horse_runs(self, html_content, horse_name, verbosity=1):
        """
        Parses the horse racing HTML content and returns structured data for runs.
        (Using the proven method from the working script)
        """
        if verbosity >= 2:
            self.stdout.write(f"Parsing runs for {horse_name}...")
        
        soup = BeautifulSoup(html_content, 'html.parser')
        rows = soup.find_all('tr', class_='small')
        
        parsed_runs = []
        
        for row in rows:
            cells = row.find_all('td')
            if len(cells) < 21:
                continue
                
            try:
                # Column 0: Date & Days
                days_date_str = cells[0].get_text(strip=True)
                match = re.match(r'\((\d+)\)\s*(\d{2}\.\d{2}\.\d{2})', days_date_str)
                if match:
                    days_since_last_run = match.group(1)
                    raw_date = match.group(2)
                    # Convert date from YY.MM.DD to YYYY-MM-DD
                    try:
                        run_date = datetime.strptime(raw_date, '%y.%m.%d').strftime('%Y-%m-%d')
                    except ValueError:
                        run_date = raw_date
                else:
                    days_since_last_run = None
                    run_date = days_date_str

                # Column 3: Race Class
                race_class = cells[1].get_text(strip=True)
                
                # Column 1: Track Condition
                going = cells[2].get_text(strip=True)
                
                # Column 2: Race Number
                race_number = cells[3].get_text(strip=True)
                
                # Column 4: Track Name
                track = cells[4].get_text(strip=True)
                
                # Column 6: Distance
                distance = cells[6].get_text(strip=True)
                
                # Column 7: Jockey
                jockey = cells[7].get_text(strip=True)
                
                # Column 8: Weight
                weight = cells[8].get_text(strip=True)
                
                # Column 9: Merit Rating
                merit_rating = cells[9].get_text(strip=True).strip('()')
                
                # Column 10: Equipment
                equipment = cells[10].get_text(strip=True)
                
                # Column 11: Draw and Field Size
                draw_info = cells[11].get_text(strip=True)
                if '-' in draw_info:
                    draw, field_size = draw_info.split('-')
                else:
                    draw, field_size = None, None
                
                # Column 12: Finishing Position
                position = cells[12].get_text(strip=True)
                
                # Column 13: Lengths Behind
                margin = cells[13].get_text(strip=True)
                
                # Column 15: Time
                time_seconds = cells[15].get_text(strip=True)
                
                # Column 16: Speed Figure
                speed_figure = cells[16].get_text(strip=True)
                
                # Column 17: Starting Price
                sp_price = cells[17].get_text(strip=True)
                
                # Column 20: Comment
                comment = cells[20].get_text(strip=True) if len(cells) > 20 else ""

                run_data = {
                    'date': run_date,
                    'days_since_last_run': days_since_last_run,
                    'track': track,
                    'going': going,
                    'race_class': race_class,
                    'distance': int(distance),
                    'position': int(position),
                    'margin': float(margin) if margin.replace('.', '').isdigit() else 0.0,
                    'weight': float(weight),
                    'merit_rating': int(merit_rating) if merit_rating.isdigit() else None,
                    'jockey': jockey,
                    'draw': int(draw) if draw and draw.isdigit() else None,
                    'field_size': int(field_size) if field_size and field_size.isdigit() else None,
                    'time_seconds': float(time_seconds) if time_seconds.replace('.', '').isdigit() else None,
                    'starting_price': sp_price,
                    'comment': comment,
                    'horse_name': horse_name
                }
                
                parsed_runs.append(run_data)
                
            except (IndexError, ValueError) as e:
                if verbosity >= 1:
                    self.stdout.write(f"Error parsing row for {horse_name}: {e}")
                continue
            except Exception as e:
                if verbosity >= 1:
                    self.stdout.write(f"Unexpected error parsing row for {horse_name}: {e}")
                continue
        
        return parsed_runs  




    def display_runs_table(self, parsed_runs, horse_name):
        """
        Display runs in a formatted table using the proven format.
        """
        if not parsed_runs:
            self.stdout.write(f"    🐎 {horse_name} is a MAIDEN - no previous runs")
            return
        
        # Prepare data for tabulate
        headers = ['Date', 'Track', 'Going', 'Class', 'Dist', 'Pos', 'Len', 'Wgt', 'MR', 'Jockey', 'Draw', 'SP']
        table_data = []
        
        for run in parsed_runs:
            row = [
                run['date'],
                run['track'],
                run['going'],
                run['race_class'],
                run['distance'],
                run['position'],
                run['margin'],
                run['weight'],
                run['merit_rating'],
                run['jockey'],
                f"{run['draw']}/{run['field_size']}" if run['draw'] and run['field_size'] else '-',
                run['starting_price']
            ]
            table_data.append(row)
        
        # Display the table
        self.stdout.write(f"\n    🏇 RUN HISTORY FOR {horse_name.upper()}")
        self.stdout.write("    " + "=" * 120)
        self.stdout.write(tabulate(table_data, headers=headers, tablefmt='grid', stralign='left'))
        self.stdout.write(f"    ✅ Parsed {len(parsed_runs)} runs for {horse_name}")      