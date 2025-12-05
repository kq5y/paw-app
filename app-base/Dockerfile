FROM python:3.12-alpine

RUN pip install Flask gunicorn requests pycryptodome

RUN adduser -D -u 1000 paw

WORKDIR /user-app
RUN chown paw:paw /user-app

ENV PYTHONDONTWRITEBYTECODE=1
USER paw
