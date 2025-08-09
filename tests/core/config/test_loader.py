"""Tests for configuration loader."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.core.config.loader import ConfigLoader, get_config_loader, load_config


class TestConfigLoader:
    """Test cases for ConfigLoader."""

    @pytest.fixture()
    def temp_config_dir(self):
        """Create a temporary directory for test configs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture()
    def config_loader(self, temp_config_dir):
        """Create a ConfigLoader instance with temp directory."""
        return ConfigLoader(config_dir=temp_config_dir)

    def test_init(self, temp_config_dir):
        """Test ConfigLoader initialization."""
        loader = ConfigLoader(config_dir=temp_config_dir)
        assert loader.config_dir == temp_config_dir
        assert loader._cache == {}
        assert loader._schemas == {}
        assert loader._observer is None

    def test_load_simple_config(self, config_loader, temp_config_dir):
        """Test loading a simple configuration file."""
        # Create test config
        config_data = {"database": {"host": "localhost", "port": 5432, "name": "test_db"}}

        config_file = temp_config_dir / "database.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Load config
        loaded = config_loader.load_config("database")
        assert loaded == config_data

    def test_load_with_environment_override(self, config_loader, temp_config_dir):
        """Test loading config with environment-specific override."""
        # Base config
        base_config = {"api": {"host": "localhost", "port": 8000, "debug": True}}

        # Production override
        prod_config = {"api": {"host": "api.example.com", "debug": False}}

        # Write configs
        with open(temp_config_dir / "api.yaml", "w") as f:
            yaml.dump(base_config, f)

        with open(temp_config_dir / "api.production.yaml", "w") as f:
            yaml.dump(prod_config, f)

        # Load with production environment
        loaded = config_loader.load_config("api", environment="production")

        # Should have merged config
        assert loaded["api"]["host"] == "api.example.com"
        assert loaded["api"]["port"] == 8000  # From base
        assert loaded["api"]["debug"] is False  # From override

    def test_environment_variable_substitution(self, config_loader, temp_config_dir):
        """Test environment variable substitution."""
        # Set test env vars
        os.environ["TEST_DB_HOST"] = "test-db.example.com"
        os.environ["TEST_DB_PORT"] = "5433"

        try:
            config_data = {
                "database": {
                    "host": "${TEST_DB_HOST}",
                    "port": "${TEST_DB_PORT}",
                    "name": "${TEST_DB_NAME:-default_db}",
                    "ssl": "${TEST_DB_SSL:-true}",
                }
            }

            config_file = temp_config_dir / "database.yaml"
            with open(config_file, "w") as f:
                yaml.dump(config_data, f)

            loaded = config_loader.load_config("database")

            assert loaded["database"]["host"] == "test-db.example.com"
            assert loaded["database"]["port"] == "5433"
            assert loaded["database"]["name"] == "default_db"  # Used default
            assert loaded["database"]["ssl"] == "true"  # Used default

        finally:
            # Clean up env vars
            del os.environ["TEST_DB_HOST"]
            del os.environ["TEST_DB_PORT"]

    def test_config_caching(self, config_loader, temp_config_dir):
        """Test that configs are cached properly."""
        config_data = {"key": "value"}

        config_file = temp_config_dir / "test.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # First load
        config_loader.load_config("test")

        # Modify file
        config_data["key"] = "new_value"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        # Second load should return cached value
        loaded2 = config_loader.load_config("test")
        assert loaded2["key"] == "value"

        # Reload should clear cache
        config_loader.reload_config("test")
        loaded3 = config_loader.load_config("test")
        assert loaded3["key"] == "new_value"

    def test_merge_configs(self, config_loader):
        """Test deep merging of configurations."""
        base = {
            "server": {
                "host": "localhost",
                "port": 8000,
                "features": {"auth": True, "logging": True},
            },
            "database": {"host": "localhost"},
        }

        override = {
            "server": {"host": "production.com", "features": {"logging": False, "metrics": True}}
        }

        merged = config_loader.merge_configs(base, override)

        assert merged["server"]["host"] == "production.com"
        assert merged["server"]["port"] == 8000
        assert merged["server"]["features"]["auth"] is True
        assert merged["server"]["features"]["logging"] is False
        assert merged["server"]["features"]["metrics"] is True
        assert merged["database"]["host"] == "localhost"

    def test_get_config_path(self, config_loader, temp_config_dir):
        """Test getting configuration file paths."""
        # Create test files
        (temp_config_dir / "exists.yaml").touch()
        (temp_config_dir / "also.yml").touch()

        # Test existing files
        path = config_loader.get_config_path("exists")
        assert path == temp_config_dir / "exists.yaml"

        path = config_loader.get_config_path("also")
        assert path == temp_config_dir / "also.yml"

        # Test non-existent file with required=False
        path = config_loader.get_config_path("missing", required=False)
        assert path is None

        # Test non-existent file with required=True
        with pytest.raises(FileNotFoundError):
            config_loader.get_config_path("missing", required=True)

    def test_list_configs(self, config_loader, temp_config_dir):
        """Test listing available configurations."""
        # Create test files
        (temp_config_dir / "config1.yaml").touch()
        (temp_config_dir / "config2.yml").touch()
        (temp_config_dir / "config3.production.yaml").touch()  # Should be excluded
        (temp_config_dir / "not_yaml.txt").touch()  # Should be excluded

        configs = config_loader.list_configs()

        assert "config1" in configs
        assert "config2" in configs
        assert "config3.production" not in configs
        assert "not_yaml" not in configs

    def test_schema_validation(self, config_loader, temp_config_dir):
        """Test configuration validation against schema."""
        # Create schema
        schema = {
            "type": "object",
            "properties": {
                "port": {"type": "integer", "minimum": 1, "maximum": 65535},
                "host": {"type": "string"},
            },
            "required": ["port", "host"],
        }

        schema_dir = temp_config_dir / "schemas"
        schema_dir.mkdir()

        with open(schema_dir / "server.json", "w") as f:
            yaml.dump(schema, f)

        # Valid config
        valid_config = {"port": 8080, "host": "localhost"}
        assert config_loader.validate_config(valid_config, "server") is True

        # Invalid config - missing required field
        invalid_config = {"port": 8080}
        with pytest.raises(Exception):  # jsonschema.ValidationError
            config_loader.validate_config(invalid_config, "server")

    def test_hot_reload_watching(self, config_loader, temp_config_dir):
        """Test configuration hot-reloading setup."""
        # Start watching
        config_loader.start_watching()
        assert config_loader._observer is not None
        assert config_loader._observer.is_alive()

        # Stop watching
        config_loader.stop_watching()
        assert config_loader._observer is None

    def test_context_manager(self, temp_config_dir):
        """Test using ConfigLoader as context manager."""
        with ConfigLoader(config_dir=temp_config_dir) as loader:
            assert loader._observer is not None
            assert loader._observer.is_alive()

        # Observer should be stopped after context exit
        assert loader._observer is None

    def test_global_instance(self):
        """Test global config loader instance."""
        loader1 = get_config_loader()
        loader2 = get_config_loader()
        assert loader1 is loader2

    @patch("src.core.config.loader.get_config_loader")
    def test_load_config_function(self, mock_get_loader):
        """Test the convenience load_config function."""
        mock_loader = MagicMock()
        mock_get_loader.return_value = mock_loader
        mock_loader.load_config.return_value = {"test": "data"}

        result = load_config("test", "production")

        mock_loader.load_config.assert_called_once_with("test", "production")
        assert result == {"test": "data"}
