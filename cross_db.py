import csv, re, sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent
DATA = BASE / 'data'
XDB = DATA / 'crosses.sqlite'
CSV = DATA / 'crosses_seed.csv'


def norm(x):
    return re.sub(r'[^A-Z0-9]', '', (x or '').upper())


def init():
    DATA.mkdir(exist_ok=True)
    with sqlite3.connect(XDB) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS crosses (
            id INTEGER PRIMARY KEY,
            article_norm TEXT NOT NULL,
            article TEXT NOT NULL,
            brand TEXT NOT NULL,
            source TEXT NOT NULL,
            confidence TEXT NOT NULL DEFAULT 'seed'
        )''')
        con.execute('CREATE INDEX IF NOT EXISTS idx_crosses_article ON crosses(article_norm)')
        if con.execute('SELECT COUNT(*) FROM crosses').fetchone()[0] == 0 and CSV.exists():
            with CSV.open(encoding='utf-8-sig', newline='') as f:
                for r in csv.DictReader(f):
                    con.execute('INSERT INTO crosses(article_norm,article,brand,source,confidence) VALUES(?,?,?,?,?)',
                                (norm(r['article']), r['article'], r['brand'], r['source'], r.get('confidence','seed')))
            con.commit()


def find(article, limit=80):
    init()
    a = norm(article)
    if not a:
        return []
    with sqlite3.connect(XDB) as con:
        direct = con.execute('''SELECT article, brand, source, confidence
                                FROM crosses WHERE article_norm=? ORDER BY brand, article LIMIT ?''', (a, limit)).fetchall()
        # Treat all rows with the same source group as an equivalence cluster.
        if direct:
            sources = set(r[2] for r in direct)
            # Expand by source cluster: every article in a verified seed group is a cross.
            marks = ','.join('?' for _ in sources)
            rows = con.execute(f'''SELECT article, brand, source, confidence
                                   FROM crosses WHERE source IN ({marks}) ORDER BY brand, article LIMIT ?''',
                               (*sources, limit)).fetchall()
        else:
            rows = []
    seen=set(); out=[]
    for r in rows:
        key=(norm(r[0]), r[1])
        if key in seen: continue
        seen.add(key)
        out.append({'article':r[0], 'brand':r[1], 'source':r[2], 'confidence':r[3]})
    return out
