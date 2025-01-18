web: gunicorn -w 1 -k eventlet app:app
release: flask db init
release: flask db upgrade