"""Shared customer-facing calorie text for indexing and agents."""

CALORIE_FIELDS = ('calories_per_100','calorie_basis','calorie_status','calorie_source','calorie_notes')

def nutrition_summary(product):
    value = product.get('calories_per_100')
    if value is None:
        return ''
    unit = '100 ml' if product.get('calorie_basis') == 'per_100ml' else '100 g'
    status = 'Estimated' if product.get('calorie_status') != 'label_verified' else 'Label verified'
    return f"Calories: {value:g} kcal per {unit} ({status}). {product.get('calorie_notes') or ''}".strip()
