import os
import sys
import yaml
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))


def test_backend_dockerfile_structure():
    dockerfile_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "Dockerfile"))
    assert os.path.isfile(dockerfile_path), "Backend Dockerfile must exist"

    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "FROM python:3.11-slim" in content
    assert "WORKDIR /app" in content
    assert "EXPOSE 8000" in content
    assert "HEALTHCHECK" in content
    assert "USER copilot" in content
    assert "uvicorn" in content and "main:app" in content


def test_frontend_dockerfile_structure():
    dockerfile_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "Dockerfile"))
    assert os.path.isfile(dockerfile_path), "Frontend Dockerfile must exist"

    with open(dockerfile_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "FROM node:20-alpine AS builder" in content
    assert "FROM nginx:1.25-alpine" in content
    assert "EXPOSE 80" in content
    assert "HEALTHCHECK" in content
    assert "COPY --from=builder /app/build /usr/share/nginx/html" in content


def test_dockerignore_security():
    backend_dockerignore = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".dockerignore"))
    frontend_dockerignore = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", ".dockerignore"))

    assert os.path.isfile(backend_dockerignore), "Backend .dockerignore must exist"
    assert os.path.isfile(frontend_dockerignore), "Frontend .dockerignore must exist"

    with open(backend_dockerignore, "r", encoding="utf-8") as f:
        backend_ignored = f.read().splitlines()

    assert ".env" in backend_ignored
    assert "venv/" in backend_ignored or "venv" in backend_ignored

    with open(frontend_dockerignore, "r", encoding="utf-8") as f:
        frontend_ignored = f.read().splitlines()

    assert "node_modules/" in frontend_ignored or "node_modules" in frontend_ignored


def test_nginx_conf():
    nginx_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "frontend", "nginx.conf"))
    assert os.path.isfile(nginx_path), "nginx.conf must exist"

    with open(nginx_path, "r", encoding="utf-8") as f:
        content = f.read()

    assert "try_files $uri $uri/ /index.html;" in content
    assert "listen 80;" in content
    assert "X-Frame-Options" in content


def test_docker_compose_valid_yaml():
    compose_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.yml"))
    dev_compose_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "docker-compose.dev.yml"))

    assert os.path.isfile(compose_path), "docker-compose.yml must exist at project root"
    assert os.path.isfile(dev_compose_path), "docker-compose.dev.yml must exist at project root"

    with open(compose_path, "r", encoding="utf-8") as f:
        compose_data = yaml.safe_load(f)

    assert "services" in compose_data
    assert "backend" in compose_data["services"]
    assert "frontend" in compose_data["services"]
    assert "networks" in compose_data

    # Check dependency and healthcheck
    backend = compose_data["services"]["backend"]
    frontend = compose_data["services"]["frontend"]

    assert "healthcheck" in backend
    assert "depends_on" in frontend
    assert "backend" in frontend["depends_on"]
