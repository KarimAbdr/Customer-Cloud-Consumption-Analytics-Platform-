import numpy as np
import pandas as pd

from ml.training.model import ChurnModel
from ml.training.train import predict_proba


class ChurnPredictor:
    def __init__(self, model: ChurnModel) -> None:
        self._model = model

    def predict(self, features: pd.DataFrame) -> float:
        return float(predict_proba(self._model, features)[0])

    def predict_many(self, features: pd.DataFrame) -> np.ndarray:
        """Probabilities for many customers at once, in the order of `features`."""
        if features.empty:
            return np.array([])
        return predict_proba(self._model, features)
