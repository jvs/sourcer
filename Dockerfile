FROM python:3.7

WORKDIR /workspace
COPY requirements-dev.txt .
RUN pip install -r requirements-dev.txt
