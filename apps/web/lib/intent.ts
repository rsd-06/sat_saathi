/**
 * Keyword intent classifier — the deliberately dumb stand-in the spec calls
 * for at the `understand` step. The real classifier replaces this behind the
 * same signature; nothing downstream should depend on how the label was found.
 *
 * Keywords are listed per language because the officer may type in any of the
 * four, regardless of the interface language.
 *
 * Matching is token-anchored, never substring-anywhere. A naive `includes()`
 * once matched "பின்" (after) inside "பின்வருமாறு" (as follows) and routed an
 * unrelated Tamil sentence to change detection. Tamil, Hindi and Bengali are
 * agglutinative, so a keyword may be a token's *prefix* — but it must start
 * the token, and bare positional words (before/after/முன்/பின்/पहले/बाद) are
 * excluded entirely: they carry no intent on their own and appear inside far
 * too many compounds.
 */

export type Intent =
  | "water_extent"
  | "vegetation"
  | "change"
  | "built_up"
  | "land_cover";

export type IntentMatch = {
  intent: Intent;
  /** Sum of matched keyword lengths — longer terms are more specific. */
  score: number;
  matched: string[];
};

const KEYWORDS: Record<Exclude<Intent, "land_cover">, string[]> = {
  water_extent: [
    "water", "flood", "flooded", "flooding", "inundated", "inundation",
    "submerged", "river", "lake", "waterlogged",
    "पानी", "बाढ़", "जलमग्न", "नदी", "झील",
    "நீர்", "வெள்ள", "மூழ்க", "ஆறு", "ஏரி",
    "জল", "বন্যা", "জলমগ্ন", "নদী", "প্লাবিত",
  ],
  vegetation: [
    "crop", "crops", "paddy", "rice", "vegetation", "farm", "farmland",
    "field", "fields", "harvest", "yield", "ndvi", "canopy", "greenery",
    "फसल", "धान", "खेत", "हरियाली", "वनस्पति",
    "பயிர்", "நெல்", "வயல்", "தாவர", "பசுமை",
    "ফসল", "ধান", "ক্ষেত", "সবুজ", "গাছপালা",
  ],
  change: [
    // "before"/"after" alone are not change indicators; the phrase is.
    "change", "changed", "changes", "difference", "differences", "compare",
    "comparison", "before and after", "between these", "between the two",
    "बदल", "परिवर्तन", "अंतर", "तुलना",
    "மாற்ற", "மாறி", "மாறு", "வேறுபாடு", "ஒப்பிட",
    "পরিবর্তন", "বদল", "পার্থক্য", "তুলনা",
  ],
  built_up: [
    "built", "built-up", "urban", "building", "buildings", "settlement",
    "city", "town", "road", "roads", "infrastructure",
    "निर्मित", "शहर", "इमारत", "बस्ती", "सड़क",
    "கட்டிட", "நகர", "குடியிருப்", "சாலை",
    "নির্মিত", "শহর", "বাড়ি", "বসতি", "রাস্তা",
  ],
};

/** Split on whitespace and punctuation, keeping letters of every script. */
function tokenize(text: string): string[] {
  return text
    .toLowerCase()
    .split(/[\s.,;:!?'"()[\]{}/\\|<>@#$%^&*+=~`_—–-]+/u)
    .filter(Boolean);
}

function matches(keyword: string, tokens: string[], haystack: string) {
  // Multi-word keywords are phrases; check them against the whole string.
  if (keyword.includes(" ")) return haystack.includes(keyword);
  // Single words anchor to a token start, which tolerates attached suffixes
  // without matching a keyword buried mid-word.
  return tokens.some((tok) => tok === keyword || tok.startsWith(keyword));
}

export function classifyIntentDetailed(question: string): IntentMatch {
  const haystack = question.toLowerCase();
  const tokens = tokenize(question);

  let best: IntentMatch = { intent: "land_cover", score: 0, matched: [] };

  for (const [intent, words] of Object.entries(KEYWORDS)) {
    const hit = words.filter((w) => matches(w.toLowerCase(), tokens, haystack));
    if (hit.length === 0) continue;
    const score = hit.reduce((sum, w) => sum + w.length, 0);
    if (score > best.score) {
      best = { intent: intent as Intent, score, matched: hit };
    }
  }

  return best;
}

export function classifyIntent(question: string): Intent {
  return classifyIntentDetailed(question).intent;
}
