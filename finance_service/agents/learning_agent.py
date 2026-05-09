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


# ==================== LAYER 1: Real-Time Trade Analysis ====================

    async def layer1_analyze_trade(self, trade_id: str, trade_data: Dict[str, Any]) -> Optional['TradeAnalysisLayer1']:
        """
        Analyze a trade using LLM in real-time (immediately after execution).
        
        This provides immediate coaching feedback on entry quality, pattern recognition,
        and psychological discipline using Claude/Gemini LLM.
        
        Args:
            trade_id: Unique trade identifier
            trade_data: Trade execution data including symbol, side, price, P&L, etc.
        
        Returns:
            TradeAnalysisLayer1 dataclass or None if analysis fails
        """
        try:
            from finance_service.ml.learning_models import TradeAnalysisLayer1, PatternType
            import asyncio
            
            # Build trade context for LLM prompt
            prompt_context = await self._build_trade_analysis_context(trade_id, trade_data)
            if not prompt_context:
                logger.warning(f"Could not build context for trade {trade_id}")
                return None
            
            # Load prompt template
            prompt_template = self._load_prompt_template()
            if not prompt_template:
                logger.warning("Could not load trade analysis prompt template")
                return None
            
            # Build final prompt by substituting template variables
            llm_prompt = self._format_trade_analysis_prompt(prompt_template, prompt_context)
            
            # Call LLM with timeout protection
            try:
                llm_response = await asyncio.wait_for(
                    self._call_gemini_for_trade_analysis(llm_prompt),
                    timeout=5.0  # 5 second timeout for LLM call
                )
            except asyncio.TimeoutError:
                logger.warning(f"LLM timeout analyzing trade {trade_id}")
                return None
            
            if not llm_response:
                logger.warning(f"Empty LLM response for trade {trade_id}")
                return None
            
            # Parse JSON response
            try:
                analysis_json = self._parse_json_response(llm_response)
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"Failed to parse LLM response for {trade_id}: {e}")
                return None
            
            # Convert to TradeAnalysisLayer1 dataclass
            analysis = TradeAnalysisLayer1(
                trade_id=trade_id,
                symbol=trade_data.get('symbol', 'UNKNOWN'),
                entry_score=float(analysis_json.get('entry_score', 5.0)),
                skill_vs_luck_ratio=float(analysis_json.get('skill_vs_luck_ratio', 0.5)),
                pattern_type=analysis_json.get('pattern_type', PatternType.UNKNOWN.value),
                mistakes=analysis_json.get('mistakes', []),
                psychological_notes=analysis_json.get('psychological_notes', []),
                recommendations=analysis_json.get('recommendations', []),
                tags=analysis_json.get('tags', []),
                llm_response=analysis_json
            )
            
            logger.info(f"✅ Layer 1 analysis complete for {trade_id}: score={analysis.entry_score}, skill={analysis.skill_vs_luck_ratio}")
            return analysis
            
        except Exception as e:
            logger.error(f"Layer 1 analysis failed for trade {trade_id}: {e}")
            return None
    
    async def _build_trade_analysis_context(self, trade_id: str, trade_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Gather all context needed to analyze a trade (market regime, indicators, sentiment, etc.)."""
        try:
            context = {
                'symbol': trade_data.get('symbol', 'UNKNOWN'),
                'side': trade_data.get('side', 'BUY'),
                'quantity': trade_data.get('quantity', 0),
                'entry_price': trade_data.get('price', 0),
                'exit_price': trade_data.get('exit_price', trade_data.get('price', 0)),
                'pnl': trade_data.get('pnl', 0),
                'pnl_pct': trade_data.get('pnl_pct', 0),
                'filled_at': trade_data.get('filled_at', datetime.utcnow().isoformat()),
                'trade_reason': trade_data.get('reason', trade_data.get('decision', {}).get('reason', 'Unknown')),
                'confidence_score': trade_data.get('confidence', 5),
                'rr_ratio': trade_data.get('risk_reward_ratio', 1.0),
                'position_pct_of_max': trade_data.get('position_pct', 2.0),
            }
            
            # Try to get market regime and indicators (if available from agents)
            if hasattr(self, 'market_regime_agent') and self.market_regime_agent:
                regime = await self.market_regime_agent.get_current_regime(context['symbol'])
                context['market_regime'] = regime.get('regime', 'unknown')
                context['trend_direction'] = regime.get('trend', 'unknown')
                context['current_volatility'] = regime.get('volatility', 'normal')
            else:
                context['market_regime'] = 'unknown'
                context['trend_direction'] = 'unknown'
                context['current_volatility'] = 'normal'
            
            # Get indicator values
            context['rsi_at_entry'] = trade_data.get('rsi', None) or 'N/A'
            context['macd_at_entry'] = trade_data.get('macd', None) or 'N/A'
            context['bb_at_entry'] = trade_data.get('bollinger_bands', None) or 'N/A'
            context['ma20_at_entry'] = trade_data.get('ma20', None) or 'N/A'
            context['ma50_at_entry'] = trade_data.get('ma50', None) or 'N/A'
            
            # Sentiment
            context['news_sentiment'] = trade_data.get('news_sentiment', 'neutral')
            context['social_sentiment'] = trade_data.get('social_sentiment', 'neutral')
            context['iv_rank'] = trade_data.get('iv_rank', 50)
            
            # Volume profile
            context['volume_profile'] = trade_data.get('volume_profile', 'normal')
            
            return context
        except Exception as e:
            logger.error(f"Failed to build trade context: {e}")
            return None
    
    def _load_prompt_template(self) -> Optional[str]:
        """Load the trade analysis prompt template from file."""
        try:
            prompt_path = Path(__file__).parent.parent / "prompts" / "trade_analysis_layer1.md"
            if not prompt_path.exists():
                logger.warning(f"Prompt template not found: {prompt_path}")
                return None
            
            with open(prompt_path, 'r') as f:
                template = f.read()
            
            return template
        except Exception as e:
            logger.error(f"Failed to load prompt template: {e}")
            return None
    
    def _format_trade_analysis_prompt(self, template: str, context: Dict[str, Any]) -> str:
        """Format the prompt template with actual trade data."""
        try:
            prompt = template
            for key, value in context.items():
                placeholder = f"{{{key}}}"
                if isinstance(value, (int, float)):
                    value_str = f"{value:.2f}" if isinstance(value, float) else str(value)
                else:
                    value_str = str(value) if value is not None else "N/A"
                
                prompt = prompt.replace(placeholder, value_str)
            
            return prompt
        except Exception as e:
            logger.error(f"Failed to format prompt: {e}")
            return template
    
    async def _call_gemini_for_trade_analysis(self, prompt: str) -> Optional[str]:
        """Call Gemini LLM for trade analysis."""
        try:
            import google.generativeai as genai
            from finance_service.agents.llm_config import llm_config
            
            # Get LLM client
            client = llm_config.get_client("learning_layer1")
            if not client:
                logger.error("Could not get LLM client for learning_layer1")
                return None
            
            # Call model
            response = await asyncio.to_thread(
                client.generate_content,
                genai.types.ContentType.text,
                prompt
            )
            
            if not response or not response.text:
                logger.warning("Empty LLM response")
                return None
            
            return response.text
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return None
    
    def _parse_json_response(self, response_text: str) -> Dict[str, Any]:
        """Extract and parse JSON from LLM response."""
        import re
        
        # Try to find JSON in the response
        json_match = re.search(r'\{.*\}', response_text, re.DOTALL)
        if not json_match:
            raise ValueError("No JSON found in response")
        
        json_str = json_match.group(0)
        return json.loads(json_str)

    async def handle_trade_executed_layer1(self, event_payload: Dict[str, Any]) -> None:
        """
        Event handler: Called when a trade is executed.
        Triggers Layer 1 real-time analysis asynchronously (non-blocking).
        
        Args:
            event_payload: Event data including trade_id and Trade object
        """
        try:
            trade_id = event_payload.get('trade_id')
            trade_obj = event_payload.get('trade')
            
            if not trade_id or not trade_obj:
                logger.warning("Invalid TRADE_EXECUTED event: missing trade_id or trade object")
                return
            
            # Convert trade object to dict for analysis
            if hasattr(trade_obj, '__dict__'):
                trade_data = trade_obj.__dict__
            else:
                trade_data = trade_obj if isinstance(trade_obj, dict) else {}
            
            # Ensure required fields
            trade_data['trade_id'] = trade_id
            
            # Call Layer 1 analysis
            analysis = await self.layer1_analyze_trade(trade_id, trade_data)
            
            if analysis is None:
                logger.warning(f"Layer 1 analysis returned None for {trade_id}")
                return
            
            # Persist to database
            from finance_service.ml.learning_models import insert_trade_analysis_layer1
            from finance_service.storage.database import get_portfolio_db
            
            db = get_portfolio_db()
            if not insert_trade_analysis_layer1(db, analysis):
                logger.warning(f"Failed to persist analysis for {trade_id}")
            
            # Send asynchronous notifications (don't block)
            try:
                await self._notify_telegram_layer1(analysis)
            except Exception as e:
                logger.warning(f"Failed to send Telegram notification: {e}")
            
            # Publish LEARNING_FEEDBACK event
            try:
                await self.event_bus.publish(
                    'LEARNING_FEEDBACK',
                    {
                        'agent_id': 'learning_agent',
                        'event_type': 'LEARNING_FEEDBACK',
                        'trade_id': trade_id,
                        'layer': 1,
                        'analysis': analysis.to_dict()
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to publish LEARNING_FEEDBACK: {e}")
                
        except Exception as e:
            logger.warning(f"Layer 1 handler failed (non-blocking): {e}")
            # Non-blocking: Don't crash trading
    
    async def _notify_telegram_layer1(self, analysis: 'TradeAnalysisLayer1') -> None:
        """Send trade analysis feedback to Telegram."""
        try:
            if not hasattr(self, 'telegram_agent') or not self.telegram_agent:
                return
            
            # Format message
            entry_emoji = "🟢" if analysis.entry_score >= 7 else "🟡" if analysis.entry_score >= 4 else "🔴"
            skill_pct = int(analysis.skill_vs_luck_ratio * 100)
            luck_pct = 100 - skill_pct
            
            recommendation = analysis.recommendations[0] if analysis.recommendations else {}
            rec_text = recommendation.get('suggestion', 'Continue tracking') if recommendation else 'Continue tracking'
            
            message = f"""
📊 **Trade Analysis - {analysis.symbol}**

{entry_emoji} **Entry Score:** {analysis.entry_score:.1f}/10
🎯 **Pattern:** {analysis.pattern_type.replace('_', ' ').title()}
🧠 **Skill vs Luck:** {skill_pct}% skill, {luck_pct}% luck

💡 **Key Insight:** {analysis.mistakes[0] if analysis.mistakes else 'Good execution'}

⚡ **Action:** {rec_text}

ID: `{analysis.trade_id}`
"""
            
            await self.telegram_agent.send_message(message)
            
        except Exception as e:
            logger.debug(f"Telegram notification failed: {e}")
