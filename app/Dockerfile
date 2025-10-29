# ./django/Dockerfile
FROM python:3.12

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY requirements.txt /app/

RUN pip install --upgrade pip
RUN pip install gunicorn
RUN pip install uvicorn
RUN pip install -r requirements.txt

# Instalar herramientas necesarias incluyendo cron
RUN apt-get update && apt-get install -y wget gnupg2 lsb-release

# Agregar repositorio de PostgreSQL
RUN wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
RUN echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" | tee /etc/apt/sources.list.d/pgdg.list

# Actualizar e instalar dependencias
RUN apt-get update

# Copia el contenido del directorio al contenedor
COPY . /app/

# Ejecutar autoflake para limpiar el código
RUN pip install --no-cache-dir autoflake \
 && autoflake -r --in-place \
    --remove-all-unused-imports \
    --remove-unused-variables \
    --exclude "*/migrations/*,.venv,venv,__pycache__" \
    .

# Expose port 8000 for the Django application
EXPOSE 8000

# Ejecuta el script de inicialización y luego arranca Gunicorn y celery
CMD ["sh", "-c", "python manage.py collectstatic --no-input && \
                  python init_scripts.py && \
                  celery -A ms_main_load_data worker -Q zoho -c 1 -n zoho@%h --loglevel=info -E & \
                  celery -A ms_main_load_data worker -Q senitron -c 2 -n senitron@%h --loglevel=info -E & \
                  celery -A ms_main_load_data beat --loglevel=info & \
                  gunicorn ms_main_load_data.asgi:application -w 3 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000"]
