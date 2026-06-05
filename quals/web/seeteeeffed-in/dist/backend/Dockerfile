FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app.py .
COPY frontend /app/frontend
EXPOSE 5000
CMD ["python", "app.py"]
