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

# Actualizar e instalar dependencias
RUN apt-get update

# Copia el contenido del directorio al contenedor
COPY . /app/

# Expose port 8000 for the Django application
EXPOSE 8000

# Ejecuta el script de inicialización y luego arranca Gunicorn y celery
CMD ["sh", "-c", "python manage.py migrate && \
                  python manage.py collectstatic --no-input && \
                  python init_scripts.py && \
                  celery -A ms_main_load_data worker --loglevel=info -E & \
                  celery -A ms_main_load_data beat --loglevel=info & \
                  gunicorn ms_main_load_data.asgi:application -w 3 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000"]
