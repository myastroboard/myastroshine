import js from '@eslint/js';
import globals from 'globals';
import reactHooks from 'eslint-plugin-react-hooks';
import reactRefresh from 'eslint-plugin-react-refresh';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist', 'node_modules'] },
  js.configs.recommended,
  tseslint.configs.recommended,
  reactRefresh.configs.vite,
  {
    files: ['**/*.{ts,tsx}'],
    languageOptions: {
      ecmaVersion: 2022,
      globals: globals.browser,
    },
    plugins: {
      'react-hooks': reactHooks,
    },
    rules: {
      // Classic hooks rules only. eslint-plugin-react-hooks v7 also ships the
      // React Compiler ruleset; enable it when/if this app adopts the compiler.
      'react-hooks/rules-of-hooks': 'error',
      'react-hooks/exhaustive-deps': 'warn',
      // AGENTS.md section 5: no HTML-string sinks.
      'no-restricted-properties': [
        'error',
        { object: 'element', property: 'innerHTML', message: 'Use textContent or React nodes.' },
      ],
    },
  },
);
