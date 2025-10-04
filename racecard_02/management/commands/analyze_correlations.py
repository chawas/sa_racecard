# racecard/management/commands/analyze_correlations.py
import pandas as pd
import numpy as np
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    
    def handle(self, *args, **options):
        from ..services.ai_data_service import AIDataService
        
        data_service = AIDataService()
        dataset = data_service.create_training_dataset()
        
        # Convert to pandas DataFrame
        df = self._create_dataframe(dataset)
        
        # Calculate correlations
        self._analyze_correlations(df)
        
        # Feature importance analysis
        self._analyze_feature_importance(df)
    
    def _create_dataframe(self, dataset):
        """Convert dataset to pandas DataFrame"""
        rows = []
        for data in dataset:
            row = data['features'].copy()
            row.update(data['target'])
            row['race_id'] = data['race_id']
            row['horse_id'] = data['horse_id']
            rows.append(row)
        
        return pd.DataFrame(rows)
    
    def _analyze_correlations(self, df):
        """Analyze correlations between features and targets"""
        self.stdout.write("=== CORRELATION ANALYSIS ===")
        
        # Correlation with finish position (lower is better)
        position_corr = df.corr()['finish_position'].abs().sort_values(ascending=False)
        self.stdout.write("\nCorrelation with Finish Position:")
        for feature, corr in position_corr.items():
            if feature != 'finish_position' and not pd.isna(corr):
                self.stdout.write(f"  {feature:25s}: {corr:.3f}")
        
        # Correlation with speed rating (higher is better)
        if 'speed_rating' in df.columns:
            speed_corr = df.corr()['speed_rating'].abs().sort_values(ascending=False)
            self.stdout.write("\nCorrelation with Speed Rating:")
            for feature, corr in speed_corr.items():
                if feature != 'speed_rating' and not pd.isna(corr):
                    self.stdout.write(f"  {feature:25s}: {corr:.3f}")
    
    def _analyze_feature_importance(self, df):
        """Advanced feature importance analysis"""
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.model_selection import train_test_split
        
        # Prepare data
        X = df.drop(['finish_position', 'beaten_lengths', 'speed_rating', 'race_id', 'horse_id'], 
                   axis=1, errors='ignore')
        y = df['finish_position']
        
        # Remove non-numeric columns and handle missing values
        X = X.select_dtypes(include=[np.number]).fillna(0)
        
        # Train-test split
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Train Random Forest for feature importance
        model = RandomForestRegressor(n_estimators=100, random_state=42)
        model.fit(X_train, y_train)
        
        # Get feature importance
        importance = pd.DataFrame({
            'feature': X.columns,
            'importance': model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        self.stdout.write("\n=== RANDOM FOREST FEATURE IMPORTANCE ===")
        for _, row in importance.head(15).iterrows():
            self.stdout.write(f"  {row['feature']:25s}: {row['importance']:.4f}")