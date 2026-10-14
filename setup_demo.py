"""Create a NEW disposable demo repository without touching existing directories."""
import subprocess
from pathlib import Path

root = Path(__file__).parent.resolve()
target = root / 'demo-repo'
if target.exists():
    raise SystemExit('demo-repo already exists. It has been left unchanged.')
target.mkdir()
source = (root / 'demo' / 'pipeline.py').read_text(encoding='utf-8')
(target / 'pipeline.py').write_text(source.replace('.strip()', ''), encoding='utf-8')
def git(*args):
    subprocess.run(['git', '-C', str(target), *args], check=True)
git('init', '-b', 'main')
git('config', 'user.name', 'Codegraph Demo')
git('config', 'user.email', 'demo@example.invalid')
git('add', 'pipeline.py')
git('commit', '-m', 'Demo baseline')
(target / 'pipeline.py').write_text(source, encoding='utf-8')
print('Demo ready. Run: python -m codegraph --repo .\\demo-repo --base main --open')
