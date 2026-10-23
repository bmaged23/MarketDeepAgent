"""Real HTTP smoke inside a disposable running candidate; no cloud calls required."""
import json,secrets
import httpx

BASE='http://127.0.0.1:8600'
def main():
    with httpx.Client(base_url=BASE,timeout=120) as client:
        r=client.get('/healthz');r.raise_for_status();assert r.json()['status']=='ok'
        r=client.get('/readyz');r.raise_for_status();assert r.json()['products']==100
        r=client.get('/');r.raise_for_status();assert '<html' in r.text.lower()
        assert client.get('/docs').status_code==200
        products=client.get('/api/products').json();assert len(products)==100
        found=client.post('/api/search',json={'query':'Apples 1kg','mode':'hybrid','limit':5}).json()
        assert found['degraded'] is False
        apples=next(p for p in products if p['name']=='Apples 1kg')
        assert apples['product_id'] in [r['product']['product_id'] for r in found['results']]
        profile={'first_name':'Release','last_name':'Check','email':'release-'+secrets.token_hex(6)+'@example.org','password':secrets.token_urlsafe(24)}
        r=client.post('/api/register',json=profile);r.raise_for_status()
        client.headers['x-csrf-token']=client.cookies['market_csrf']
        cart=client.get('/api/cart').json()
        r=client.patch('/api/cart',json={'revision':cart['revision'],'items':[{'product_id':apples['product_id'],'quantity':2}]});r.raise_for_status()
        assert r.json()['total']==round(apples['price']*2,2)
        quote=client.post('/api/cart/quote');quote.raise_for_status();quote=quote.json()
        assert quote['ready'] is True
        assert client.get('/api/products/'+str(apples['product_id'])).json()['stock_quantity']==apples['stock_quantity']
        body={'token':quote['confirmation_token'],'confirmed':True,'payment_method':'cash_on_delivery','delivery_address':'Synthetic image check'}
        order=client.post('/api/cart/checkout',json=body);order.raise_for_status();order=order.json()
        retry=client.post('/api/cart/checkout',json=body);retry.raise_for_status();assert retry.json()['already_completed']
        assert order['order']['payment_status']=='unpaid'
        assert client.get('/api/products/'+str(apples['product_id'])).json()['stock_quantity']==apples['stock_quantity']-2
        assert not client.get('/api/cart').json()['items']
        print(json.dumps({'passed':True,'checks':['liveness','readiness','UI','API docs','catalog100','real BGE hybrid search','registration/session/CSRF','cart total','quote does not deduct stock','confirmed COD order','idempotent retry','exact stock deduction'],'synthetic_profile':profile,'order_id':order['order']['order_id']}))
if __name__=='__main__':main()
