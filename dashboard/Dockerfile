FROM python:3.10-slim

WORKDIR /app

RUN pip install Flask docker gunicorn

COPY . .

CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
