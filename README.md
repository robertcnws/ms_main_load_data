# ms_main_load_data

## INDEX ##

[1. Crear archivo .env](#crear-archivo-.env)

## Crear Archivo ```.env``` ##

### Para ```mongo-db```:

#### Archivo ```.env```:
##### MONGO_INITDB_ROOT_USERNAME=user
##### MONGO_INITDB_ROOT_PASSWORD=password

### Para ```mongo-express```:

#### Archivo ```.env```:
##### ME_CONFIG_MONGODB_ADMINUSERNAME=user
##### ME_CONFIG_MONGODB_ADMINPASSWORD=password
##### ME_CONFIG_MONGODB_SERVER=mongo-db
##### ME_CONFIG_MONGODB_PORT=27017