FROM python:3.10-slim

WORKDIR /dashboard

RUN pip install Flask docker gunicorn requests

COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
