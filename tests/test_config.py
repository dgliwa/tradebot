import os
from pathlib import Path

import pytest

from tradebot.config import LIVE_URL, PAPER_URL, Settings, load_settings


def test_defaults_and_normalization():
    settings = Settings(mode=' PAPER ', universe=[' aapl ', 'MSFT', 'aapl', ''])
    assert settings.universe == ['AAPL', 'MSFT']
    assert settings.alpaca_base_url == PAPER_URL
    assert settings.db_path == Path('data/tradebot-paper.duckdb')
    assert Settings(mode='live').db_path != settings.db_path
    assert Settings(mode='live').alpaca_base_url == LIVE_URL


@pytest.mark.parametrize('kwargs', [dict(mode='invalid'), dict(universe=[]),
                                   dict(mode='paper', alpaca_base_url=LIVE_URL)])
def test_invalid_settings_rejected(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_only_selected_file_loaded_without_env_mutation(tmp_path):
    (tmp_path / '.env.paper').write_text('TRADEBOT_MODE=paper\nALPACA_KEY=paper-key\n')
    (tmp_path / '.env.live').write_text('TRADEBOT_MODE=live\nALPACA_KEY=live-key\n')
    before = dict(os.environ)
    assert load_settings(environ={}, env_dir=tmp_path).alpaca_key == 'paper-key'
    live = load_settings(environ={'TRADEBOT_MODE': 'LIVE'}, env_dir=tmp_path)
    assert live.alpaca_key == 'live-key'
    assert live.alpaca_base_url == LIVE_URL
    assert dict(os.environ) == before


def test_env_overrides_and_secret_repr(tmp_path):
    (tmp_path / '.env.paper').write_text('ALPACA_SECRET=from-file\n')
    settings = load_settings(environ={'ALPACA_SECRET': 'private-secret', 'ALPACA_KEY': 'private-key'}, env_dir=tmp_path)
    assert settings.alpaca_secret == 'private-secret'
    assert 'private-secret' not in repr(settings)
    assert 'private-key' not in repr(settings)


def test_conflicting_file_mode_rejected(tmp_path):
    (tmp_path / '.env.paper').write_text('TRADEBOT_MODE=live\n')
    with pytest.raises(ValueError, match='conflicts'):
        load_settings(environ={}, env_dir=tmp_path)
