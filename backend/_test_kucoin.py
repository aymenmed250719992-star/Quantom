import asyncio, ccxt.async_support as ccxt, hmac, hashlib, base64, time, httpx

KEY    = '6a0846aa0ca91900019dc611'
SECRET = '8a416bd5-2194-4521-91b6-bf204b430a1a'
PW     = '11111111'

async def test_ccxt():
    ex = ccxt.kucoin({'apiKey': KEY, 'secret': SECRET, 'password': PW, 'options': {'defaultType': 'spot'}})
    try:
        b = await ex.fetch_balance()
        print('CCXT OK:', b.get('USDT'))
    except Exception as e:
        print('CCXT ERR:', str(e))
    await ex.close()

async def test_raw_v2():
    """Test KuCoin REST API v2 directly with manual HMAC signing."""
    ts = str(int(time.time() * 1000))
    method = 'GET'
    path = '/api/v1/accounts'
    body = ''
    pre = ts + method + path + body

    sig = base64.b64encode(hmac.new(SECRET.encode(), pre.encode(), hashlib.sha256).digest()).decode()
    # KuCoin v2: passphrase must also be HMAC-signed
    pw_sig = base64.b64encode(hmac.new(SECRET.encode(), PW.encode(), hashlib.sha256).digest()).decode()

    headers = {
        'KC-API-KEY':         KEY,
        'KC-API-SIGN':        sig,
        'KC-API-TIMESTAMP':   ts,
        'KC-API-PASSPHRASE':  pw_sig,
        'KC-API-KEY-VERSION': '2',
        'Content-Type':       'application/json',
    }
    async with httpx.AsyncClient() as client:
        r = await client.get('https://api.kucoin.com/api/v1/accounts', headers=headers)
        print('RAW v2:', r.status_code, r.text[:200])

async def test_raw_v1():
    """Test KuCoin REST API v1 — passphrase as plain text."""
    ts = str(int(time.time() * 1000))
    method = 'GET'
    path = '/api/v1/accounts'
    body = ''
    pre = ts + method + path + body

    sig = base64.b64encode(hmac.new(SECRET.encode(), pre.encode(), hashlib.sha256).digest()).decode()

    headers = {
        'KC-API-KEY':         KEY,
        'KC-API-SIGN':        sig,
        'KC-API-TIMESTAMP':   ts,
        'KC-API-PASSPHRASE':  PW,   # plain text
        'KC-API-KEY-VERSION': '1',
        'Content-Type':       'application/json',
    }
    async with httpx.AsyncClient() as client:
        r = await client.get('https://api.kucoin.com/api/v1/accounts', headers=headers)
        print('RAW v1:', r.status_code, r.text[:200])

asyncio.run(test_ccxt())
asyncio.run(test_raw_v2())
asyncio.run(test_raw_v1())
