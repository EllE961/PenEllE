"""Comprehensive tests for config loader module."""

import tempfile
import threading
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
import yaml
from watchdog.events import FileModifiedEvent

from src.core.config.loader import ConfigFileHandler, ConfigLoader, get_config_loader, load_config


class TestConfigFileHandler:
    """Test cases for ConfigFileHandler."""

    def test_on_modified_directory(self):
        """Test that directory modifications are ignored."""
        loader = Mock()
        handler = ConfigFileHandler(loader)

        event = Mock(spec=FileModifiedEvent)
        event.is_directory = True
        event.src_path = "/some/dir"

        handler.on_modified(event)
        loader.reload_config.assert_not_called()

    def test_on_modified_non_yaml_file(self):
        """Test that non-YAML files are ignored."""
        loader = Mock()
        handler = ConfigFileHandler(loader)

        event = Mock(spec=FileModifiedEvent)
        event.is_directory = False
        event.src_path = "/some/file.txt"

        handler.on_modified(event)
        loader.reload_config.assert_not_called()

    def test_on_modified_yaml_file_not_in_cache(self):
        """Test YAML file modification when not in cache."""
        loader = Mock()
        loader._cache = {}
        handler = ConfigFileHandler(loader)

        event = Mock(spec=FileModifiedEvent)
        event.is_directory = False
        event.src_path = "/some/config.yaml"

        handler.on_modified(event)
        loader.reload_config.assert_not_called()

    @patch("src.core.config.loader.logger")
    def test_on_modified_yaml_file_in_cache(self, mock_logger):
        """Test YAML file modification when in cache."""
        loader = Mock()
        loader._cache = {"config": {}}
        handler = ConfigFileHandler(loader)

        event = Mock(spec=FileModifiedEvent)
        event.is_directory = False
        event.src_path = "/some/config.yaml"

        handler.on_modified(event)
        loader.reload_config.assert_called_once_with("config")
        mock_logger.info.assert_called_once()

    def test_on_modified_yml_file(self):
        """Test .yml file modification."""
        loader = Mock()
        loader._cache = {"config": {}}
        handler = ConfigFileHandler(loader)

        event = Mock(spec=FileModifiedEvent)
        event.is_directory = False
        event.src_path = "/some/config.yml"

        handler.on_modified(event)
        loader.reload_config.assert_called_once_with("config")


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

    def test_init_default(self):
        """Test initialization with default config directory."""
        # Mock Path to control the default directory
        with patch("src.core.config.loader.Path") as mock_path_class:
            mock_path = Mock()
            mock_path.exists.return_value = True
            mock_path.is_dir.return_value = True
            mock_path.mkdir = Mock()
            mock_path.parent = Mock()
            mock_path.parent.parent = Mock()
            mock_path.parent.parent.parent = Mock()
            mock_path.parent.parent.parent.parent = Mock()
            mock_path.parent.parent.parent.parent.__truediv__ = Mock(return_value=mock_path)
            mock_path_class.return_value = mock_path

            loader = ConfigLoader()
            assert loader.config_dir == mock_path
            assert loader._cache == {}
            assert loader._schemas == {}
            assert loader._lock is not None
            assert loader._observer is None

    def test_init_custom_dir(self, temp_config_dir):
        """Test initialization with custom config directory."""
        loader = ConfigLoader(config_dir=temp_config_dir)
        assert loader.config_dir == temp_config_dir
        assert loader._cache == {}
        assert loader._schemas == {}

    def test_init_nonexistent_dir(self, tmp_path):
        """Test initialization with non-existent directory - should create it."""
        test_dir = tmp_path / "nonexistent" / "dir"
        loader = ConfigLoader(test_dir)
        assert loader.config_dir == test_dir
        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_init_file_instead_of_dir(self):
        """Test initialization with file instead of directory."""
        with tempfile.NamedTemporaryFile() as tmpfile:
            # Should raise an error when trying to create directory with file name
            with pytest.raises((OSError, NotADirectoryError)):
                ConfigLoader(Path(tmpfile.name))

    def test_load_file_success(self, config_loader, temp_config_dir):
        """Test successfully loading a YAML file."""
        # Create a test YAML file
        test_config = {"key": "value", "nested": {"item": 123}}
        file_path = temp_config_dir / "test.yaml"
        with open(file_path, "w") as f:
            yaml.dump(test_config, f)

        # Load the file
        result = config_loader._load_file("test")
        assert result == test_config

    def test_load_file_not_found(self, config_loader, temp_config_dir):
        """Test loading non-existent YAML file."""
        with pytest.raises(FileNotFoundError):
            config_loader._load_file("nonexistent")

    def test_load_file_invalid_yaml(self, config_loader, temp_config_dir):
        """Test loading invalid YAML file."""
        invalid_yaml = temp_config_dir / "invalid.yaml"
        with open(invalid_yaml, "w") as f:
            f.write("invalid: yaml: content: [")

        with pytest.raises(yaml.YAMLError):
            config_loader._load_file("invalid")

    def testmerge_configs(self, config_loader):
        """Test merging configurations."""
        base = {"a": 1, "b": {"c": 2, "d": 3}, "e": [1, 2]}
        override = {"b": {"c": 4, "f": 5}, "e": [3], "g": 6}

        result = config_loader.merge_configs(base, override)

        # Check merged result
        assert result["a"] == 1  # From base
        assert result["b"]["c"] == 4  # Overridden
        assert result["b"]["d"] == 3  # From base
        assert result["b"]["f"] == 5  # From override
        assert result["e"] == [3]  # Override lists (not merged)
        assert result["g"] == 6  # From override

    def test_merge_configs_empty(self, config_loader):
        """Test merging with empty configs."""
        assert config_loader.merge_configs({}, {"a": 1}) == {"a": 1}
        assert config_loader.merge_configs({"a": 1}, {}) == {"a": 1}
        assert config_loader.merge_configs({}, {}) == {}

    @patch("src.core.config.loader.jsonschema.validate")
    def testvalidate_config_with_schema(self, mock_validate, config_loader):
        """Test validating config with schema."""
        config_loader._schemas["test"] = {"type": "object"}
        config = {"key": "value"}

        config_loader.validate_config(config, "test")
        mock_validate.assert_called_once_with(config, {"type": "object"})

    @patch("src.core.config.loader.logger")
    def test_validate_config_no_schema(self, mock_logger, config_loader):
        """Test validating config without schema."""
        config_loader.validate_config({"key": "value"}, "test")
        mock_logger.warning.assert_called_with("No schema found for: test")

    def test_validate_config_invalid(self, config_loader):
        """Test validating invalid config against schema."""
        config_loader._schemas["test"] = {
            "type": "object",
            "properties": {"key": {"type": "string"}},
            "required": ["key"],
        }

        # Invalid: missing required field
        with pytest.raises(ValueError, match="Configuration validation failed"):
            config_loader.validate_config({}, "test")

    def test_load_config_simple(self, config_loader, temp_config_dir):
        """Test loading a simple configuration."""
        config_data = {"database": {"host": "localhost", "port": 5432}}

        config_file = temp_config_dir / "database.yaml"
        with open(config_file, "w") as f:
            yaml.dump(config_data, f)

        loaded = config_loader.load_config("database")
        assert loaded == config_data

    def test_load_config_with_environment(self, config_loader, temp_config_dir):
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

    def test_load_config_from_cache(self, config_loader):
        """Test loading config from cache."""
        config_loader._cache["test:local"] = {"cached": True}

        result = config_loader.load_config("test")
        assert result == {"cached": True}

    def test_load_config_with_schema_validation(self, config_loader, temp_config_dir):
        """Test loading config with schema validation."""
        # Create config
        config_file = temp_config_dir / "server.yaml"
        with open(config_file, "w") as f:
            yaml.dump({"host": "localhost", "port": 8080}, f)

        # Create schema directory and schema
        schema_dir = temp_config_dir / "schemas"
        schema_dir.mkdir()
        schema_file = schema_dir / "server.yaml"
        with open(schema_file, "w") as f:
            yaml.dump(
                {
                    "type": "object",
                    "properties": {"host": {"type": "string"}, "port": {"type": "integer"}},
                    "required": ["host", "port"],
                },
                f,
            )

        # Load config - should validate against schema
        config = config_loader.load_config("server")
        assert config["host"] == "localhost"
        assert config["port"] == 8080

    @patch("src.core.config.loader.logger")
    def test_reload_config(self, mock_logger, config_loader, temp_config_dir):
        """Test reloading configuration."""
        # Create initial config
        config_file = temp_config_dir / "test.yaml"
        with open(config_file, "w") as f:
            yaml.dump({"key": "value1"}, f)

        # Load initially
        config_loader.load_config("test")
        assert config_loader._cache["test:local"]["key"] == "value1"

        # Update file
        with open(config_file, "w") as f:
            yaml.dump({"key": "value2"}, f)

        # Reload specific config
        config_loader.reload_config("test")
        # Check that the reload was logged
        mock_logger.info.assert_any_call("Reloaded configuration: test")
        assert config_loader._cache["test:local"]["key"] == "value2"

    @patch("src.core.config.loader.logger")
    def test_reload_all_configs(self, mock_logger, config_loader):
        """Test reloading all configurations."""
        # Populate cache
        config_loader._cache = {"config1:default": {"old": True}, "config2:prod": {"old": True}}

        # Mock load_config to update cache
        def mock_load(name, environment="default"):
            config_loader._cache[f"{name}:{environment}"] = {"new": True}
            return {"new": True}

        config_loader.load_config = mock_load

        # Reload all
        config_loader.reload_config()
        mock_logger.info.assert_any_call("Reloading all configurations")

        # Check all were reloaded
        assert config_loader._cache["config1:default"]["new"] is True
        assert config_loader._cache["config2:prod"]["new"] is True

    def test_get_all_configs(self, config_loader):
        """Test getting all configurations."""
        config_loader._cache = {
            "config1:dev": {"a": 1},
            "config2:dev": {"b": 2},
            "config1:prod": {"a": 3},
        }

        # Get all configs
        all_configs = config_loader.get_all_configs()
        assert len(all_configs) == 3
        assert all_configs["config1:dev"] == {"a": 1}

        # Get configs for specific environment
        dev_configs = config_loader.get_all_configs(environment="dev")
        assert len(dev_configs) == 2
        assert dev_configs["config1"] == {"a": 1}
        assert dev_configs["config2"] == {"b": 2}

    def test_clear_cache(self, config_loader):
        """Test clearing configuration cache."""
        config_loader._cache = {"test": {"data": "value"}}

        config_loader.clear_cache()
        assert config_loader._cache == {}

    @patch("src.core.config.loader.logger")
    def test_watch_starts_watching(self, mock_logger, config_loader):
        """Test watch method starts watching."""
        # watch() should be an alias for start_watching()
        config_loader.watch()

        # Should have started watching
        assert config_loader._observer is not None
        mock_logger.info.assert_called()

        # Clean up
        config_loader.stop_watching()

    @patch("src.core.config.loader.logger")
    def test_stop_watching_works(self, mock_logger, config_loader):
        """Test stop_watching method works correctly."""
        # Start watching first
        config_loader.start_watching()
        assert config_loader._observer is not None

        # Stop watching
        config_loader.stop_watching()
        assert config_loader._observer is None
        mock_logger.info.assert_called()

    def test_thread_safety(self, config_loader, temp_config_dir):
        """Test that config loading is thread-safe."""
        # Create a config file
        config_file = temp_config_dir / "test.yaml"
        with open(config_file, "w") as f:
            yaml.dump({"thread": "safe"}, f)

        results = []

        def load_config():
            result = config_loader.load_config("test")
            results.append(result)

        # Run multiple threads
        threads = [threading.Thread(target=load_config) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All should get the same result
        assert len(results) == 10
        assert all(r == {"thread": "safe"} for r in results)


class TestConfigLoaderHelpers:
    """Test helper functions."""

    def test_get_config_loader_singleton(self):
        """Test getting config loader singleton."""
        # Reset global instance
        import src.core.config.loader

        src.core.config.loader._config_loader = None

        # First call creates instance
        loader1 = get_config_loader()
        assert loader1 is not None

        # Second call returns same instance
        loader2 = get_config_loader()
        assert loader1 is loader2

    @patch("src.core.config.loader.get_config_loader")
    def test_load_config_helper(self, mock_get_loader):
        """Test load_config helper function."""
        mock_loader = Mock()
        mock_loader.load_config.return_value = {"test": "data"}
        mock_get_loader.return_value = mock_loader

        result = load_config("test_config", environment="dev")

        assert result == {"test": "data"}
        mock_get_loader.assert_called_once()
        mock_loader.load_config.assert_called_once_with("test_config", "dev")

    def test_load_config_default_environment(self):
        """Test load_config with default environment."""
        with patch("src.core.config.loader.get_config_loader") as mock_get_loader:
            mock_loader = Mock()
            mock_loader.load_config.return_value = {"test": "data"}
            mock_get_loader.return_value = mock_loader

            load_config("test_config")

            mock_loader.load_config.assert_called_once_with("test_config", "local")
