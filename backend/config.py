import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARGA_DATA_CFG = os.path.join(os.path.dirname(BASE_DIR), 'Carga Data SM', 'Conexion BD')

def load_env_file():
    """Lee el archivo .env si existe en la raíz y actualiza os.environ."""
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip().strip("'\"")
                    os.environ[k] = v

load_env_file()

def load_db_config():
    config = {
        'Server': '192.168.10.6',
        'Port': 1433,
        'User': 'sa',
        'Password': '',
        'Database': 'Sharepoint_Proyectos'
    }
    
    cfg_file = os.getenv('DB_CONFIG_FILE', CARGA_DATA_CFG)
    if os.path.exists(cfg_file):
        with open(cfg_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and ':' in line:
                    k, v = line.split(':', 1)
                    config[k.strip()] = v.strip()
                    
    # Override with env vars if present
    config['Server'] = os.getenv('DB_SERVER', config.get('Server', '192.168.10.6'))
    config['Port'] = int(os.getenv('DB_PORT', config.get('Port', 1433)))
    config['User'] = os.getenv('DB_USER', config.get('User', 'sa'))
    config['Password'] = os.getenv('DB_PASSWORD', config.get('Password', ''))
    config['Database'] = os.getenv('DB_NAME', config.get('Database', 'Sharepoint_Proyectos'))
    
    return config

DB_CONFIG = load_db_config()
JWT_ACCESS_SECRET = os.getenv('JWT_ACCESS_SECRET') or os.getenv('PORTAL_JWT_SECRET')
if not JWT_ACCESS_SECRET:
    raise RuntimeError('Falta JWT_ACCESS_SECRET (o PORTAL_JWT_SECRET) en .env: debe ser el mismo valor que en el Portal de Acceso')
PORTAL_JWT_SECRET = JWT_ACCESS_SECRET
PORTAL_BASE_URL = os.getenv('PORTAL_BASE_URL', 'https://200.14.222.162')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24

CORS_ORIGINS = [
    'https://200.14.222.162',
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'http://100.82.24.75:8000',
]

def _get_int_env(key: str, default: int) -> int:
    val = os.getenv(key)
    if val is not None and val.strip().isdigit():
        try:
            return int(val.strip())
        except (ValueError, TypeError):
            pass
    return default

def get_smtp_config():
    """Retorna la configuración SMTP para Office 365."""
    load_env_file()
    return {
        'host': os.getenv('SMTP_HOST', 'smtp.office365.com'),
        'port': _get_int_env('SMTP_PORT', 587),
        'user': os.getenv('SMTP_USER', ''),
        'password': os.getenv('SMTP_PASS', ''),
        'from_email': os.getenv('SMTP_FROM', os.getenv('SMTP_USER', '')),
        'timeout': _get_int_env('SMTP_TIMEOUT', 30),
        'default_recipient': os.getenv('SMTP_DEFAULT_RECIPIENT', 'alejandro.aguilarm@clarovtr.cl'),
    }

SMTP_CONFIG = get_smtp_config()

