FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OMP_NUM_THREADS=1 \
    MKL_NUM_THREADS=1 \
    OPENBLAS_NUM_THREADS=1 \
    NUMEXPR_NUM_THREADS=1 \
    TORCH_NUM_THREADS=1 \
    TORCH_NUM_INTEROP_THREADS=1 \
    MAX_CONTENT_LENGTH=262144 \
    MAX_ISSUED_TEAMS=512

WORKDIR /app

COPY dist/ /app/dist/
COPY chall/app.py chall/common.py chall/audit_selection.py chall/real_flag.txt /app/chall/

RUN pip install --no-cache-dir numpy flask requests \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch
RUN printf '{}\n' > /app/chall/issued_packs.json

EXPOSE 5000

CMD ["python", "-u", "/app/chall/app.py"]
