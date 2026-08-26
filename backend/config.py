import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CARGA_DATA_CFG = os.path.join(os.path.dirname(BASE_DIR), 'Carga Data SM', 'Conexion BD')

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
JWT_SECRET = os.getenv('JWT_SECRET', 'app-lti-super-secret-key-2026-claro')
JWT_ALGORITHM = 'HS256'
JWT_EXPIRATION_HOURS = 24
