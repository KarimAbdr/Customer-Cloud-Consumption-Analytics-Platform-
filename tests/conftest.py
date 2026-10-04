"""Keep Airflow (imported by the DAG tests) away from any real ~/airflow installation."""

import os
import tempfile

os.environ["AIRFLOW_HOME"] = tempfile.mkdtemp(prefix="airflow-test-")
os.environ["AIRFLOW__CORE__LOAD_EXAMPLES"] = "False"
