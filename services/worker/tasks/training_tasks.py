from services.worker.celery_app import celery_app
from apps.api.modules.automl.service import run_automl_experiment_task

@celery_app.task(name="run_automl_experiment")
def run_automl_experiment(experiment_id: str):
    """
    Run the AutoML experiment pipeline in the background.
    """
    run_automl_experiment_task(experiment_id)
