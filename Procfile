release: alembic upgrade head
web: gunicorn -k uvicorn.workers.UvicornWorker app.main:app --log-level info
worker: python -m app.core.scheduler
