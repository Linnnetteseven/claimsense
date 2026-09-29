module.exports = {
  root: true,
  env: { browser: true, es2021: true },
  ignorePatterns: ["dist"],
  extends: [
    "eslint:recommended",
    "plugin:react/recommended",
    "plugin:react-hooks/recommended",
  ],
  parserOptions: {
    ecmaVersion: "latest",
    sourceType: "module",
    ecmaFeatures: { jsx: true },
  },
  settings: { react: { version: "detect" } },
  plugins: ["react-refresh"],
  rules: {
    "react/prop-types": "warn",
    "react/react-in-jsx-scope": "off",
    "react-refresh/only-export-components": [
      "warn",
      { allowConstantExport: true },
    ],
  },
  overrides: [
    {
      // Node-side build config.
      files: ["*.config.js", ".eslintrc.cjs"],
      env: { node: true, browser: false },
    },
  ],
};
