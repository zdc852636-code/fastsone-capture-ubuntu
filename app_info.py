"""Public application name and per-user installation identity."""
from pathlib import Path

NAME = 'fastsone capture-ubuntu'
VERSION = '2.6.2'
APPLICATION_ID = 'fastsone-capture-ubuntu'
LEGACY_ID = 'fastsone-capture-lw-ubuntu'
LEGACY_NAME = 'fastsone capture-LW-ubuntu'


def installation_id(user_directory):
    """Keep upgrades on their existing lock, settings, models and desktop entries."""
    for identifier in (APPLICATION_ID, LEGACY_ID):
        entries = (user_directory / '.local/share' / identifier,
                   user_directory / '.config' / identifier,
                   user_directory / '.local/share/applications' / (identifier + '.desktop'),
                   user_directory / '.config/autostart' / (identifier + '.desktop'))
        if any(entry.exists() for entry in entries):
            return identifier
    return APPLICATION_ID


IDENT = installation_id(Path.home())
