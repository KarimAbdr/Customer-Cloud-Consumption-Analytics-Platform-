import pandas as pd

from ml.training.model import ChurnModel
from ml.training.train import predict_proba


class ChurnPredictor:
    def __init__(self, model: ChurnModel) -> None:
        self._model = model

    def predict(self, features: pd.DataFrame) -> float:
        return float(predict_proba(self._model, features)[0])
