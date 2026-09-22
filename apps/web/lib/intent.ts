/**
 * Keyword intent classifier — the deliberately dumb stand-in the spec calls
 * for at the `understand` step. The real classifier replaces this behind the
 * same signature; nothing downstream should depend on how the label was found.
 *
 * Keywords are listed per language because the officer may type in any of the
 * four, regardless of the interface language.
 */

export type Intent =
  | "water_extent"
  | "vegetation"
  | "change"
  | "built_up"
  | "land_cover";

const KEYWORDS: Record<Exclude<Intent, "land_cover">, string[]> = {
  water_extent: [
    "water", "flood", "flooded", "flooding", "inundat", "submerged", "river", "lake",
    "पानी", "बाढ़", "जल", "जलमग्न", "नदी",
    "நீர்", "வெள்ள", "மூழ்க", "ஆறு",
    "জল", "বন্যা", "জলমগ্ন", "নদী", "প্লাবিত",
  ],
  vegetation: [
    "crop", "paddy", "rice", "vegetation", "green", "farm", "field", "harvest", "yield", "ndvi",
    "फसल", "धान", "खेत", "हरियाली", "वनस्पति",
    "பயிர்", "நெல்", "வயல்", "தாவர", "பசுமை",
    "ফসল", "ধান", "ক্ষেত", "গাছ", "সবুজ",
  ],
  change: [
    "change", "changed", "difference", "before", "after", "compare", "between",
    "बदल", "परिवर्तन", "अंतर", "पहले", "बाद",
    "மாற்ற", "மாறி", "வேறுபாடு", "முன்", "பின்",
    "পরিবর্তন", "বদল", "পার্থক্য", "আগে", "পরে",
  ],
  built_up: [
    "built", "urban", "building", "settlement", "city", "town", "road", "infrastructure",
    "निर्मित", "शहर", "इमारत", "बस्ती", "सड़क",
    "கட்டிட", "நகர", "குடியிருப்", "சாலை",
    "নির্মিত", "শহর", "বাড়ি", "বসতি", "রাস্তা",
  ],
};

export function classifyIntent(question: string): Intent {
  const q = question.toLowerCase();
  let best: Intent = "land_cover";
  let bestHits = 0;

  for (const [intent, words] of Object.entries(KEYWORDS)) {
    const hits = words.filter((w) => q.includes(w.toLowerCase())).length;
    if (hits > bestHits) {
      bestHits = hits;
      best = intent as Intent;
    }
  }
  return best;
}
