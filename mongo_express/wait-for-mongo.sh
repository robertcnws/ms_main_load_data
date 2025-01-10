#!/bin/sh
set -e

# Variables que ya tengas definidas en tu Dockerfile o ECS:
# ME_CONFIG_MONGODB_SERVER (host), ME_CONFIG_MONGODB_PORT (puerto), etc.

HOST="${ME_CONFIG_MONGODB_SERVER:-mongo}"
PORT="${ME_CONFIG_MONGODB_PORT:-27017}"
MAX_RETRIES=10
SLEEP_SECONDS=2

echo "Waiting for Mongo ($HOST:$PORT) to become available..."

attempt=1
while [ $attempt -le $MAX_RETRIES ]
do
  # Usar netcat en modo silencioso para chequear conexión TCP
  if nc -z "$HOST" "$PORT" >/dev/null 2>&1; then
    echo "Mongo is available! (attempt $attempt)"
    break
  else
    echo "Mongo not ready (attempt $attempt/$MAX_RETRIES). Retrying in $SLEEP_SECONDS s..."
    sleep $SLEEP_SECONDS
  fi
  attempt=$((attempt+1))
done

# Si tras varios intentos no se pudo conectar, puedes decidir si salir o continuar
if [ $attempt -gt $MAX_RETRIES ]; then
  echo "Error: Mongo not reachable after $MAX_RETRIES attempts."
  # Si quieres forzar salida, descomenta:
  # exit 1
fi

# Ahora que terminó el wait, ejecuta el comando real de mongo-express
echo "Starting mongo-express..."
exec npm start
