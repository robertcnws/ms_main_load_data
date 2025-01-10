# ms_main_load_data

## INDEX ##

[1. Crear archivo .env](#crear-archivo-.env)

## PARA DESPLIEGUE LOCAL

## Crear Archivo ```.env``` ##

### Para ```mongo-db```:

#### Archivo ```.env```:
##### MONGO_INITDB_ROOT_USERNAME=your_username
##### MONGO_INITDB_ROOT_PASSWORD=your_password
##### MONGO_INITDB_DATABASE=your_database

### Para ```mongo-express```:

#### Archivo ```.env```:
##### ME_CONFIG_MONGODB_ADMINUSERNAME=your_mongodb_username
##### ME_CONFIG_MONGODB_ADMINPASSWORD=your_mongodb_password
##### ME_CONFIG_MONGODB_SERVER=your_mongodb_host_in_dockercompose
##### ME_CONFIG_OPTIONS_EDITORTHEME=default
##### ME_CONFIG_BASICAUTH_USERNAME=your_user_login_mongoexpress
##### ME_CONFIG_BASICAUTH_PASSWORD=your_password_login_mongoexpress
##### ME_CONFIG_SITE_BASEURL=/mongo-express
##### ME_CONFIG_SITE_ENABLE_LINKS=false


### Para ```app```:

#### Archivo ```.env```:

##### MONGO_HOST=your_mongodb_host_in_dockercompose
##### MONGO_PORT=27017
##### MONGO_USER=your_mongodb_username
##### MONGO_PASSWORD=your_mongodb_password
##### MONGO_DB=your_mongodb_database
##### MONGO_URI=mongodb://your_mongodb_username:your_mongodb_password@your_mongodb_host_in_dockercompose:27017/your_mongodb_database

##### DJANGO_SUPERUSER_USERNAME=your_django_super_user_name
##### DJANGO_SUPERUSER_EMAIL=your_django_super_user_email
##### DJANGO_SUPERUSER_PASSWORD=your_django_super_user_password
##### LOGINUSER_USERNAME=your_django_loginuser
##### LOGINUSER_EMAIL=your_django_loginuser_email
##### LOGINUSER_PASSWORD=your_django_loginuser_password

##### ZOHO_SCOPES=ZohoInventory.items.READ,ZohoInventory.shipmentorders.READ,ZohoInventory.purchasereceives.READ,ZohoInventory.salesorders.READ,ZohoInventory.packages.READ,ZohoBooks.invoices.READ,ZohoBooks.contacts.READ,ZohoBooks.settings.READ
##### ZOHO_INVENTORY_ITEMS_URL=https://www.zohoapis.com/inventory/v1/items
##### ZOHO_INVENTORY_SHIPMENTORDERS_URL=https://www.zohoapis.com/inventory/v1/shipmentorders
##### ZOHO_INVENTORY_PURCHASERECEIVES_URL=https://www.zohoapis.com/inventory/v1/purchasereceives
##### ZOHO_INVENTORY_SALESORDERS_URL=https://www.zohoapis.com/inventory/v1/salesorders
##### ZOHO_INVENTORY_SHIPMENTS_URL=https://www.zohoapis.com/inventory/v1/shipmentorders
##### ZOHO_INVENTORY_PACKAGES_URL=https://www.zohoapis.com/inventory/v1/packages
##### ZOHO_BOOKS_INVOICES_URL=https://www.zohoapis.com/books/v3/invoices
##### ZOHO_BOOKS_CUSTOMERS_URL=https://www.zohoapis.com/books/v3/contacts
##### ZOHO_BOOKS_ITEMS_URL=https://www.zohoapis.com/books/v3/items
##### ZOHO_TOKEN_URL=https://accounts.zoho.com/oauth/v2/token
##### ZOHO_AUTH_URL=https://accounts.zoho.com/oauth/v2/auth

##### API_KEY_SENITRON=your_api_key_senitron
##### API_SENITRON_QUANTITIES_URL=https://app.senitron.net/nws/001/api/v1/inventories/quantities
##### API_SENITRON_ASSETS_URL=https://app.senitron.net/nws/001/api/v1/inventories/assets
##### API_SENITRON_ASSETS_LOGS_URL=https://app.senitron.net/nws/001/api/v1/inventories/assets/statuses/logs

##### CELERY_BROKER_URL=redis://your_redis_host_in_dockercompose:6379/0
##### CELERY_RESULT_BACKEND=redis://your_redis_host_in_dockercompose:6379/0
##### CELERY_TASKS_DELAY=10

##### DAY_OF_WEEK_MONDAY_TO_SATURDAY=mon-sat
##### DAY_OF_WEEK_SUNDAY=sun

##### MINUTE_ZOHO_SALES_MONDAY_TO_SATURDAY=*/5
##### HOUR_ZOHO_SALES_MONDAY_TO_SATURDAY=7-17

##### MINUTE_ZOHO_CUSTOMERS_ITEMS_MONDAY_TO_SATURDAY=*/2
##### HOUR_ZOHO_CUSTOMERS_ITEMS_MONDAY_TO_SATURDAY=7-17

##### MINUTE_SENITRON_MONDAY_TO_SATURDAY=*/10
##### HOUR_SENITRON_MONDAY_TO_SATURDAY=7-17

##### MINUTE_ZOHO_SALES_SUNDAY=0
##### HOUR_ZOHO_SALES_SUNDAY=*/6

##### MINUTE_ZOHO_CUSTOMERS_ITEMS_SUNDAY=30
##### HOUR_ZOHO_CUSTOMERS_ITEMS_SUNDAY=*/12

##### MINUTE_SENITRON_SUNDAY=5
##### HOUR_SENITRON_SUNDAY=*/2

##### ZOHO_ORG_ID=your_zoho_organization_id
##### ZOHO_CLIENT_ID=your_zoho_api_client_id
##### ZOHO_CLIENT_SECRET=your_zoho_api_secret_id
##### ZOHO_REDIRECT_URI=your_zoho_api_redirect_uri

##### ALLOWED_HOSTS=your_allowed_hosts
##### CSRF_TRUSTED_ORIGINS=your_csrf_trusted_origins
##### CORS_ALLOWED_ORIGINS=your_cors_allowed_origins
##### FRONTEND_URL=your_frontend_url



