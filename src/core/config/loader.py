"""Configuration loader module for PenEllE.

This module provides a hierarchical configuration system that:
- Loads YAML configuration files
- Supports environment-specific overrides
- Validates configurations against schemas
- Supports hot-reloading for development
"""

import os
import threading
from pathlib import Path
from typing import Any, Dict, Optional, Set

import jsonschema
import yaml
from deepmerge import Merger  # type: ignore
from watchdog.events import FileModifiedEvent, FileSystemEventHandler

from src.core.logging import get_logger

logger = get_logger(__name__)


class ConfigFileHandler(FileSystemEventHandler):
    """Handles file system events for configuration hot-reloading."""

    def __init__(self, loader: "ConfigLoader"):
        self.loader = loader

    def on_modified(self, event: FileModifiedEvent) -> None:
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        if file_path.suffix in [".yaml", ".yml"]:
            config_name = file_path.stem
            if config_name in self.loader._cache:
                logger.info(f"Configuration file modified: {config_name}")
                self.loader.reload_config(config_name)


class ConfigLoader:
    """Hierarchical configuration loader with hot-reloading support."""

    def __init__(self, config_dir: Optional[Path] = None):
        """Initialize the configuration loader.

        Args:
            config_dir: Root directory for configuration files.
                       Defaults to 'config' in project root.
        """
        self.config_dir = config_dir or Path(__file__).parent.parent.parent.parent / "config"
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._schemas: Dict[str, Dict[str, Any]] = {}
        self._observer: Optional[Any] = None  # Type is Observer when not None
        self._lock = threading.RLock()
        self._merger = Merger([(dict, "merge")], ["override"], ["override"])

        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def start_watching(self) -> None:
        """Start watching configuration files for changes."""
        if self._observer is not None:
            return

        from watchdog.observers import Observer

        self._observer = Observer()
        handler = ConfigFileHandler(self)
        self._observer.schedule(handler, str(self.config_dir), recursive=True)
        self._observer.start()
        logger.info(f"Started watching configuration directory: {self.config_dir}")

    def stop_watching(self) -> None:
        """Stop watching configuration files."""
        if self._observer is None:
            return

        self._observer.stop()
        self._observer.join()
        self._observer = None
        logger.info("Stopped watching configuration files")

    def load_config(self, config_name: str, environment: str = "local") -> Dict[str, Any]:
        """Load configuration with environment-specific overrides.

        Args:
            config_name: Name of the configuration file (without extension)
            environment: Environment name (local, test, production)

        Returns:
            Merged configuration dictionary

        Raises:
            FileNotFoundError: If configuration file doesn't exist
            yaml.YAMLError: If YAML parsing fails
            jsonschema.ValidationError: If schema validation fails
        """
        cache_key = f"{config_name}:{environment}"

        with self._lock:
            # Check cache first
            if cache_key in self._cache:
                return self._cache[cache_key].copy()

            # Load base configuration
            base_config = self._load_file(config_name)

            # Load environment-specific override if exists
            env_config_path = self.get_config_path(f"{config_name}.{environment}", required=False)
            if env_config_path and env_config_path.exists():
                env_config = self._load_file(f"{config_name}.{environment}")
                config = self.merge_configs(base_config, env_config)
            else:
                config = base_config

            # Apply environment variables
            config = self._apply_env_vars(config)

            # Validate if schema exists
            if config_name in self._schemas:
                self.validate_config(config, config_name)

            # Cache the result
            self._cache[cache_key] = config

            logger.info(f"Loaded configuration: {config_name} (environment: {environment})")
            return dict(config)

    def reload_config(self, config_name: Optional[str] = None) -> None:
        """Reload a configuration file and clear its cache.

        Args:
            config_name: Name of the configuration to reload. If None, reloads all configs.
        """
        if config_name is None:
            # Reload all configs
            self.reload_all_configs()
        else:
            with self._lock:
                # Get all environments for this config
                environments_to_reload = []
                keys_to_remove = [k for k in self._cache.keys() if k.startswith(f"{config_name}:")]

                for key in keys_to_remove:
                    parts = key.split(":")
                    if len(parts) == 2:
                        environments_to_reload.append(parts[1])
                    del self._cache[key]

                logger.info(f"Reloaded configuration: {config_name}")

                # Reload configs for each environment that was cached
                for env in environments_to_reload:
                    try:
                        self.load_config(config_name, environment=env)
                    except Exception as e:
                        logger.error(f"Failed to reload {config_name}:{env}: {e}")

    def validate_config(self, config: Dict[str, Any], schema_name: str) -> bool:
        """Validate configuration against a schema.

        Args:
            config: Configuration dictionary to validate
            schema_name: Name of the schema to validate against

        Returns:
            True if validation passes

        Raises:
            jsonschema.ValidationError: If validation fails
        """
        if schema_name not in self._schemas:
            schema_path = self.config_dir / "schemas" / f"{schema_name}.json"
            if schema_path.exists():
                with open(schema_path) as f:
                    self._schemas[schema_name] = yaml.safe_load(f)
            else:
                logger.warning(f"No schema found for: {schema_name}")
                return True

        try:
            jsonschema.validate(config, self._schemas[schema_name])
            return True
        except jsonschema.ValidationError as e:
            raise ValueError(f"Configuration validation failed: {e.message}")

    def merge_configs(self, base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two configuration dictionaries.

        Args:
            base: Base configuration
            override: Override configuration

        Returns:
            Merged configuration
        """
        return self._merger.merge(base.copy(), override)  # type: ignore

    def get_config_path(
        self, config_name: str, environment: Optional[str] = None, required: bool = True
    ) -> Optional[Path]:
        """Get the path to a configuration file.

        Args:
            config_name: Name of the configuration file
            environment: Optional environment suffix
            required: Whether to raise error if not found

        Returns:
            Path to configuration file or None if not found

        Raises:
            FileNotFoundError: If required=True and file doesn't exist
        """
        # Try with .yaml extension first, then .yml
        for ext in [".yaml", ".yml"]:
            if environment:
                path = self.config_dir / f"{config_name}.{environment}{ext}"
            else:
                path = self.config_dir / f"{config_name}{ext}"

            if path.exists():
                return path

        if required:
            raise FileNotFoundError(f"Configuration file not found: {config_name}")

        return None

    def _load_file(self, config_name: str) -> Dict[str, Any]:
        """Load a YAML configuration file.

        Args:
            config_name: Name of the configuration file

        Returns:
            Parsed configuration dictionary
        """
        config_path = self.get_config_path(config_name)
        if config_path is None:
            raise FileNotFoundError(f"Configuration file not found: {config_name}")

        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _apply_env_vars(self, config: Any) -> Any:
        """Recursively apply environment variable substitutions.

        Args:
            config: Configuration value (dict, list, or scalar)

        Returns:
            Configuration with environment variables substituted
        """
        if isinstance(config, dict):
            return {k: self._apply_env_vars(v) for k, v in config.items()}
        elif isinstance(config, list):
            return [self._apply_env_vars(item) for item in config]
        elif isinstance(config, str) and config.startswith("${") and config.endswith("}"):
            env_var = config[2:-1]
            default = None

            # Handle ${VAR:-default} syntax
            if ":-" in env_var:
                env_var, default = env_var.split(":-", 1)

            value = os.environ.get(env_var, default)
            if value is None:
                logger.warning(f"Environment variable not set: {env_var}")

            return value
        else:
            return config

    def list_configs(self) -> Set[str]:
        """List all available configuration files.

        Returns:
            Set of configuration names (without extensions)
        """
        configs = set()

        for path in self.config_dir.glob("*.yaml"):
            # Skip environment-specific files
            if "." not in path.stem or path.stem.count(".") == 0:
                configs.add(path.stem)

        for path in self.config_dir.glob("*.yml"):
            if "." not in path.stem or path.stem.count(".") == 0:
                configs.add(path.stem)

        return configs

    def __enter__(self) -> "ConfigLoader":
        """Context manager entry."""
        self.start_watching()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit."""
        self.stop_watching()

    def reload_all_configs(self) -> None:
        """Reload all configurations in cache."""
        logger.info("Reloading all configurations")
        with self._lock:
            # Get all config names and environments from cache
            configs_to_reload = list(self._cache.keys())

            # Clear cache first
            self._cache.clear()

            # Reload each config
            for cache_key in configs_to_reload:
                parts = cache_key.split(":")
                if len(parts) == 2:
                    config_name, environment = parts
                    try:
                        self.load_config(config_name, environment)
                    except Exception as e:
                        logger.error(f"Failed to reload {config_name}:{environment}: {e}")

    def get_all_configs(self, environment: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """Get all loaded configurations.

        Args:
            environment: Filter by specific environment

        Returns:
            Dictionary of configurations
        """
        with self._lock:
            if environment is None:
                # Return all configs with full cache keys
                return dict(self._cache)
            else:
                # Filter by environment and return with config names only
                filtered = {}
                for cache_key, config in self._cache.items():
                    parts = cache_key.split(":")
                    if len(parts) == 2:
                        config_name, env = parts
                        if env == environment:
                            filtered[config_name] = config
                return filtered

    def clear_cache(self) -> None:
        """Clear all cached configurations."""
        with self._lock:
            self._cache.clear()
            logger.info("Configuration cache cleared")

    def watch(self) -> None:
        """Start watching configuration files (alias for start_watching)."""
        self.start_watching()


# Global instance
_config_loader: Optional[ConfigLoader] = None


def get_config_loader() -> ConfigLoader:
    """Get the global configuration loader instance.

    Returns:
        ConfigLoader instance
    """
    global _config_loader
    if _config_loader is None:
        _config_loader = ConfigLoader()
    return _config_loader


def load_config(config_name: str, environment: str = "local") -> Dict[str, Any]:
    """Convenience function to load a configuration.

    Args:
        config_name: Name of the configuration file
        environment: Environment name

    Returns:
        Configuration dictionary
    """
    return get_config_loader().load_config(config_name, environment)
