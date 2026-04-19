FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /repo/03_data_extraction
COPY requirements.txt /tmp/requirements.txt
RUN python -m pip install --upgrade pip \
  && pip install -r /tmp/requirements.txt
CMD ["python", "run_pipeline.py"]
