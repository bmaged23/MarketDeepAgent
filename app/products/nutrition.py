"""Populate missing demo nutrition by exact product name; preserve supplied label values."""
import argparse
import json
from pathlib import Path
from app.config import PROJECT_ROOT, get_settings
from app.database.connection import connection, migrate
from app.utils.nutrition import CALORIE_FIELDS
from app.products.schemas import ProductUpdate

NUTRITION_FIELDS = CALORIE_FIELDS


def apply_catalog_nutrition(database_path, source_path=None):
    source_path = Path(source_path or PROJECT_ROOT / 'data/catalog_nutrition.json')
    records = json.loads(source_path.read_text())['products']
    if len({r['name'] for r in records}) != len(records):
        raise ValueError('Nutrition dataset contains duplicate product names')
    validated = [(r['name'],ProductUpdate.model_validate({k:r[k] for k in NUTRITION_FIELDS}).model_dump(exclude_unset=True)) for r in records]
    updated = 0
    with connection(database_path,write=True) as conn:
        for name,record in validated:
            rows = conn.execute('SELECT product_id,calories_per_100 FROM product WHERE name=?',(name,)).fetchall()
            if len(rows) != 1 or rows[0]['calories_per_100'] is not None:
                continue
            conn.execute('UPDATE product SET '+','.join(f'{field}=?' for field in NUTRITION_FIELDS)+' WHERE product_id=?', [record[field] for field in NUTRITION_FIELDS]+[rows[0]['product_id']])
            updated += 1
    return {'updated':updated}


def main():
    parser = argparse.ArgumentParser(description='Fill missing demo product calorie estimates without overwriting labels')
    parser.parse_args()
    settings = get_settings()
    migrate(settings.database_path)
    print(json.dumps(apply_catalog_nutrition(settings.database_path)))


if __name__ == '__main__': main()
