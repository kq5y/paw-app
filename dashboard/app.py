import os
import io
import random
import shutil
import tarfile

import docker
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

client = docker.from_env()

BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")
APPS_CODE_DIR = "/apps-code"

DEFAULT_APP_CODE = """from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello_world():
    return '<h1>Hello from my new Flask App!</h1>'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
"""

def get_random_name():
    adjectives = ['bright', 'cold', 'dark', 'great', 'high', 'little', 'new', 'old', 'shiny', 'young']
    nouns = ['river', 'sea', 'sky', 'sun', 'moon', 'star', 'tree', 'wind', 'fire', 'snow']
    return f"{random.choice(adjectives)}-{random.choice(nouns)}-{random.randint(100, 999)}"

def get_apps():
    apps = []
    running_containers = {c.name: c for c in client.containers.list(all=True)}

    if not os.path.exists(APPS_CODE_DIR):
        os.makedirs(APPS_CODE_DIR)
        
    for app_name in os.listdir(APPS_CODE_DIR):
        app_path = os.path.join(APPS_CODE_DIR, app_name)
        if os.path.isdir(app_path):
            container_name = f"user-app-{app_name}"
            container = running_containers.get(container_name)
            status = container.status if container else "stopped"
            apps.append({
                "name": app_name,
                "status": status,
                "url": f"http://{app_name}.{BASE_DOMAIN}",
                "https_url": f"https://{app_name}.{BASE_DOMAIN}"
            })
    return apps

@app.route('/')
def index():
    apps = get_apps()
    return render_template('index.html', apps=apps, base_domain=BASE_DOMAIN)

@app.route('/new', methods=['POST'])
def new_app():
    app_name = get_random_name()
    app_path = os.path.join(APPS_CODE_DIR, app_name)
    os.makedirs(app_path)
    with open(os.path.join(app_path, 'app.py'), 'w') as f:
        f.write(DEFAULT_APP_CODE)
    
    start_app_container(app_name)
    
    return redirect(url_for('index'))

@app.route('/app/<app_name>/edit', methods=['GET', 'POST'])
def edit_app(app_name):
    app_py_path = os.path.join(APPS_CODE_DIR, app_name, 'app.py')
    if not os.path.exists(app_py_path):
        return "App not found", 404

    if request.method == 'POST':
        code = request.form['code']
        with open(app_py_path, 'w') as f:
            f.write(code)
        restart_app_container(app_name)
        return redirect(url_for('index'))

    with open(app_py_path, 'r') as f:
        code = f.read()
    return render_template('edit.html', app_name=app_name, code=code)


def start_app_container(app_name):
    container_name = f"user-app-{app_name}"
    app_host_path = os.path.abspath(os.path.join(APPS_CODE_DIR, app_name))
    
    try:
        old_container = client.containers.get(container_name)
        old_container.remove(force=True)
    except docker.errors.NotFound:
        pass

    labels = {
        "traefik.enable": "true",
        f"traefik.http.routers.{app_name}-secure.rule": f"Host(`{app_name}.{BASE_DOMAIN}`)",
        f"traefik.http.routers.{app_name}-secure.entrypoints": "websecure",
        f"traefik.http.routers.{app_name}-secure.tls.certresolver": "myresolver",
        f"traefik.http.routers.{app_name}-secure.tls.domains[0].main": f"*.{BASE_DOMAIN}",
        f"traefik.http.routers.{app_name}.rule": f"Host(`{app_name}.{BASE_DOMAIN}`)",
        f"traefik.http.routers.{app_name}.entrypoints": "web",
        f"traefik.http.services.{app_name}.loadbalancer.server.port": "5000",
    }
    
    command = [
        "/bin/sh",
        "-c",
        "pip install Flask gunicorn requests && gunicorn --bind 0.0.0.0:5000 --access-logfile - --error-logfile - app:app"
    ]
    
    container = client.containers.create(
        image="python:3.10-slim",
        name=container_name,
        command=command,
        working_dir="/user-app",
        labels=labels,
        network="paw-web-network",
        detach=True,
        restart_policy={"Name": "always"}
    )

    network = client.networks.get("paw-web-network")
    network.connect(container)

    def make_tarfile(src_dir):
        tar_stream = io.BytesIO()
        with tarfile.open(fileobj=tar_stream, mode='w') as tar:
            for filename in os.listdir(src_dir):
                filepath = os.path.join(src_dir, filename)
                tar.add(filepath, arcname=filename)
        tar_stream.seek(0)
        return tar_stream
    
    container.put_archive('/user-app', data=make_tarfile(app_host_path))
    
    container.start()

def restart_app_container(app_name):
    start_app_container(app_name)

@app.route('/app/<app_name>/delete', methods=['POST'])
def delete_app(app_name):
    container_name = f"user-app-{app_name}"
    try:
        container = client.containers.get(container_name)
        container.remove(force=True)
    except docker.errors.NotFound:
        pass
        
    app_path = os.path.join(APPS_CODE_DIR, app_name)
    if os.path.exists(app_path):
        shutil.rmtree(app_path)
        
    return redirect(url_for('index'))

@app.route('/app/<app_name>/logs', methods=['GET'])
def get_logs(app_name):
    container_name = f"user-app-{app_name}"
    try:
        container = client.containers.get(container_name)
        logs = container.logs(tail=100).decode('utf-8')
        return render_template('logs.html', app_name=app_name, logs=logs)
    except docker.errors.NotFound:
        return "Container not found", 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
