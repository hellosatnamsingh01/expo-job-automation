#!/bin/bash
celery -A app.tasks.celery_app worker --pool=solo --loglevel=info &
celery -A app.tasks.celery_app beat --loglevel=info &
wait
