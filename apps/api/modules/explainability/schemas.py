from pydantic import BaseModel
from typing import Dict, Any, Optional


class ShapGlobalResponse(BaseModel):
    summary_plot_base64: str
    feature_importances: Dict[str, float]
    insight: str
    # Phase 10 — model-aware extras
    explanation_method: Optional[str] = None  # shap_tree | coefficients | kernel_shap
    directions: Optional[Dict[str, str]] = None  # feature → "pushes prediction up/down"


class ShapLocalResponse(BaseModel):
    force_plot_base64: str
    row_values: Dict[str, Any]
    shap_values: Dict[str, float]
    base_value: float
    prediction: float
    explanation_method: Optional[str] = None
    narrative: Optional[str] = None  # plain-English why-this-prediction sentence
