FROM python:3.6

WORKDIR /workspace

COPY requirements.txt ./
COPY requirements-dev.txt ./

RUN pip install -r requirements.txt
RUN pip install -r requirements-dev.txt
