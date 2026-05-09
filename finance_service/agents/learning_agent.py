"""LearningAgent - Machine learning for trade outcome prediction and strategy optimization.

Features:
- Train LightGBM classifier on historical trade outcomes
- Compute SHAP values for interpretability
- Suggest rule adjustments based on feature importance
- Optuna-based hyperparameter optimization (optional)
"""
import os
import asyncio
import logging
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
import pandas as pd
import numpy as np
import joblib
import json
from pathlib import Path

from finance_service.agents.agent_interface import Agent, AgentReport
from finance_service.core.event_bus import Event, Events, get_event_bus
from finance_service.core.yaml_config import YAMLConfigEngine
from finance_service.ml.feature_store import FeatureStore, FeatureRecord

try:
    import lightgbm as lgb
    LIGHTGBM_AVAILABLE = True
except ImportError:
    LIGHTGBM_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class ModelMetadata:
    """Metadata for a trained model"""
    model_version: str
    trained_at: datetime
    accuracy: float
    features: List[str]
    feature_importance: Dict[str, float]
    train_samples: int
    label_type: str
    hyperparams: Dict[str, Any]


class LearningAgent(Agent):
    """ML learning agent for trade outcome prediction and strategy optimization.

    Configuration:
        finance.learning.enabled: true/false
        finance.learning.label_type: "win_rate" (binary), "pnl" (regression)
        finance.learning.retrain_days: 7 (frequency)
        finance.learning.min_trades: 100 (min trades before training)
    """

    @property
    def agent_id(self) -> str:
        return "learning_agent"

    @property
    def goal(self) -> str:
        return "Learn from trade outcomes to improve strategy performance and provide insights."

    def __init__(self, config_engine: YAMLConfigEngine):
        self.config_engine = config_engine
        self.enabled = config_engine.get("finance", "learning/enabled", default=False)
        self.label_type = config_engine.get("finance", "learning/label_type", default="win_rate")
        self.retrain_days = config_engine.get("finance", "learning/retrain_days", default=7)
        self.min_trades = config_engine.get("finance", "learning/min_trades", default=100)
        
        self.model_dir = Path(os.getenv("STORAGE_DIR", "storage")) / "ml_models"
        self.model_dir.mkdir(parents=True, exist_ok=True)
        self.current_model: Optional[Any] = None
        self.metadata: Optional[ModelMetadata] = None
        self.feature_store = FeatureStore()
        
        logger.info(f"LearningAgent initialized (enabled={self.enabled})")

    async def run(self, payload: Dict[str, Any]) -> Optional[AgentReport]:
        """
        Run learning tasks: either train on historical data or predict on new features.

        Args:
            payload: {
                "mode": "train" | "predict" | "explain",
                "features": FeatureRecord (for predict/explain),
                "symbol": Optional[str],
                "date": Optional[date],
            }

        Returns:
            AgentReport with model predictions, explanations, or training metrics.
        """
        if not self.enabled or not LIGHTGBM_AVAILABLE:
            return AgentReport(self.agent_id, "success", "Learning disabled or LightGBM missing", {})

        mode = payload.get("mode", "train")
        logger.info(f"LearningAgent run: mode={mode}")

        if mode == "train":
            return await self._train_model()
        elif mode == "predict":
            features = payload.get("features")
            if not features:
                return AgentReport(self.agent_id, "error", "Missing features for prediction", {})
            proba = self._predict(features)
            return AgentReport(self.agent_id, "success", "Prediction complete", {"win_probability": float(proba)})
        elif mode == "explain":
            features = payload.get("features")
            if not features:
                return AgentReport(self.agent_id, "error", "Missing features for explanation", {})
            explanation = self._explain(features)
            return AgentReport(self.agent_id, "success", "Explanation generated", {"explanation": explanation})
        else:
            return AgentReport(self.agent_id, "error", f"Unknown mode: {mode}", {})

    async def _train_model(self) -> AgentReport:
        """Train LightGBM on historical feature/label data"""
        logger.info("LearningAgent: starting model training")
        
        # Determine training window
        end_date = date.today()
        start_date = end_date - timedelta(days=365)  # 1 year
        
        # Load dataset
        X, y = self.feature_store.load_dataset(
            start_date=start_date,
            end_date=end_date,
            label_type=self.label_type
        )
        if X.empty or len(y) < self.min_trades:
            logger.warning(f"Insufficient training data: {len(y)} trades (need {self.min_trades})")
            return AgentReport(self.agent_id, "warning", f"Only {len(y)} samples, need {self.min_trades}", {})
        
        logger.info(f"Training on {len(X)} samples, {len(X.columns)-2} features")  # exclude symbol, date

        # Prepare features (drop identifier columns)
        feature_cols = [c for c in X.columns if c not in ['symbol', 'date']]
        X_train = X[feature_cols].fillna(0)
        y_train = y.fillna(0)

        # Hyperparameter tuning with Optuna (optional, can be toggled)
        use_optuna = self.config_engine.get("finance", "learning/use_optuna", default=False)
        if use_optuna:
            best_params = self._optimize_hyperparameters(X_train, y_train)
        else:
            best_params = {
                'n_estimators': 100,
                'learning_rate': 0.05,
                'max_depth': 5,
                'num_leaves': 31,
                'min_child_samples': 20,
                'subsample': 0.8,
                'colsample_bytree': 0.8,
                'random_state': 42,
            }

        # Train final model
        if self.label_type == "win_rate":
            # Binary classification
            model = Any(**best_params)
            model.fit(X_train, y_train)
            accuracy = model.score(X_train, y_train)
        else:
            # Regression
            model = lgb.LGBMRegressor(**best_params)
            model.fit(X_train, y_train)
            accuracy = model.score(X_train, y_train)  # R2

        self.current_model = model
        self.metadata = ModelMetadata(
            model_version=datetime.now().strftime("%Y%m%d_%H%M%S"),
            trained_at=datetime.now(),
            accuracy=float(accuracy),
            features=feature_cols,
            feature_importance={k: float(v) for k, v in zip(feature_cols, model.feature_importances_)},
            train_samples=len(X_train),
            label_type=self.label_type,
            hyperparams=best_params,
        )

        # Save model
        model_path = self.model_dir / f"model_{self.metadata.model_version}.pkl"
        with open(model_path, 'wb') as f:
            joblib.dump(model, f)
        # Save metadata
        meta_path = self.model_dir / f"metadata_{self.metadata.model_version}.json"
        with open(meta_path, 'w') as f:
            json.dump(asdict(self.metadata), f, indent=2, default=str)

        logger.info(f"Model trained: accuracy={accuracy:.3f}, saved to {model_path}")

        # Publish event
        await self.event_bus.publish(Event(
            event_type=Events.MODEL_TRAINED,
            data=asdict(self.metadata)
        ))

        return AgentReport(
            self.agent_id,
            "success",
            f"Model trained on {len(X_train)} samples, accuracy={accuracy:.3f}",
            {
                "accuracy": accuracy,
                "samples": len(X_train),
                "features": len(feature_cols),
                "model_path": str(model_path),
            }
        )

    def _predict(self, features: FeatureRecord) -> float:
        """Predict probability of positive outcome for a feature set"""
        if self.current_model is None:
            # Load latest model
            latest = self._load_latest_model()
            if latest is None:
                logger.warning("No trained model available for prediction")
                return 0.5
            self.current_model, self.metadata = latest

        # Build feature vector
        feature_vec = np.array([features.features.get(f, 0.0) for f in self.metadata.features]).reshape(1, -1)
        if hasattr(self.current_model, 'predict_proba'):
            proba = self.current_model.predict_proba(feature_vec)[0, 1]
        else:
            proba = self.current_model.predict(feature_vec)[0]
        return float(proba)

    def _explain(self, features: FeatureRecord) -> Dict[str, Any]:
        """Generate SHAP explanation for a prediction"""
        if self.current_model is None:
            latest = self._load_latest_model()
            if latest is None:
                return {}
            self.current_model, self.metadata = latest
        
        try:
            import shap
            # Build feature vector
            feature_vec = pd.DataFrame([[features.features.get(f, 0.0) for f in self.metadata.features]], columns=self.metadata.features)
            explainer = shap.TreeExplainer(self.current_model)
            shap_values = explainer.shap_values(feature_vec)
            if isinstance(shap_values, list):
                shap_values = shap_values[1]  # for classifier
            # Get top contributing features
            shap_abs = np.abs(shap_values[0])
            top_idx = np.argsort(shap_abs)[-10:][::-1]
            top_features = [(self.metadata.features[i], float(shap_values[0, i]), float(feature_vec.iloc[0, i])) 
                           for i in top_idx]
            return {
                "prediction": self._predict(features),
                "base_value": float(explainer.expected_value) if hasattr(explainer, 'expected_value') else None,
                "top_features": [{"name": n, "shap_value": s, "feature_value": v} for n, s, v in top_features]
            }
        except ImportError:
            logger.warning("SHAP not installed; skipping explanation")
            return {}

    def _optimize_hyperparameters(self, X: pd.DataFrame, y: pd.Series) -> Dict[str, Any]:
        """Use Optuna to find optimal hyperparameters"""
        try:
            import optuna
            def objective(trial):
                params = {
                    'n_estimators': trial.suggest_int('n_estimators', 50, 300),
                    'learning_rate': trial.suggest_float('learning_rate', 0.01, 0.3, log=True),
                    'max_depth': trial.suggest_int('max_depth', 3, 10),
                    'num_leaves': trial.suggest_int('num_leaves', 15, 127),
                    'min_child_samples': trial.suggest_int('min_child_samples', 10, 100),
                    'subsample': trial.suggest_float('subsample', 0.6, 1.0),
                    'colsample_bytree': trial.suggest_float('colsample_bytree', 0.6, 1.0),
                    'random_state': 42,
                }
                if self.label_type == "win_rate":
                    model = Any(**params)
                else:
                    model = lgb.LGBMRegressor(**params)
                # Simple cross-validation split (5-fold)
                from sklearn.model_selection import cross_val_score
                scores = cross_val_score(model, X, y, cv=5, scoring='roc_auc' if self.label_type == "win_rate" else 'r2')
                return scores.mean()
            study = optuna.create_study(direction='maximize')
            study.optimize(objective, n_trials=20, timeout=3600)
            logger.info(f"Optuna best score: {study.best_value:.3f}")
            return study.best_params
        except ImportError:
            logger.warning("Optuna not installed; using default hyperparameters")
            return {}

    def _load_latest_model(self) -> Optional[Tuple[Any, ModelMetadata]]:
        """Load the most recent trained model"""
        models = sorted(self.model_dir.glob("model_*.pkl"))
        if not models:
            return None
        latest_model_path = models[-1]
        meta_path = self.model_dir / f"metadata_{latest_model_path.stem.replace('model_', '')}.json"
        with open(latest_model_path, 'rb') as f:
            model = joblib.load(f)
        with open(meta_path, 'r') as f:
            meta_data = json.load(f)
            meta = ModelMetadata(**meta_data)
        return model, meta
