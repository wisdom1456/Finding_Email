# Configuration Consolidation Plan

## Overview

This document provides a comprehensive plan for consolidating the fragmented configuration system into a single, unified configuration module. The current system has multiple competing configuration approaches that create maintenance complexity and path dependencies.

## Current Configuration Fragmentation Analysis

### 1.1 Identified Configuration Files

| File | Purpose | Type | Status | Issues |
|------|---------|------|---------|---------|
| [`config/default.py`](config/default.py:1) | **CANONICAL** Pydantic settings | Environment/API | **KEEP** | Modern, type-safe approach |
| [`core/config_manager.py`](core/config_manager.py:1) | YAML config loader | YAML/Templates | MERGE | Duplicate functionality |
| [`core/config_and_template_loader.py`](core/config_and_template_loader.py:1) | YAML + template loader | YAML/Templates | MERGE | Redundant with config_manager |
| [`core/configuration_manager.py`](core/configuration_manager.py:1) | Yet another YAML loader | YAML/Templates | MERGE | Third duplicate implementation |

### 1.2 Configuration Fragmentation Issues

**Multiple YAML Loaders**:
- 3 separate implementations of YAML configuration loading
- Inconsistent error handling and logging approaches
- Duplicate template directory discovery logic
- Hardcoded paths that will break after refactor

**Path Dependencies**:
```python
# Hardcoded paths that break after refactor
"backend/config/templates/universal_legal_config.yaml"
"backend/assets/templates"
"backend/config"
```

**Inconsistent APIs**:
```python
# config_manager.py
config_manager.get_prompt(section, fallback)

# config_and_template_loader.py  
loader.load_configuration(config_path)

# configuration_manager.py
manager.get_config(key, default)
```

## 2. Target Unified Configuration Architecture

### 2.1 Unified Configuration Module Structure

```
src/legal_portal/config/
├── __init__.py                    # Public API exports
├── settings.py                    # Pydantic settings (from config/default.py)
├── yaml_config.py                 # Consolidated YAML configuration
├── template_discovery.py          # Template directory management
├── prompts/                       # YAML prompt configurations
│   ├── universal_legal_config.yaml
│   ├── persona_configs.yaml
│   └── formatting_rules.yaml
└── templates/                     # Jinja2 templates
    ├── findings_email.jinja2
    ├── document_appendix.jinja2
    └── template_utils.py
```

### 2.2 Consolidated Configuration Class Design

```python
# src/legal_portal/config/__init__.py
from .settings import Settings, get_settings
from .yaml_config import UnifiedConfigManager

# Single point of access
__all__ = ["Settings", "get_settings", "UnifiedConfigManager", "get_config_manager"]

def get_config_manager() -> UnifiedConfigManager:
    """Get unified configuration manager instance."""
    return UnifiedConfigManager()
```

## 3. Unified Configuration Implementation

### 3.1 Enhanced Settings Module

**File**: `src/legal_portal/config/settings.py` (enhanced from [`config/default.py`](config/default.py:1))

```python
"""
Unified Configuration Management Module

Provides type-safe, centralized configuration system combining:
- Pydantic environment variable settings  
- YAML configuration management
- Template directory discovery
- Path resolution for new package structure
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional, Union, Any

from dotenv import load_dotenv
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings

# Load environment variables
load_dotenv()

class Settings(BaseSettings):
    """Enhanced settings with unified configuration support."""
    
    # ... existing Pydantic settings from config/default.py ...
    
    # NEW: Configuration directory settings
    config_root: Optional[str] = Field(
        None,
        alias="CONFIG_ROOT",
        description="Root directory for configuration files"
    )
    
    template_directory: Optional[str] = Field(
        None, 
        alias="TEMPLATE_DIRECTORY",
        description="Directory containing Jinja2 templates"
    )
    
    yaml_config_path: Optional[str] = Field(
        None,
        alias="YAML_CONFIG_PATH", 
        description="Path to YAML configuration file"
    )
    
    @property
    def package_root(self) -> Path:
        """Get the package root directory."""
        return Path(__file__).parent.parent.parent  # src/legal_portal/
    
    @property
    def project_root(self) -> Path:
        """Get the project root directory.""" 
        return self.package_root.parent.parent  # Root of project
    
    @property
    def config_directory(self) -> Path:
        """Get configuration directory path."""
        if self.config_root:
            return Path(self.config_root)
        return self.package_root / "config"
    
    @property
    def default_template_directory(self) -> Path:
        """Get default template directory."""
        if self.template_directory:
            return Path(self.template_directory)
        return self.config_directory / "templates"
    
    @property
    def default_yaml_config_path(self) -> Path:
        """Get default YAML config path."""
        if self.yaml_config_path:
            return Path(self.yaml_config_path)
        return self.config_directory / "prompts" / "universal_legal_config.yaml"
```

### 3.2 Unified YAML Configuration Manager

**File**: `src/legal_portal/config/yaml_config.py`

```python
"""
Unified YAML Configuration Manager

Consolidates functionality from:
- core/config_manager.py
- core/config_and_template_loader.py  
- core/configuration_manager.py
"""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .settings import get_settings

logger = logging.getLogger(__name__)

class UnifiedConfigManager:
    """
    Unified configuration manager combining all YAML config functionality.
    
    This class consolidates the fragmented configuration management
    functionality into a single, coherent interface.
    """
    
    def __init__(self, config_path: Optional[str] = None):
        """Initialize unified config manager."""
        self.settings = get_settings()
        self.config_path = config_path or str(self.settings.default_yaml_config_path)
        self.config: Dict[str, Any] = {}
        self.template_env: Optional[Environment] = None
        
        # Load configuration
        self._load_yaml_configuration()
        self._setup_template_environment()
    
    def _load_yaml_configuration(self) -> None:
        """Load YAML configuration with enhanced error handling."""
        try:
            config_path = Path(self.config_path)
            
            if not config_path.exists():
                logger.warning(f"YAML config not found: {config_path}, using defaults")
                self.config = self._get_default_config()
                return
            
            with open(config_path, encoding="utf-8") as f:
                self.config = yaml.safe_load(f) or {}
                
            logger.info(f"YAML configuration loaded: {config_path}")
            
        except yaml.YAMLError as e:
            logger.error(f"YAML parsing failed: {e}")
            self.config = self._get_default_config()
        except Exception as e:
            logger.error(f"Configuration loading failed: {e}")
            self.config = self._get_default_config()
    
    def _setup_template_environment(self) -> None:
        """Setup Jinja2 template environment."""
        try:
            template_dir = self.settings.default_template_directory
            
            if not template_dir.exists():
                logger.warning(f"Template directory not found: {template_dir}")
                self.template_env = None
                return
            
            self.template_env = Environment(
                loader=FileSystemLoader(str(template_dir)),
                autoescape=select_autoescape(["html", "xml"])
            )
            
            logger.info(f"Template environment initialized: {template_dir}")
            
        except Exception as e:
            logger.error(f"Template environment setup failed: {e}")
            self.template_env = None
    
    # Unified API methods consolidating all config managers
    def get_prompt(self, section: str, fallback: str = "") -> str:
        """Get prompt from configuration (from config_manager.py)."""
        return self.config.get("sections", {}).get(section, fallback)
    
    def get_persona(self, persona_name: str, fallback: str = "") -> str:
        """Get persona from configuration (from config_manager.py)."""
        return self.config.get("personas", {}).get(persona_name, fallback)
    
    def get_formatting_rule(self, rule_name: str, fallback: str = "") -> str:
        """Get formatting rule (from config_manager.py)."""
        return self.config.get("formatting", {}).get(rule_name, fallback)
    
    def get_config(self, key: str = None, default: Any = None) -> Any:
        """Get config value with dot notation (from configuration_manager.py)."""
        if key is None:
            return self.config
        
        # Support dot notation for nested keys
        keys = key.split(".")
        value = self.config
        
        try:
            for k in keys:
                value = value[k]
            return value
        except (KeyError, TypeError):
            return default
    
    def get_jinja_env(self) -> Optional[Environment]:
        """Get Jinja2 environment (from config_and_template_loader.py)."""
        return self.template_env
    
    def get_template_path(self, template_name: str) -> Optional[Path]:
        """Get full path to template file."""
        template_dir = self.settings.default_template_directory
        template_path = template_dir / template_name
        
        if template_path.exists():
            return template_path
        return None
    
    def is_configured(self) -> bool:
        """Check if configuration is properly loaded."""
        return bool(self.config and self.template_env)
    
    def reload_configuration(self, new_config_path: Optional[str] = None) -> None:
        """Reload configuration from file."""
        if new_config_path:
            self.config_path = new_config_path
        
        self._load_yaml_configuration()
        self._setup_template_environment()
        
        logger.info("Configuration reloaded successfully")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Provide default configuration when YAML loading fails."""
        return {
            "sections": {},
            "personas": {
                "default": "You are a helpful legal document analysis assistant."
            },
            "formatting": {
                "default": "Use clear, professional formatting."
            }
        }

# Global instance
_config_manager_instance: Optional[UnifiedConfigManager] = None

def get_config_manager() -> UnifiedConfigManager:
    """Get or create global configuration manager instance."""
    global _config_manager_instance
    if _config_manager_instance is None:
        _config_manager_instance = UnifiedConfigManager()
    return _config_manager_instance
```

## 4. Migration Strategy

### 4.1 Phase 1: Create Unified Configuration Module

```bash
# 1. Create new unified configuration structure (part of refactor)
mkdir -p src/legal_portal/config/{prompts,templates}

# 2. Create unified configuration files
# (Will be created as part of main refactor)

# 3. Move existing YAML configs and templates
git mv config/auth_config.yaml src/legal_portal/config/prompts/
# Note: backend/config/templates will be moved in main refactor
```

### 4.2 Phase 2: Update Import Statements

**Search and Replace Operations**:

```python
# Replace fragmented config imports
FROM: from core.config_manager import ConfigManager
TO:   from legal_portal.config import get_config_manager

FROM: from core.config_and_template_loader import ConfigAndTemplateLoader  
TO:   from legal_portal.config import get_config_manager

FROM: from core.configuration_manager import ConfigurationManager
TO:   from legal_portal.config import get_config_manager

FROM: from config.default import get_settings
TO:   from legal_portal.config import get_settings
```

### 4.3 Phase 3: Update Usage Patterns

**Standardize Configuration Access**:

```python
# OLD: Multiple different patterns
config_manager = ConfigManager()
loader = ConfigAndTemplateLoader()
manager = ConfigurationManager()

# NEW: Single unified pattern
config_manager = get_config_manager()
settings = get_settings()
```

## 5. Integration with Refactor Plan

### 5.1 Configuration Files Movement (from CONCRETE_REFACTOR_PLAN.md)

```bash
# Enhanced configuration migration
git mv config/default.py src/legal_portal/config/settings.py

# Move YAML configurations
if [ -d "backend/config" ]; then
    find backend/config -name "*.yaml" -exec git mv {} src/legal_portal/config/prompts/ \;
    find backend/config -name "*.yml" -exec git mv {} src/legal_portal/config/prompts/ \;
fi

# Move template files  
if [ -d "backend/assets/templates" ]; then
    git mv backend/assets/templates/* src/legal_portal/config/templates/
elif [ -d "assets/templates" ]; then
    git mv assets/templates/* src/legal_portal/config/templates/
fi
```

### 5.2 Import Path Updates

The refactor plan already includes import path updates. This configuration plan adds:

```python
# Additional configuration-specific import updates
def update_config_imports(file_path):
    """Update configuration imports in a file."""
    mappings = {
        # Unified config manager imports
        r'from core\.config_manager import ConfigManager': 
            'from legal_portal.config import get_config_manager',
        
        r'from core\.config_and_template_loader import ConfigAndTemplateLoader':
            'from legal_portal.config import get_config_manager',
            
        r'from core\.configuration_manager import ConfigurationManager':
            'from legal_portal.config import get_config_manager',
        
        # Settings imports  
        r'from config\.default import': 
            'from legal_portal.config.settings import',
        
        # Usage pattern updates
        r'ConfigManager\(\)': 'get_config_manager()',
        r'ConfigAndTemplateLoader\(\)': 'get_config_manager()',
        r'ConfigurationManager\(\)': 'get_config_manager()',
    }
```

## 6. Backwards Compatibility Strategy

### 6.1 Deprecation Wrapper

Create temporary compatibility layer during transition:

```python
# src/legal_portal/config/deprecated.py
"""
Backwards compatibility wrappers for old configuration classes.
These will be removed after migration is complete.
"""

import warnings
from .yaml_config import get_config_manager

class ConfigManager:
    """Deprecated: Use get_config_manager() instead."""
    
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "ConfigManager is deprecated. Use get_config_manager() instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self._manager = get_config_manager()
    
    def get_prompt(self, section: str, fallback: str = "") -> str:
        return self._manager.get_prompt(section, fallback)

# Similar wrappers for other deprecated classes...
```

### 6.2 Migration Timeline

1. **Week 1**: Create unified configuration module
2. **Week 2**: Update core modules to use unified config
3. **Week 3**: Update application code and tests
4. **Week 4**: Remove deprecated configuration files
5. **Week 5**: Remove backwards compatibility wrappers

## 7. Testing Strategy

### 7.1 Configuration Tests

```python
# tests/unit/config/test_unified_config.py
def test_unified_config_manager():
    """Test unified configuration manager functionality."""
    manager = get_config_manager()
    
    # Test prompt access
    assert isinstance(manager.get_prompt("default"), str)
    
    # Test persona access  
    assert isinstance(manager.get_persona("default"), str)
    
    # Test template environment
    env = manager.get_jinja_env()
    assert env is not None
    
    # Test configuration status
    assert manager.is_configured()

def test_settings_integration():
    """Test settings and config manager integration."""
    settings = get_settings()
    manager = get_config_manager()
    
    # Verify path resolution
    assert settings.config_directory.exists()
    assert settings.default_template_directory.exists()
```

### 7.2 Migration Validation

```python
# Validation script
def validate_configuration_migration():
    """Validate that configuration migration was successful."""
    
    # 1. Verify unified config works
    from legal_portal.config import get_config_manager, get_settings
    
    manager = get_config_manager()
    settings = get_settings()
    
    assert manager.is_configured()
    assert settings.openai_api_key  # Environment var access
    
    # 2. Verify no imports of old config classes
    check_for_deprecated_imports()
    
    # 3. Verify template loading works
    env = manager.get_jinja_env()
    template = env.get_template("findings_email.jinja2")
    assert template is not None
    
    print("✅ Configuration migration validation passed")
```

## 8. Benefits of Unified Configuration

### 8.1 Immediate Benefits

1. **Single Source of Truth**: One configuration system instead of 4
2. **Type Safety**: Pydantic validation for all settings
3. **Path Independence**: No hardcoded backend/ paths
4. **Consistent API**: Unified interface for all configuration access
5. **Better Testing**: Mockable configuration for unit tests

### 8.2 Long-term Benefits

1. **Maintainability**: Single configuration codebase to maintain
2. **Extensibility**: Easy to add new configuration sources
3. **Documentation**: Self-documenting through Pydantic models
4. **Performance**: Single configuration load per application start
5. **Security**: Centralized secret management

## 9. Risk Mitigation

### 9.1 Migration Risks

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| Import errors | High | Medium | Comprehensive import mapping and testing |
| Configuration loss | High | Low | Backup existing configs before migration |
| Template loading failure | Medium | Low | Validate template paths during migration |
| Performance regression | Low | Low | Lazy loading and caching strategies |

### 9.2 Rollback Procedures

```bash
# Rollback configuration changes
git checkout HEAD~1 -- src/legal_portal/config/
git checkout HEAD~1 -- core/config*.py

# Restore original imports
git checkout HEAD~1 -- core/
git checkout HEAD~1 -- app/
```

This unified configuration system eliminates fragmentation while providing a robust, type-safe foundation for the consolidated application architecture.