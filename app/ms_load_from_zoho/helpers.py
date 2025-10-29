import time
import threading
from collections import deque
from random import random
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
import requests
import os
from django.http import JsonResponse
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.contrib import messages
from django.urls import reverse
from .models import (
                      AppConfig,
                    )

import requests
import logging
import time


logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# ---------- Parámetros tunables ----------
ZOHO_RPM = int(os.getenv("ZOHO_MAX_CALLS_PER_MINUTE", "80"))   # llamadas/minuto
ZOHO_MAX_ATTEMPTS = 6                                          # reintentos por request
ZOHO_BASE_BACKOFF = 1.2                                         # factor de backoff exponencial
ZOHO_JITTER_MAX = 0.3                                           # jitter aleatorio (seg)
ZOHO_WORKERS_SHIP = int(os.getenv("ZOHO_WORKERS_SHIP", "2"))    # concurrencia shipments
ZOHO_WORKERS_PKG  = int(os.getenv("ZOHO_WORKERS_PKG",  "2"))    # concurrencia packages
ZOHO_429_FALLBACK_SLEEP = float(os.getenv("ZOHO_429_FALLBACK_SLEEP", "60"))
# -----------------------------------------

class RateLimiter:
    """Token bucket simple: máx ZOHO_RPM por ventana de 60s (global por proceso)."""
    def __init__(self, max_per_minute: int):
        self.max = max_per_minute
        self.window = deque()
        self.lock = threading.Lock()

    def wait_for_slot(self):
        with self.lock:
            now = time.time()
            # limpia entradas fuera de ventana de 60s
            while self.window and now - self.window[0] >= 60.0:
                self.window.popleft()
            if len(self.window) < self.max:
                self.window.append(now)
                return 0.0  # sin espera
            # cuánto falta para liberar el más antiguo
            delay = 60.0 - (now - self.window[0])
        time.sleep(max(0.0, delay))
        # reintento inmediato para tomar el slot
        return self.wait_for_slot()

_global_rl = RateLimiter(ZOHO_RPM)

def _retry_session():
    r = Retry(
        total=3,  # reintentos de conexión/errores transitorios a nivel urllib3
        backoff_factor=0.6,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    s = requests.Session()
    s.headers.update({"User-Agent": "NWS-MainLoad/1.0"})
    s.mount("https://", HTTPAdapter(max_retries=r))
    s.mount("http://",  HTTPAdapter(max_retries=r))
    return s

def zoho_get(session, url, headers, params, zoho_org_id, logger, timeout=40):
    attempt = 0
    last_exc = None
    while attempt < ZOHO_MAX_ATTEMPTS:
        attempt += 1
        _global_rl.wait_for_slot()
        try:
            resp = session.get(url, headers=headers, params=params, timeout=timeout)

            if resp.status_code == 401:
                new_token = refresh_zoho_access_token(zoho_org_id)
                headers['Authorization'] = f'Zoho-oauthtoken {new_token}'
                _global_rl.wait_for_slot()
                resp = session.get(url, headers=headers, params=params, timeout=timeout)

            if resp.status_code == 429:
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    try:
                        sleep_s = max(1.0, float(retry_after))
                    except Exception:
                        sleep_s = ZOHO_429_FALLBACK_SLEEP
                else:
                    # <-- CAMBIO: espera fuerte (por defecto 60s) cuando no hay Retry-After
                    sleep_s = ZOHO_429_FALLBACK_SLEEP
                logger.warning(f"429 {url} (attempt {attempt}/{ZOHO_MAX_ATTEMPTS}). Sleeping {sleep_s:.1f}s...")
                time.sleep(sleep_s)
                continue

            resp.raise_for_status()
            return resp

        except requests.exceptions.RequestException as e:
            last_exc = e
            sleep_s = (ZOHO_BASE_BACKOFF ** attempt) + random() * ZOHO_JITTER_MAX
            logger.warning(
                f"Transient error on {url} (attempt {attempt}/{ZOHO_MAX_ATTEMPTS}): {e}. "
                f"Sleeping {sleep_s:.1f}s..."
            )
            time.sleep(sleep_s)

    if last_exc:
        logger.error(f"Max attempts exceeded for {url}: {last_exc}")
        raise last_exc
    raise RuntimeError(f"Max attempts exceeded for {url}")


#############################################
# GET AUTH URL
#############################################

def generate_auth_url(zoho_org_id):
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    client_id = app_config.zoho_client_id
    redirect_uri = app_config.zoho_redirect_uri
    scopes = ",".join(settings.ZOHO_SCOPES)
    auth_url = (
        f"https://accounts.zoho.com/oauth/v2/auth?"
        f"scope={scopes}&client_id={client_id}&response_type=code&access_type=offline"
        f"&prompt=consent&redirect_uri={redirect_uri}"
    )
    return JsonResponse({'auth_url': auth_url}, status=200)

#############################################
# GET ACCESS TOKEN
#############################################

def get_access_token(client_id, client_secret, refresh_token, zoho_org_id):
    logger.info(f'Getting access token: {zoho_org_id}')
    token_url = settings.ZOHO_TOKEN_URL
    if not refresh_token:
        raise Exception(f"Refresh token is missing for Zoho Org ID: {zoho_org_id}")
        # refresh_token = get_refresh_token()
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    try:
        response = requests.post(token_url, data=payload)
        if response.status_code == 200:
            access_token = response.json()["access_token"]
            return access_token
        else:
            raise Exception(f"Failed to get access token for Zoho Org ID {zoho_org_id}: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error getting access token for Zoho Org ID {zoho_org_id}: {e}")
        raise Exception(f"Error getting access token for Zoho Org ID {zoho_org_id}: {e}")

#############################################
# GET REFRESH TOKEN
#############################################

def refresh_zoho_access_token(zoho_org_id):
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    refresh_url = settings.ZOHO_TOKEN_URL
    payload = {
        'refresh_token': app_config.zoho_refresh_token,
        'client_id': app_config.zoho_client_id,
        'client_secret': app_config.zoho_client_secret,
        'grant_type': 'refresh_token'
    }
    try:
        response = requests.post(refresh_url, data=payload)
        if response.status_code == 200:
            new_token = response.json().get('access_token')
            return new_token
        else:
            raise Exception(f"Failed to refresh Zoho token for Zoho Org ID {zoho_org_id}: {response.text}")
    except requests.exceptions.RequestException as e:
        logger.error(f"Error refreshing Zoho token for Zoho Org ID {zoho_org_id} : {e}")
        raise Exception(f"Error refreshing Zoho token for Zoho Org ID {zoho_org_id}: {e}")


def get_refresh_token(request, zoho_org_id):
    authorization_code = request.GET.get("code", None)
    if not authorization_code:
        return JsonResponse({'error': 'Authorization code is missing'}, status=400)
    
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    token_url = "https://accounts.zoho.com/oauth/v2/token"
    data = {
        "code": authorization_code,
        "client_id": app_config.zoho_client_id,
        "client_secret": app_config.zoho_client_secret,
        "redirect_uri": app_config.zoho_redirect_uri,
        "grant_type": "authorization_code",
    }
    
    try:
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        response_json = response.json()
        access_token = response_json.get("access_token", None)
        refresh_token = response_json.get("refresh_token", None)

        if access_token and refresh_token:
            app_config.zoho_refresh_token = refresh_token
            app_config.save()
            return redirect(reverse("ms_load_from_zoho:zoho_api_settings", kwargs={'zoho_org_id': zoho_org_id}))
        else:
            raise Exception(f"Failed to obtain access_token and/or refresh_token for Zoho Org ID: {zoho_org_id}")

    except requests.exceptions.RequestException as e:
        logger.error(f"Error obtaining access_token and/or refresh_token for Zoho Org ID: {zoho_org_id}: {e}")
        return JsonResponse({'error': 'Failed to get refresh token'}, status=500)


#############################################
# ZOHO API SETTINGS
#############################################

def zoho_api_settings(zoho_org_id): 
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    if not app_config:
        app_config = AppConfig()
        app_config.save()

    connected = (
        app_config.zoho_connection_configured
        and app_config.zoho_refresh_token is not None
        or ""
    )
    
    auth_url = None
    if not connected:
        auth_url = reverse("ms_load_from_zoho:generate_auth_url", kwargs={'zoho_org_id': zoho_org_id})
    app_config_data = app_config.to_mongo().to_dict()
    app_config_data.pop('_id', None)  

    data = {
        "app_config": app_config_data,
        "connected": connected,
        "auth_url": auth_url,
        "zoho_connection_configured": app_config.zoho_connection_configured,
    }

    return JsonResponse(data, status=200)


#############################################
# ZOHO API CONNECT
#############################################

def zoho_api_connect(request, zoho_org_id):
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    if app_config.zoho_connection_configured:
        try:
            get_access_token(
                app_config.zoho_client_id,
                app_config.zoho_client_secret,
                app_config.zoho_refresh_token,
                zoho_org_id
            )
            messages.success(request, "Zoho API connected successfully.")
        except Exception as e:
            messages.error(request, f"Error connecting to Zoho API: {str(e)}")
    else:
        messages.warning(request, "Zoho API connection is not configured yet.")
    return JsonResponse({'message': 'Zoho API connected successfully.'}, status=200)


def config_headers(zoho_org_id):
    app_config = AppConfig.objects(zoho_org_id=zoho_org_id).first()
    access_token = get_access_token(
        app_config.zoho_client_id,
        app_config.zoho_client_secret,
        app_config.zoho_refresh_token,
        zoho_org_id
    )
    headers = {
        "Authorization": f"Zoho-oauthtoken {access_token}"
    }
    return headers