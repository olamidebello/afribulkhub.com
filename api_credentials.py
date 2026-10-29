"""Private Alibaba integration configuration; secret values never enter public settings."""
import json
import os
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken

SECRET_FIELDS = ('app_key', 'app_secret', 'access_token', 'refresh_token')
DEFAULTS = {'enabled': True, 'scheduled_enabled': True, 'auto_publish': True,
            'environment': 'production', 'token_expires_at': 0}


def init(c):
    c.execute('CREATE TABLE IF NOT EXISTS integration_credentials('
              'provider TEXT PRIMARY KEY, config TEXT NOT NULL, secrets TEXT NOT NULL,'
              'revision INTEGER NOT NULL, updated INTEGER NOT NULL, actor INTEGER NOT NULL)')


def read(c):
    row = c.execute("SELECT * FROM integration_credentials WHERE provider='alibaba'").fetchone()
    config = dict(DEFAULTS)
    if row:
        config.update(json.loads(row['config']))
    return row, config


def cipher(app, create=False):
    path = Path(os.environ.get('ABH_CREDENTIAL_KEY_FILE',
                               str(Path(app.DB).parent/'api-credentials.key')))
    if create and not path.exists():
        # The database and this separate key file must both be backed up privately.
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(Fernet.generate_key())
    app.require(path.is_file(), 'Credential encryption key is missing; restore the server key file', 409)
    try:
        return Fernet(path.read_bytes().strip())
    except (ValueError, OSError):
        raise app.Error(409, 'Credential encryption key is unavailable or invalid')


def decrypt(row, app):
    if not row or not row['secrets']:
        return {}
    try:
        return json.loads(cipher(app).decrypt(row['secrets'].encode()))
    except (InvalidToken, ValueError):
        raise app.Error(409, 'Cannot decrypt credentials; restore the original server key file')


def status(c, app):
    row, config = read(c)
    # Presence metadata is kept in config; listing settings never needs secret decryption.
    configured = config.pop('configured', {})
    return dict(config, credentials={name: bool(configured.get(name)) for name in SECRET_FIELDS},
                revision=row['revision'] if row else 0,
                updated=row['updated'] if row else None,
                updated_by=row['actor'] if row else None,
                markup_percent=30, live_api_connected=False,
                upstream_orders_connected=False)


def save(c, u, data, app):
    app.require(isinstance(data, dict), 'Expected settings object', 400)
    allowed = set(DEFAULTS) | set(SECRET_FIELDS) | {'revision'}
    app.require(not (set(data)-allowed), 'Unknown integration setting', 400)
    row, config = read(c)
    revision = row['revision'] if row else 0
    app.require(type(data.get('revision')) is int and data['revision'] == revision,
                'Settings changed; reload before saving', 409)
    for key, default in DEFAULTS.items():
        if key not in data:
            continue
        value = data[key]
        app.require(type(value) is type(default), 'Invalid setting: '+key, 400)
        if key == 'environment':
            app.require(value in {'production', 'sandbox'}, 'Invalid environment', 400)
        if key == 'token_expires_at':
            app.require(0 <= value < 32503680000, 'Invalid token expiry timestamp', 400)
        config[key] = value
    values = decrypt(row, app)
    for name in SECRET_FIELDS:
        if name in data:
            value = data[name]
            app.require(isinstance(value, str) and len(value) <= 12000,
                        'Invalid credential field: '+name, 400)
            # Empty inputs deliberately retain existing values for safe rotation.
            if value.strip():
                values[name] = value.strip()
    config['configured'] = {name: bool(values.get(name)) for name in SECRET_FIELDS}
    encrypted = cipher(app, create=not row or not row['secrets']).encrypt(
        json.dumps(values).encode()).decode() if values else ''
    c.execute('INSERT INTO integration_credentials VALUES (?,?,?,?,?,?) '
              'ON CONFLICT(provider) DO UPDATE SET config=excluded.config, secrets=excluded.secrets,'
              'revision=excluded.revision, updated=excluded.updated, actor=excluded.actor',
              ('alibaba', json.dumps(config), encrypted, revision+1, app.now(), u['id']))
    app.audit(c, u, 'alibaba:credentials:update')
    return status(c, app)


def revoke(c, u, app):
    row, _ = read(c)
    config = dict(DEFAULTS, enabled=False, scheduled_enabled=False)
    c.execute('INSERT INTO integration_credentials VALUES (?,?,?,?,?,?) '
              'ON CONFLICT(provider) DO UPDATE SET config=excluded.config, secrets=excluded.secrets,'
              'revision=excluded.revision, updated=excluded.updated, actor=excluded.actor',
              ('alibaba', json.dumps(config), '', (row['revision'] if row else 0)+1, app.now(), u['id']))
    app.audit(c, u, 'alibaba:credentials:remove')
    return status(c, app)


def validate(c, u, app):
    row, config = read(c)
    values = decrypt(row, app)
    missing = [name for name in ('app_key', 'app_secret', 'access_token') if not values.get(name)]
    expired = bool(config['token_expires_at'] and config['token_expires_at'] <= app.now())
    app.audit(c, u, 'alibaba:credentials:validate')
    return {'credentials_present': not missing, 'missing_fields': missing,
            'token_expired': expired, 'live_api_connected': False,
            'message': 'Local configuration validation only. Alibaba has not authenticated these credentials; the approved API adapter is still required.'}
