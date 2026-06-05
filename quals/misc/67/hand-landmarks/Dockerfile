FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 \
    PORT=8790 \
    HAND_LANDMARK_MODEL=/models/hand_landmarker.task

RUN apt-get update \
  && apt-get install -y --no-install-recommends curl libgl1 libglib2.0-0 libgomp1 \
  && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY hand-landmarks/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN mkdir -p /models \
  && curl -fsSL \
    https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task \
    -o /models/hand_landmarker.task

COPY hand-landmarks/server.py /app/server.py

RUN groupadd --gid 1000 app \
  && useradd --uid 1000 --gid 1000 --home-dir /app --shell /usr/sbin/nologin app \
  && chown -R app:app /app /models

USER app

EXPOSE 8790

CMD ["python", "/app/server.py"]
