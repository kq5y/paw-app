import os
import docker
import random
import shutil
from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

client = docker.from_env()

BASE_DOMAIN = os.environ.get("BASE_DOMAIN", "localhost")
APPS_CODE_DIR = "/apps-code"

DEFAULT_APP_CODE = """
from flask import Flask

app = Flask(__name__)

@app.route('/')
def hello_world():
    return '<h1>Hello from my new Flask App!</h1>'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
"""

def get_random_name():
    """ユニークなアプリ名を生成"""
    adjectives = ['bright', 'cold', 'dark', 'great', 'high', 'little', 'new', 'old', 'shiny', 'young']
    nouns = ['river', 'sea', 'sky', 'sun', 'moon', 'star', 'tree', 'wind', 'fire', 'snow']
    return f"{random.choice(adjectives)}-{random.choice(nouns)}-{random.randint(100, 999)}"

def get_apps():
    """既存のアプリとコンテナの状態を取得"""
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
    """アプリ一覧ページ"""
    apps = get_apps()
    return render_template('index.html', apps=apps, base_domain=BASE_DOMAIN)

@app.route('/new', methods=['POST'])
def new_app():
    """新しいアプリを作成"""
    app_name = get_random_name()
    app_path = os.path.join(APPS_CODE_DIR, app_name)
    os.makedirs(app_path)
    with open(os.path.join(app_path, 'app.py'), 'w') as f:
        f.write(DEFAULT_APP_CODE)
    
    start_app_container(app_name)
    
    return redirect(url_for('index'))

@app.route('/app/<app_name>/edit', methods=['GET', 'POST'])
def edit_app(app_name):
    """アプリのコードを編集"""
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
    """アプリのコンテナを起動"""
    container_name = f"user-app-{app_name}"
    app_host_path = os.path.abspath(os.path.join(APPS_CODE_DIR, app_name))
    
    try:
        old_container = client.containers.get(container_name)
        old_container.remove(force=True)
    except docker.errors.NotFound:
        pass

    labels = {
        "traefik.enable": "true",
        "traefik.docker.network": "paw-web-network",
        f"traefik.http.routers.{app_name}-secure.rule": f"Host(`{app_name}.{BASE_DOMAIN}`)",
        f"traefik.http.routers.{app_name}-secure.entrypoints": "websecure",
        f"traefik.http.routers.{app_name}-secure.tls.certresolver": "myresolver",
        f"traefik.http.services.{app_name}-secure.loadbalancer.server.port": "5000",
        f"traefik.http.routers.{app_name}.rule": f"Host(`{app_name}.{BASE_DOMAIN}`)",
        f"traefik.http.routers.{app_name}.entrypoints": "web",
        f"traefik.http.services.{app_name}.loadbalancer.server.port": "5000",
    }
    
    command = [
        "/bin/sh",
        "-c",
        "pip install Flask gunicorn && gunicorn --bind 0.0.0.0:5000 user-app.app:app"
    ]
    
    client.containers.run(
        image="python:3.10-slim",
        name=container_name,
        command=command,
        working_dir="/user-app",
        volumes={app_host_path: {'bind': '/user-app', 'mode': 'rw'}},
        labels=labels,
        network="paw-web-network",
        detach=True,
        restart_policy={"Name": "always"}
    )

def restart_app_container(app_name):
    start_app_container(app_name)

@app.route('/app/<app_name>/delete', methods=['POST'])
def delete_app(app_name):
    """アプリとコンテナを削除"""
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
