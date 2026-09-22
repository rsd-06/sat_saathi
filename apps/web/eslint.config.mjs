import nextCoreWebVitals from "eslint-config-next/core-web-vitals";
import nextTypescript from "eslint-config-next/typescript";

// eslint-config-next ships flat-config arrays natively as of the ESLint 9 /
// flat-config-only release line — FlatCompat is for legacy .eslintrc-shaped
// shareable configs and corrupts these (circular plugin references) when
// forced through it.
const config = [...nextCoreWebVitals, ...nextTypescript];

export default config;
