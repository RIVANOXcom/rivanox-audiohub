# Localization policy

**All repository and project communication is in English only.**

App UI languages: `en`, `de`, `es`, `fr`, `it`. Translation resources are maintained as separate locale files with the same message keys. English is the canonical fallback. The UI detects browser language on first use and allows manual override.

Requirements:

- Never put UI labels directly into application logic when a translation key is available.
- Fallback to English for incomplete or unsupported locales.
- Escape/untrusted content; translations are plain text, not HTML.
- Keep error messages represented by stable keys across the local API.
- Test translation-key parity and ensure controls have translated accessibility labels.
- Product claims and privacy notices must remain accurate in every language.
