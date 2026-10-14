"""Create a NEW mixed-language demo; never overwrite an existing directory."""
import subprocess
import sys
from pathlib import Path

PY = '''def price(amount):
    subtotal = amount * 2
    tax = subtotal * 0.1
    total = subtotal + tax
    return round(total, 2)

def checkout(amount):
    return price(amount) + price(1)
'''
JS = '''export function price(amount) {
    const subtotal = amount * 2;
    const tax = subtotal * 0.1;
    const total = subtotal + tax;
    return Math.round(total * 100) / 100;
}
export const checkout = amount => price(amount) + price(1);
'''
repo=Path(sys.argv[1]).resolve()
if repo.exists():raise SystemExit('Destination already exists; not overwritten')
repo.mkdir(parents=True)
def git(*args):return subprocess.check_output(['git','-C',str(repo),*args],stderr=subprocess.STDOUT).decode().strip()
git('init');git('config','user.name','PLISM PoC');git('config','user.email','poc@example.invalid')
(repo/'pricing.py').write_text(PY,encoding='utf-8');(repo/'pricing.js').write_text(JS,encoding='utf-8')
git('add','.');git('commit','-m','Base pricing functions')
(repo/'pricing.py').write_text(PY+'\n'+PY.split('def checkout')[0].replace('price','discount_price').replace('amount','quantity').replace('subtotal','initial'),encoding='utf-8')
(repo/'pricing.js').write_text(JS+'\n'+JS.split('export const checkout')[0].replace('price','discountPrice').replace('amount','quantity').replace('subtotal','initial'),encoding='utf-8')
(repo/'unsupported.css').write_text('body { color: green; }\n',encoding='utf-8')
(repo/'broken.js').write_text('function unfinished( {\n',encoding='utf-8')
git('add','.');git('commit','-m','Duplicate calculation plus parser failure fixture')
print(repo)
