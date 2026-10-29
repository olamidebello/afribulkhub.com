"""Apply an authorized normalized feed atomically; suitable for a systemd timer."""
import argparse
import json
from pathlib import Path
import sys

# Works both in tools/ in a checkout and alongside app.py after installation.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE if (HERE/'app.py').exists() else HERE.parent))
import app
import alibaba_import


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--feed', required=True)
    parser.add_argument('--email', required=True, help='Existing active super administrator')
    args = parser.parse_args()
    file = Path(args.feed)
    if file.stat().st_size > 100000:
        parser.error('Feed must be at most 100000 bytes; split into batches of at most 250 offers')
    payload = json.loads(file.read_text())
    app.init_db()
    with app.connect() as c:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT id FROM users WHERE email=?', (args.email.lower(),)).fetchone()
        app.require(row, 'Administrator not found', 404)
        u = app.person(c, row[0])
        active = c.execute('SELECT status FROM tenants WHERE id=?', (u['tenant_id'],)).fetchone()[0]
        app.require(u['status'] == 'active' and active == 'active', 'Administrator suspended')
        # Re-reading an unchanged feed is normal for a timer; never reapply it.
        offers = payload.get('offers', []) if isinstance(payload, dict) else []
        stamp = payload.get('generated_at') if isinstance(payload, dict) else None
        unchanged = bool(offers) and all(
            isinstance(offer, dict) and c.execute(
                'SELECT 1 FROM alibaba_offers WHERE external_id=? AND source_time=?',
                (offer.get('external_id'), stamp)).fetchone() for offer in offers)
        result = {'skipped': True, 'reason': 'Feed already applied'} if unchanged else alibaba_import.sync(c, u, payload, app)
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except app.Error as exc:
        print(exc.message, file=sys.stderr)
        sys.exit(1)
