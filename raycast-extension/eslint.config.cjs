const raycast = require("@raycast/eslint-config");
module.exports = [
  ...raycast,
  {
    plugins: { "react-hooks": require("eslint-plugin-react-hooks") },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
    },
  },
  { ignores: ["dist/**", "node_modules/**", "raycast-env.d.ts"] },
  {
    rules: {
      "@raycast/prefer-title-case": [
        "warn",
        { extraFixedCaseWords: ["ssync", "stdout", "stderr"] },
      ],
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
];
