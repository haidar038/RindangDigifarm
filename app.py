from App import create_app

app = create_app()

if __name__ == '__main__':
    app.run(debug=False, use_reloader=True, host='0.0.0.0', port=8082, threaded=True)