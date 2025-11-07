# ms_load_from_zoho/management/commands/sync_images_from_pg.py
import os
import math
import logging
from typing import Iterable, Tuple, Optional

import psycopg2
from django.core.management.base import BaseCommand, CommandParser
from mongoengine.connection import get_db

from ms_load_from_zoho.models import ZohoInventoryItem  # tu Document de MongoEngine

logger = logging.getLogger(__name__)


def iter_pg_rows(
    since: Optional[str] = None,
    batch_size: int = 1000,
) -> Iterable[Tuple[str, str]]:
    """
    Genera tuplas (item_id, image_name) desde Postgres.
    """
    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "dealerportal-postgres.cb4gqugm6ftg.us-east-2.rds.amazonaws.com"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "dealerportal-db"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", "poiuqwer09871234*-"),
        connect_timeout=10,
    )
    try:
        conn.autocommit = False
        with conn.cursor(name="cur_sync_images", withhold=True) as cur:
            cur.itersize = batch_size

            base_sql = """
                SELECT zoho_item_id, image_name
                FROM base_product
                WHERE image_name IS NOT NULL AND image_name <> ''
            """
            params = []
            if since:
                base_sql += " AND updated_at >= %s"
                params.append(since)

            # ayuda a streaming estable
            base_sql += " ORDER BY zoho_item_id"

            cur.execute(base_sql, params)

            for item_id, image_name in cur:
                if item_id and image_name:
                    yield str(item_id), str(image_name)

        conn.commit()
    finally:
        conn.close()


def bulk_update_mongo(pairs: Iterable[Tuple[str, str]], dry_run: bool = False) -> Tuple[int, int]:
    """
    Hace bulk_update en Mongo usando el collection nativo para eficiencia.
    Retorna (matched, modified).
    """
    from pymongo import UpdateOne

    coll = ZohoInventoryItem._get_collection()  # colección 'zoho_inventory_item'
    ops = []
    count = 0
    matched = 0
    modified = 0

    for item_id, image_name in pairs:
        ops.append(
            UpdateOne(
                {"item_id": item_id},
                {"$set": {"dealerportal_image": image_name}},
                upsert=False,  # no creamos nuevos; solo actualizamos existentes
            )
        )
        count += 1

        # ejecutar en lotes ~1000
        if len(ops) >= 1000:
            if not dry_run:
                res = coll.bulk_write(ops, ordered=False)
                matched += (res.matched_count or 0)
                modified += (res.modified_count or 0)
            ops = []

    if ops:
        if not dry_run:
            res = coll.bulk_write(ops, ordered=False)
            matched += (res.matched_count or 0)
            modified += (res.modified_count or 0)

    return matched, modified


class Command(BaseCommand):
    help = "Sincroniza image_name desde Postgres (tabla base_product) hacia Mongo (ZohoInventoryItem) por item_id."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--since", type=str, default=os.getenv("SYNC_SINCE"), help="YYYY-MM-DD para filtrar por updated_at en Postgres (opcional).")
        parser.add_argument("--batch", type=int, default=int(os.getenv("SYNC_BATCH_SIZE", "1000")), help="Tamaño de lote para leer de Postgres.")
        parser.add_argument("--dry-run", action="store_true", help="No escribe en Mongo, solo cuenta.")
        parser.add_argument("--verbose", action="store_true", help="Log detallado.")

    def handle(self, *args, **options):
        if options["verbose"]:
            logging.basicConfig(level=logging.INFO)

        since = options["since"]
        batch_size = options["batch"]
        dry_run = options["dry_run"]

        logger.info("Iniciando sync de imágenes: since=%s batch=%s dry_run=%s", since, batch_size, dry_run)

        # sanity check de índice/unique en item_id
        # (tu modelo ya define unique=True; si no, conviene asegurar índice)
        db = get_db()  # asegura que hay conexión MongoEngine
        logger.info("Mongo DB conectado: %s", db.name)

        # stream desde PG y hacer bulk por chunks hacia Mongo
        total_read = 0
        total_matched = 0
        total_modified = 0

        buffer_pairs = []
        for pair in iter_pg_rows(since=since, batch_size=batch_size):
            buffer_pairs.append(pair)
            total_read += 1

            if len(buffer_pairs) >= batch_size:
                matched, modified = bulk_update_mongo(buffer_pairs, dry_run=dry_run)
                total_matched += matched
                total_modified += modified
                logger.info("Batch aplicado: read=%s matched=%s modified=%s", total_read, total_matched, total_modified)
                buffer_pairs = []

        if buffer_pairs:
            matched, modified = bulk_update_mongo(buffer_pairs, dry_run=dry_run)
            total_matched += matched
            total_modified += modified

        logger.info("Sync terminado: rows_leidas=%s, matched=%s, modified=%s, dry_run=%s",
                    total_read, total_matched, total_modified, dry_run)
