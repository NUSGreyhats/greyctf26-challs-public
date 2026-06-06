FROM python:3.11-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends socat \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY dist/requirements.txt .
RUN pip install --no-cache-dir --extra-index-url https://download.pytorch.org/whl/cpu -r requirements.txt
COPY dist/ .

ENV OMP_NUM_THREADS=1
ENV MKL_NUM_THREADS=1
ENV OPENBLAS_NUM_THREADS=1
ENV NUMEXPR_NUM_THREADS=1

ENV FLAG=grey{w40w_Y0u_h4Z_a_L0t_oF_Fr3n5_inDeEd_:0}
EXPOSE 38267

CMD ["sh", "-c", "exec socat -t 20 TCP-LISTEN:38267,reuseaddr,fork EXEC:'python3 /app/server.py',stderr"]
