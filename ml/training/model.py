"""Model container kept in its own module so pickles never reference `__main__`.

Running `python -m ml.training.train` makes classes defined there live in `__main__`;
a model pickled from such a class cannot be loaded by another process (e.g. the API).
"""

from dataclasses import dataclass

from lightgbm import LGBMClassifier


@dataclass(frozen=True)
class ChurnModel:
    """Estimator plus the category levels seen in training.

    Fixing the levels keeps training and serving encodings identical; categories
    unseen at serving time become missing values instead of raising.
    """

    estimator: LGBMClassifier
    feature_names: list[str]
    categories: dict[str, list[str]]
