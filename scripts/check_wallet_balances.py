import urllib.request, json

wallet = "0x49884F6254cE54989E45dC93E34902b3BEBd47A9"

def native_bal(rpc):
    payload = json.dumps({"jsonrpc":"2.0","method":"eth_getBalance","params":[wallet,"latest"],"id":1}).encode()
    req = urllib.request.Request(rpc, data=payload, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return int(json.loads(r.read()).get("result","0x0"), 16)

def erc20_bal(rpc, token, dec=6):
    padded = wallet[2:].lower().zfill(64)
    payload = json.dumps({"jsonrpc":"2.0","method":"eth_call","params":[{"to":token,"data":"0x70a08231"+padded},"latest"],"id":1}).encode()
    req = urllib.request.Request(rpc, data=payload, headers={"Content-Type":"application/json"})
    with urllib.request.urlopen(req, timeout=8) as r:
        return int(json.loads(r.read()).get("result","0x0"), 16) / (10**dec)

chains = [
    ("Ethereum",  "https://rpc.ankr.com/eth",      "ETH",  18, "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48"),
    ("Polygon",   "https://rpc.ankr.com/polygon",  "MATIC",18, "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359"),
    ("Arbitrum",  "https://rpc.ankr.com/arbitrum", "ETH",  18, "0xaf88d065e77c8cC2239327C5EDb3A432268e5831"),
    ("Optimism",  "https://rpc.ankr.com/optimism", "ETH",  18, "0x0b2C639c533813f4Aa9D7837CAf62653d097Ff85"),
    ("BNB Chain", "https://rpc.ankr.com/bsc",      "BNB",  18, "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"),
    ("Base",      "https://rpc.ankr.com/base",     "ETH",  18, "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"),
]

print("Wallet: " + wallet)
print("-" * 44)
print("%-12s %14s %10s" % ("Chain", "Native", "USDC"))
print("-" * 44)
for name, rpc, sym, dec, usdc_addr in chains:
    try:
        nat = native_bal(rpc) / (10**dec)
        usd = erc20_bal(rpc, usdc_addr)
        flag = " <<<" if (nat > 0 or usd > 0) else ""
        print("%-12s %8.4f %-5s $%7.4f%s" % (name, nat, sym, usd, flag))
    except Exception as e:
        print("%-12s error: %s" % (name, str(e)[:35]))
