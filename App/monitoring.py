# monitoring.py
import logging, sentry_sdk, os
from datetime import datetime, time
from logging.handlers import RotatingFileHandler
from flask import Flask, request, current_app, jsonify
from prometheus_flask_exporter import PrometheusMetrics
from sentry_sdk.integrations.flask import FlaskIntegration

from App import db, cache

app = current_app

def setup_monitoring(app: Flask):
    # Configure Sentry for error tracking
    sentry_sdk.init(
        dsn="your-sentry-dsn",
        integrations=[FlaskIntegration()],
        traces_sample_rate=1.0,
        environment=app.config['FLASK_ENV']
    )

    # Setup Prometheus metrics
    metrics = PrometheusMetrics(app)
    metrics.info('app_info', 'Application info', version='1.0.0')

    # Custom metrics
    by_path_counter = metrics.counter(
        'by_path_counter', 'Request count by request paths',
        labels={'path': lambda: request.path}
    )

    # Configure logging
    if not app.debug:
        if not os.path.exists('logs'):
            os.mkdir('logs')
        file_handler = RotatingFileHandler(
            'logs/rindang.log', 
            maxBytes=10240, 
            backupCount=10
        )
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
        ))
        file_handler.setLevel(logging.INFO)
        app.logger.addHandler(file_handler)

        app.logger.setLevel(logging.INFO)
        app.logger.info('Rindang startup')

# Request logging middleware
@app.before_request
def log_request_info():
    app.logger.debug('Headers: %s', request.headers)
    app.logger.debug('Body: %s', request.get_data())

# Error tracking
@app.errorhandler(Exception)
def handle_exception(e):
    current_app.logger.error(f'Unhandled exception: {e}', exc_info=True)
    return "Internal Server Error", 500

# Performance monitoring
def log_slow_queries():
    threshold = app.config.get('SLOW_QUERY_THRESHOLD', 0.5)  # seconds
    
    @db.event.listens_for(db.engine, 'after_cursor_execute')
    def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
        total = time.time() - context._query_start_time
        if total > threshold:
            app.logger.warning(
                f"Slow query detected: {statement} with params {parameters}. "
                f"Execution time: {total:.2f}s"
            )

# Health check endpoint
@app.route('/health')
def health_check():
    health_status = {
        'status': 'healthy',
        'database': check_db_connection(),
        'cache': check_cache_connection(),
        'timestamp': datetime.now().isoformat()
    }
    return jsonify(health_status)

def check_db_connection():
    try:
        db.session.execute('SELECT 1')
        return True
    except Exception as e:
        current_app.logger.error(f"Database health check failed: {e}")
        return False

def check_cache_connection():
    try:
        cache.get('health_check')
        return True
    except Exception as e:
        current_app.logger.error(f"Cache health check failed: {e}")
        return False