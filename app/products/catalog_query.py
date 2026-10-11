"""Validated, read-only product queries; no model-authored SQL is executed."""
from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.database.connection import connection
from app.products.queries import SELECT_PRODUCT, filter_clause
from app.product_search.schemas import SearchFilters
from app.utils.nutrition import CALORIE_FIELDS
from app.products.schemas import NutritionFields

ProductField = Literal['product_id', 'name', 'description', 'category', 'category_id',
                       'price', 'stock_quantity', 'image_path', 'calories_per_100',
                       'calorie_basis', 'calorie_status', 'calorie_source', 'calorie_notes']
PRODUCT_FIELDS = ('product_id', 'name', 'description', 'category', 'category_id',
                  'price', 'stock_quantity', 'image_path') + CALORIE_FIELDS


class ProductEvidence(NutritionFields):
    """Output contract; projected optional fields can be omitted."""
    model_config = ConfigDict(extra='forbid')
    product_id: int = Field(gt=0)
    name: str
    category_id: int = Field(gt=0)
    category: str
    description: str | None = None
    price: float | None = None
    stock_quantity: int | None = None
    image_path: str | None = None


class CatalogQuery(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    fields: list[ProductField] = Field(default_factory=list, max_length=13,
        description='Empty returns all public product fields. IDs/name/category and calorie units/status/notes are retained when needed.')
    product_ids: list[Annotated[int, Field(gt=0, strict=True)]] = Field(default_factory=list, max_length=100)
    name_contains: str | None = Field(default=None, min_length=1, max_length=200)
    min_calories: float | None = Field(default=None, ge=0, le=2000, allow_inf_nan=False)
    max_calories: float | None = Field(default=None, ge=0, le=2000, allow_inf_nan=False)
    calorie_basis: Literal['per_100g', 'per_100ml'] | None = None
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0, le=100000)
    all_matches: bool = Field(default=False, description='True when the question needs every matching product, e.g. category-wide comparisons/averages. Fetch subsequent pages as needed.')

    @model_validator(mode='after')
    def valid_selection(self):
        if any(type(i) is not int or i <= 0 for i in self.product_ids):
            raise ValueError('Product IDs must be positive integers')
        if self.min_calories is not None and self.max_calories is not None and self.min_calories > self.max_calories:
            raise ValueError('Invalid calorie range')
        return self


def project_product(product, fields=()):
    selected = set(fields or PRODUCT_FIELDS)
    selected.update(('product_id', 'name', 'category', 'category_id'))
    if selected.intersection(CALORIE_FIELDS):
        selected.update(CALORIE_FIELDS)
    return {key: product.get(key) for key in PRODUCT_FIELDS if key in selected}


def query_catalog(database_path, query, filters=None, max_results=100):
    query = CatalogQuery.model_validate(query)
    filters = SearchFilters.model_validate(filters or {})
    clause, params = filter_clause(filters)
    if query.product_ids:
        clause += ' AND p.product_id IN (' + ','.join('?' for _ in query.product_ids) + ')'
        params.extend(query.product_ids)
    if query.name_contains:
        # instr treats SQL/wildcard-like user text literally.
        clause += ' AND instr(lower(p.name), lower(?)) > 0'
        params.append(query.name_contains)
    for value, op in ((query.min_calories, '>='), (query.max_calories, '<=')):
        if value is not None:
            clause += f' AND p.calories_per_100 {op} ?'
            params.append(value)
    if query.calorie_basis:
        clause += ' AND p.calorie_basis=?'
        params.append(query.calorie_basis)
    if type(max_results) is not int or not 1 <= max_results <= 100:
        raise ValueError("SQL page maximum must be between 1 and 100")
    limit = min(query.limit, max_results)
    with connection(database_path) as conn:
        total = conn.execute('SELECT count(*) FROM product p JOIN category c USING(category_id) WHERE ' + clause, params).fetchone()[0]
        rows = conn.execute(SELECT_PRODUCT + ' WHERE ' + clause + ' ORDER BY p.product_id LIMIT ? OFFSET ?',
                            [*params, limit, query.offset]).fetchall()
    next_offset = query.offset + len(rows) if query.offset + len(rows) < total else None
    return {'degraded': False,
            'results': [{'product': project_product(dict(row), query.fields), 'score': None,
                         'sources': ['sql']} for row in rows],
            'selection': {'source': 'sql', 'total_matches': total, 'returned': len(rows),
                          'offset': query.offset, 'next_offset': next_offset,
                          'all_matches': query.all_matches, 'requested_fields': query.fields}}
