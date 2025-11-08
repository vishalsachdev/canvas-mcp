# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Comprehensive documentation enhancements
- CONTRIBUTING.md with detailed contribution guidelines
- CODE_OF_CONDUCT.md for community standards
- Enhanced troubleshooting FAQ in README
- Visual setup guide section with placeholders for screenshots/GIFs
- Feature comparison table in README
- Quick start guide for 5-minute setup

### Changed
- Enhanced README with additional badges
- Improved documentation structure

## [1.0.3] - 2024-11-08

### Added
- Validation for `maxPeerReviewPoints` configuration parameter
- Bulk discussion grading API for token-efficient grading operations
- Concurrent processing with rate limiting for bulk operations

### Fixed
- All PR feedback addressed - Direct API calls, concurrent processing, validation
- Configuration validation for peer review grading

### Documentation
- Search canvas tools documentation added to tools/README.md

## [1.0.2] - 2024-11-05

### Added
- Code execution API (TypeScript) for bulk operations
- `search_canvas_tools` MCP tool for discovering available operations
- Bulk grading functionality with 99.7% token reduction
- Discussion grading with peer review support

### Features
- Direct Canvas API calls from code execution environment
- Token-efficient bulk processing (90 submissions: 1.35M → 3.5K tokens)
- Dry run mode for previewing grades
- Comprehensive grading analytics

### Documentation
- Bulk grading example with detailed walkthrough
- Code API file structure documentation
- Discovery tool usage guide

## [1.0.1] - 2024-10-28

### Added
- Student-focused MCP tools
  - `get_my_upcoming_assignments` - Personal assignment tracking
  - `get_my_todo_items` - Canvas TODO list
  - `get_my_submission_status` - Submission tracking
  - `get_my_course_grades` - Grade monitoring
  - `get_my_peer_reviews_todo` - Peer review management

### Documentation
- Student Guide (STUDENT_GUIDE.md)
- Educator Guide (EDUCATOR_GUIDE.md)
- Separate guides for different user types

### Changed
- Improved tool organization by audience (students vs educators)
- Enhanced privacy documentation

## [1.0.0] - 2024-10-15

### Added
- Modular architecture refactor
  - Core utilities in `src/canvas_mcp/core/`
  - Tool implementations in `src/canvas_mcp/tools/`
  - Resources in `src/canvas_mcp/resources/`
- Modern Python package structure with `pyproject.toml`
- FastMCP framework integration
- Comprehensive tool categories:
  - Course management
  - Assignment handling
  - Discussion forums
  - Peer reviews
  - Rubrics
  - Student analytics
  - Messaging
- FERPA-compliant data anonymization
  - Source-level anonymization
  - Automatic email masking
  - Local-only processing
  - De-anonymization mapping

### Features
- Smart caching system (bidirectional course code ↔ ID mapping)
- Flexible course identifiers (IDs, course codes, SIS IDs)
- ISO 8601 date standardization
- Async architecture with connection pooling
- Parameter validation with Union/Optional type handling
- Comprehensive analytics tools

### Documentation
- Complete tool documentation (tools/README.md)
- Development guide (docs/CLAUDE.md)
- Best practices guide
- Course documentation template

### Changed
- Migrated from monolithic to modular architecture
- Improved error handling (JSON responses)
- Enhanced privacy controls
- Better tool organization and naming

### Deprecated
- Legacy monolithic implementation (moved to archive/)

## [0.9.0] - 2024-09-20

### Added
- Initial public release
- Basic Canvas API integration
- Core MCP server functionality
- Essential educator tools
- Basic documentation

### Features
- Course listing
- Assignment management
- Basic grading support
- Discussion forum access
- Simple configuration

## Version History Summary

- **1.0.x**: Production-ready with code execution API, student tools, comprehensive documentation
- **0.9.x**: Initial public release with basic functionality

---

## How to Read This Changelog

### Types of Changes

- **Added**: New features
- **Changed**: Changes to existing functionality
- **Deprecated**: Soon-to-be removed features
- **Removed**: Removed features
- **Fixed**: Bug fixes
- **Security**: Security vulnerability fixes
- **Documentation**: Documentation-only changes

### Version Numbers

Following [Semantic Versioning](https://semver.org/):
- **MAJOR** (1.x.x): Breaking changes
- **MINOR** (x.1.x): New features, backward compatible
- **PATCH** (x.x.1): Bug fixes, backward compatible

### Links

- Compare versions: `https://github.com/vishalsachdev/canvas-mcp/compare/v1.0.2...v1.0.3`
- View release: `https://github.com/vishalsachdev/canvas-mcp/releases/tag/v1.0.3`

## Contributing

When making changes:
1. Add entries under `[Unreleased]`
2. Use appropriate category (Added, Changed, Fixed, etc.)
3. Write clear, user-focused descriptions
4. Link to issues/PRs when relevant
5. Move to version section during release

For more information, see [CONTRIBUTING.md](CONTRIBUTING.md).
