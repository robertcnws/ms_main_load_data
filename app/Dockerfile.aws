# ./django/Dockerfile.aws
FROM python:3.12

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

ENV TZ=America/New_York

RUN ln -fs /usr/share/zoneinfo/$TZ /etc/localtime && \
    dpkg-reconfigure -f noninteractive tzdata

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --upgrade pip
RUN pip install gunicorn
RUN pip install uvicorn
RUN pip install -r requirements.txt

# Instalar herramientas necesarias incluyendo cron
RUN apt-get update && apt-get install -y wget gnupg2 lsb-release

# Herramientas necesarias (incluye gpg y certificados)
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates gnupg lsb-release && \
    rm -rf /var/lib/apt/lists/*

# Importar la clave en keyring (sin apt-key)
RUN install -m 0755 -d /etc/apt/keyrings && \
    wget -qO- https://www.postgresql.org/media/keys/ACCC4CF8.asc | \
      gpg --dearmor -o /etc/apt/keyrings/postgresql.gpg && \
    chmod 0644 /etc/apt/keyrings/postgresql.gpg

# Registrar el repo PGDG usando signed-by
RUN echo "deb [signed-by=/etc/apt/keyrings/postgresql.gpg] \
http://apt.postgresql.org/pub/repos/apt $(lsb_release -cs)-pgdg main" \
> /etc/apt/sources.list.d/pgdg.list

# Actualizar índices con el nuevo repo
RUN apt-get update

# Copia el contenido del directorio al contenedor
COPY . /app/
# Eliminar celerybeat-schedule y ejecutar autoflake para limpiar el código
RUN rm -f /app/celerybeat-schedule && \
    pip install --no-cache-dir autoflake && \
    autoflake -r --in-place \
      --remove-all-unused-imports \
      --remove-unused-variables \
      --exclude "*/migrations/*,.venv,venv,__pycache__" \
      .

COPY ./_deploy/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

# Puertos de app y Flower
EXPOSE 8000 5555

# (Opcional) Credenciales por defecto de Flower (cámbialas en prod)
ENV FLOWER_USER=admin \
    FLOWER_PASSWORD=admin

# (Opcional) Healthcheck para workers
HEALTHCHECK --interval=60s --timeout=10s --retries=3 \
  CMD celery -A ms_main_load_data inspect ping -d zoho@* -d senitron@* >/dev/null 2>&1 || exit 1

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
