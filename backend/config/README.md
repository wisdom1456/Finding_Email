# Configuration-Driven Legal Document Analysis System

## Overview

The Legal Document Analysis Portal now supports a flexible, configuration-driven architecture that allows different AI prompts and templates to be used based on legal practice areas. This system enables customization of the analysis pipeline without modifying code.

## Architecture

### Core Components

1. **EmailGeneratorV2** - Generates legal findings letters using configurable templates and prompts
2. **AIAnalyzer** - Performs document analysis using configurable AI prompts
3. **Configuration Files** - YAML files containing practice area-specific prompts and settings

### Configuration Flow

```
Configuration YAML File
        ↓
EmailGeneratorV2 ← shared config → AIAnalyzer
        ↓                              ↓
Template Rendering              Document Analysis
        ↓                              ↓
    Findings Letter              Legal Assessment
```

## Configuration File Structure

Configuration files are stored in `backend/config/templates/` and follow this structure:

```yaml
# Template Configuration
template_path: "backend/assets/templates/findings_email.jinja2"

# AI Personas - Define different AI analysis personalities
personas:
  attorney: "You are a seasoned Florida litigation attorney..."
  paralegal: "You are a UNIFIED_LEGAL_ADVISOR paralegal..."

# Analysis Sections - Prompts for different analysis stages
sections:
  intake_analysis: "Detailed prompt for intake form analysis..."
  case_document_analysis: "Detailed prompt for case document analysis..."
  media_summarization: "Detailed prompt for media content summarization..."
  final_assessment: "Detailed prompt for final legal assessment..."
  # ... additional sections

# Email Generation Formatting
formatting:
  greeting: "Dear {client_name}:"
  closing: "Thank you,\nChevonne Christian, Esq.\nCivil Division Attorney"
  signature: "We're committed to achieving the best possible outcome for your case."
```

## Usage

### Command Line Interface

```bash
python backend_logic/main_processor.py \
  --intake_form path/to/intake.pdf \
  --case_documents path/to/docs/ \
  --output_dir ./output \
  --config_path backend/config/templates/contractor_dispute_config.yaml
```

### Programmatic Usage

```python
from backend_logic.email_generator import EmailGeneratorV2
from backend_logic.ai_analyzer import AIAnalyzer
from openai import OpenAI

# Initialize with configuration
config_path = "backend/config/templates/contractor_dispute_config.yaml"
client = OpenAI(api_key="your-api-key")

email_generator = EmailGeneratorV2(client, config_path=config_path)
ai_analyzer = AIAnalyzer(client, doc_processor, config_path=config_path)

# Components automatically load and use the configuration
```

### Streamlit Integration

The main `process_case_documents()` function in `main_processor.py` accepts a `config_path` parameter:

```python
await process_case_documents(
    output_dir="./output",
    config_path="backend/config/templates/contractor_dispute_config.yaml"
)
```

## Available Configurations

### contractor_dispute_config.yaml

Specialized for contractor dispute cases with:
- Florida construction law focus
- Property damage analysis emphasis
- Contractor liability assessment
- Warranty and habitability evaluation

## Creating New Configurations

### Step 1: Create Configuration File

Create a new YAML file in `backend/config/templates/`:

```yaml
# Example: personal_injury_config.yaml
template_path: "backend/assets/templates/findings_email.jinja2"

personas:
  attorney: |
    You are a seasoned Florida personal injury attorney with 15+ years of experience...
  paralegal: |
    You are a UNIFIED_LEGAL_ADVISOR paralegal specializing in personal injury cases...

sections:
  intake_analysis: |
    Analyze this personal injury intake form focusing on:
    - Incident details and timeline
    - Injury severity and medical treatment
    - Liability and insurance coverage
    ...

  case_document_analysis: |
    Review case documents for personal injury claims:
    - Medical records and treatment history
    - Police reports and incident documentation
    - Insurance correspondence and coverage
    ...

# ... continue with other sections
```

### Step 2: Test Configuration

```python
# Test the new configuration
python3 -c "
from backend_logic.email_generator import EmailGeneratorV2
from backend_logic.ai_analyzer import AIAnalyzer
from backend_logic.document_processor import DocumentProcessor

config_path = 'backend/config/templates/personal_injury_config.yaml'
# Test initialization
email_gen = EmailGeneratorV2(None, config_path=config_path)
ai_analyzer = AIAnalyzer(None, DocumentProcessor(), config_path=config_path)
print('✅ Configuration loaded successfully')
"
```

### Step 3: Deploy Configuration

Use the new configuration by specifying its path in any of the usage methods above.

## Fallback Behavior

### Graceful Degradation

- If no configuration is specified, components use built-in default prompts
- If configuration file is missing or invalid, fallback to defaults with warning
- Individual sections can fall back to defaults if missing from configuration

### Error Handling

```python
# Components handle configuration errors gracefully
try:
    email_generator = EmailGeneratorV2(client, config_path="missing_config.yaml")
    # Logs warning and uses defaults
except Exception:
    # Configuration errors don't break the system
    pass
```

## Configuration Validation

### Required Fields

- `template_path`: Path to Jinja2 template file
- `personas`: Must contain at least 'attorney' persona
- `sections`: Must contain core analysis sections

### Optional Fields

- `formatting`: Email formatting preferences
- Additional personas beyond 'attorney'
- Practice area-specific sections

## Best Practices

### 1. Configuration Organization

```
backend/config/templates/
├── contractor_dispute_config.yaml
├── personal_injury_config.yaml
├── employment_law_config.yaml
├── family_law_config.yaml
└── criminal_defense_config.yaml
```

### 2. Prompt Engineering

- Keep prompts specific to the practice area
- Include relevant Florida statutes and legal standards
- Maintain consistent tone and terminology
- Test prompts with sample cases

### 3. Version Control

- Track configuration changes in git
- Use descriptive commit messages for prompt updates
- Consider configuration versioning for major changes

### 4. Testing

- Test each new configuration with sample cases
- Validate prompt effectiveness and accuracy
- Monitor AI output quality and consistency

## Integration Points

### Main Processor

The `main_processor.py` passes configuration to both components:

```python
ai_analyzer = AIAnalyzer(openai_client, doc_processor, config_path=config_path)
email_generator = EmailGeneratorV2(openai_client, config_path=config_path)
```

### Modular AI Components

The new modular AI architecture in `backend_logic/ai/` is designed to support configuration-driven approaches:

- `ConfigManager` - Centralized configuration loading
- `PromptBuilder` - Dynamic prompt construction from configuration
- `AIAnalyzerRefactored` - Modular analysis using configuration

## Migration Guide

### From Hardcoded to Configuration

1. **Identify Hardcoded Prompts**: Find prompt strings in your code
2. **Extract to Configuration**: Move prompts to YAML configuration files
3. **Update Component Initialization**: Add `config_path` parameter
4. **Test Functionality**: Verify behavior matches original implementation
5. **Deploy New Configuration**: Use configuration files in production

### Backward Compatibility

- Existing code without configuration parameters continues to work
- Default prompts maintain original behavior
- Gradual migration path from hardcoded to configuration-driven

## Troubleshooting

### Common Issues

1. **Configuration Not Loading**
   - Check file path and permissions
   - Validate YAML syntax
   - Review error logs for details

2. **Prompts Not Working**
   - Verify section names match expected keys
   - Check prompt formatting and structure
   - Test with simple prompts first

3. **Template Errors**
   - Ensure template_path points to valid Jinja2 file
   - Verify template variables match configuration
   - Check template syntax

### Debug Mode

Enable verbose logging to debug configuration issues:

```python
import logging
logging.getLogger().setLevel(logging.DEBUG)

# Components will log detailed configuration loading information
```

## Performance Considerations

- Configuration files are loaded once at component initialization
- No performance impact during analysis processing
- Large configuration files may increase startup time slightly
- Consider configuration caching for high-volume usage

## Security Notes

- Configuration files may contain sensitive prompts or templates
- Store configuration files securely with appropriate access controls
- Avoid hardcoding API keys or credentials in configuration files
- Use environment variables for sensitive configuration

## Future Enhancements

### Planned Features

1. **Dynamic Configuration Reloading**: Update configurations without restart
2. **Configuration Templates**: Base configurations for easy customization
3. **Multi-Language Support**: Configurations for different languages
4. **Configuration Validation Schema**: Formal validation of configuration structure
5. **Configuration UI**: Web interface for editing configurations

### Extension Points

- Custom prompt processors
- Configuration inheritance and overrides
- Practice area-specific validation rules
- Integration with external prompt libraries
