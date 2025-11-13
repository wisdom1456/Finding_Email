# Backend Consolidation Plan

## Overview
Merge `backend/` and `backend_logic/` folders into the proper architecture as defined in memory bank.

## Phase 1: Analysis & Backup
- [ ] Create full backup of backend/ and backend_logic/ folders
- [ ] Document current file sizes and modification dates
- [ ] Identify which duplicates are most recent/complete

## Phase 2: Utils Consolidation
- [ ] Move backend/utils/data_models.py → utils/data_models.py
- [ ] Move backend/utils/validators.py → utils/validators.py  
- [ ] Move backend/utils/enhanced_file_validator.py → utils/enhanced_file_validator.py
- [ ] Move backend/utils/file_processors/ → utils/file_processors/
- [ ] Move backend_logic/utils/ unique files → utils/
- [ ] Update imports: `from backend.utils` → `from utils`
- [ ] Update imports: `from backend_logic.utils` → `from utils`

## Phase 3: Core Consolidation
- [ ] Keep core/ as primary business logic location
- [ ] Compare and merge duplicates:
  - ai_analyzer.py (keep best version in core/)
  - document_processor.py (keep best version in core/)
  - email_generator.py (keep best version in core/)
  - main_processor.py (already in core/)

## Phase 4: Backend_Logic Unique Files
Move to appropriate locations:
- [ ] backend_logic/cost_calculator.py → utils/cost_calculator.py
- [ ] backend_logic/cost_estimator.py → utils/cost_estimator.py
- [ ] backend_logic/cost_exporter.py → utils/cost_exporter.py
- [ ] backend_logic/cost_session_manager.py → utils/cost_session_manager.py
- [ ] backend_logic/ai/ → core/ai/
- [ ] backend_logic/email_generation/ → services/email_generation/

## Phase 5: Services Consolidation
- [ ] backend_logic/async_processor.py → services/ (compare with existing)
- [ ] backend_logic/audio_processor.py → services/ (compare with existing)
- [ ] backend_logic/video_processor.py → services/ (compare with existing)

## Phase 6: Config Consolidation
- [ ] backend/config/ → config/backend/
- [ ] backend_logic/config.py → config/settings.py
- [ ] Update all config imports

## Phase 7: Test Consolidation
- [ ] backend/tests/ → tests/backend/
- [ ] backend_logic/tests/ → tests/backend_logic/ (temporarily)
- [ ] Merge test files and remove duplicates
- [ ] Update test imports

## Phase 8: Import Updates (138 references)
Update all imports across codebase:
- [ ] `from backend.utils` → `from utils`
- [ ] `from backend_logic.utils` → `from utils`
- [ ] `from backend_logic.config` → `from config.settings`
- [ ] `from backend_logic.ai` → `from core.ai`
- [ ] `from backend_logic` → appropriate new location
- [ ] `from backend` → appropriate new location

## Phase 9: Cleanup
- [ ] Remove backend_logic/email_generator_backup.py
- [ ] Remove backend_logic/email_generator.py.bak
- [ ] Delete empty backend/ folder
- [ ] Delete empty backend_logic/ folder
- [ ] Remove any .DS_Store files

## Phase 10: Validation
- [ ] Run `python app.py` to test startup
- [ ] Run test suite
- [ ] Verify all imports resolved
- [ ] Check CI/CD pipeline passes

## Phase 11: Documentation
- [ ] Update memory-bank/systemPatterns.md
- [ ] Update memory-bank/techContext.md
- [ ] Update memory-bank/activeContext.md
- [ ] Update README.md with new structure

## Risk Mitigation
1. Full backup before starting
2. Git commit after each phase
3. Test application after each major change
4. Keep mapping document of all file moves
5. Use search/replace with regex for import updates

## Expected Outcomes
- Single source of truth for each file
- Clear architectural boundaries
- Simplified import structure
- Easier maintenance and development
- Aligned with documented architecture